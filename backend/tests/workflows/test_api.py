from fastapi.testclient import TestClient

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.bootstrap.app import create_app
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService
from zeromind.workflows.executor import WorkflowExecutor
from zeromind.workflows.repository import InMemoryWorkflowRepository

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

    return TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=InMemoryReferenceRepository(),
            agent_registry=AgentRegistry(InMemoryAgentRepository()),
            workflow_repository=repository,
            workflow_executor=WorkflowExecutor(
                repository,
                handlers={"parallel": copy_handler},
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
