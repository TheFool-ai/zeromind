import asyncio
from datetime import UTC, datetime

import yaml
from fastapi.testclient import TestClient

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.analysis.repository import AnalysisQuery, InMemoryAnalysisRepository
from zeromind.bootstrap.app import create_app
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.subscriptions.domain import Subscription
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService
from zeromind.workflows.executor import WorkflowExecutor
from zeromind.workflows.repository import InMemoryWorkflowRepository
from zeromind.workflows.service import WorkflowRunService

SOURCE = """
name: manual-copy
trigger: {events: [manual]}
nodes:
  - id: copy
    type: parallel
    input:
      value: $.trigger.value
output:
  value: $.steps.copy.value
"""


def make_client() -> TestClient:
    repository = InMemoryWorkflowRepository()

    async def copy_handler(value: dict[str, object]) -> dict[str, object]:
        return value

    executor = WorkflowExecutor(
        repository,
        handlers={"parallel": copy_handler},
    )
    return TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=InMemoryReferenceRepository(),
            agent_registry=AgentRegistry(InMemoryAgentRepository()),
            workflow_repository=repository,
            workflow_run_service=WorkflowRunService(
                repository,
                executor,
                projectors={},
            ),
        )
    )


def test_create_activate_and_run_workflow_idempotently() -> None:
    client = make_client()

    validated = client.post("/api/v1/workflows/validate", json={"source": SOURCE})
    created = client.post("/api/v1/workflows", json={"source": SOURCE})
    workflow_id = created.json()["id"]
    activated = client.post(f"/api/v1/workflows/{workflow_id}/activate")
    first = client.post(
        f"/api/v1/workflows/{workflow_id}/runs",
        json={"idempotency_key": "manual:1", "trigger": {"value": "hello"}},
    )
    second = client.post(
        f"/api/v1/workflows/{workflow_id}/runs",
        json={"idempotency_key": "manual:1", "trigger": {"value": "ignored"}},
    )
    runs = client.get("/api/v1/workflow-runs")

    assert validated.status_code == 200
    assert validated.json()["topological_order"] == ["copy"]
    assert created.status_code == 201
    assert activated.json()["status"] == "active"
    assert first.status_code == 201
    assert first.json()["output"] == {"value": "hello"}
    assert second.json()["id"] == first.json()["id"]
    assert len(runs.json()["items"]) == 1


def test_invalid_workflow_returns_structured_validation_error() -> None:
    response = make_client().post(
        "/api/v1/workflows/validate",
        json={
            "source": """
name: unsafe
trigger: {events: [manual]}
nodes:
  - {id: bad, type: parallel, input: {value: "lambda x: x"}}
"""
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_workflow"


def test_validation_reports_projection_terminal_gates_and_threshold_warnings() -> None:
    response = make_client().post(
        "/api/v1/workflows/validate",
        json={
            "source": """
name: analyzed
trigger: {events: [manual]}
projection: content_analysis_v1
nodes:
  - {id: prepare, type: parallel}
  - id: quality_gate
    type: gate
    depends_on: [prepare]
    predicate: {left: $.steps.prepare.score, operator: gte, right: 101}
    reject: {output: {schema_version: 1, status: fine_rejected}}
output: {schema_version: 1, status: qualified}
"""
        },
    )

    assert response.status_code == 200
    assert response.json()["projection"] == "content_analysis_v1"
    assert response.json()["terminal_gates"] == ["quality_gate"]
    assert len(response.json()["warnings"]) == 1
    assert "quality_gate" in response.json()["warnings"][0]
    assert "101" in response.json()["warnings"][0]


def test_manual_api_run_uses_default_analysis_projector() -> None:
    async def arrange() -> tuple[
        InMemorySubscriptionRepository,
        InMemoryReferenceRepository,
        Subscription,
        object,
    ]:
        subscriptions = InMemorySubscriptionRepository()
        subscription = Subscription.create(
            feed_url="https://example.com/feed",
            title="Example Engineering",
        )
        await subscriptions.add(subscription)
        references = InMemoryReferenceRepository()
        await IngestionService(references).ingest(
            subscription_id=subscription.id,
            entries=(
                FeedEntry(
                    guid="api-projection",
                    url="https://example.com/api-projection",
                    title="API projection",
                    summary="RSS summary",
                    author="Ada",
                    published_at=datetime(2026, 7, 31, tzinfo=UTC),
                    updated_at=None,
                ),
            ),
            fetched_at=datetime(2026, 7, 31, 1, tzinfo=UTC),
        )
        reference = (await references.list_references())[0]
        return subscriptions, references, subscription, reference

    subscriptions, references, subscription, reference = asyncio.run(arrange())
    analyses = InMemoryAnalysisRepository()
    output = {
        "schema_version": 1,
        "status": "initial_rejected",
        "reference": {
            "reference_id": str(reference.id),
            "revision": 1,
            "subscription_id": str(subscription.id),
            "url": "https://example.com/api-projection",
            "title": "API projection",
            "summary": "RSS summary",
            "author": "Ada",
            "published_at": "2026-07-31T00:00:00+00:00",
            "updated_at": None,
            "observed_at": "2026-07-31T01:00:00+00:00",
        },
        "screening": {
            "score": 10,
            "reason": "Low information density",
            "summary": "A low-value update",
            "_execution": {
                "agent_id": "33333333-3333-3333-3333-333333333333",
                "agent_version": 1,
                "provider": "openai",
                "model": "gpt-5-mini",
                "usage": {},
            },
        },
    }
    source = yaml.safe_dump(
        {
            "name": "manual-projection",
            "trigger": {"events": ["manual"]},
            "projection": "content_analysis_v1",
            "nodes": [{"id": "noop", "type": "parallel"}],
            "output": output,
        },
        sort_keys=False,
    )
    client = TestClient(
        create_app(
            subscription_service=SubscriptionService(subscriptions),
            subscription_repository=subscriptions,
            reference_repository=references,
            agent_registry=AgentRegistry(InMemoryAgentRepository()),
            workflow_repository=InMemoryWorkflowRepository(),
            analysis_repository=analyses,
        )
    )

    created = client.post("/api/v1/workflows", json={"source": source})
    workflow_id = created.json()["id"]
    client.post(f"/api/v1/workflows/{workflow_id}/activate")
    run = client.post(
        f"/api/v1/workflows/{workflow_id}/runs",
        json={
            "idempotency_key": "manual:projected",
            "trigger": {
                "reference_id": str(reference.id),
                "revision": 1,
            },
        },
    )

    projected = asyncio.run(
        analyses.list(AnalysisQuery(effective_decision=None))
    )
    assert run.status_code == 201
    assert run.json()["status"] == "completed"
    assert len(projected) == 1
    assert projected[0].source_name == "Example Engineering"
