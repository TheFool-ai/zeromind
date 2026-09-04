from datetime import UTC, datetime
from uuid import UUID

import pytest

from zeromind.analysis.projector import AnalysisProjector
from zeromind.analysis.repository import AnalysisQuery, InMemoryAnalysisRepository
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.subscriptions.domain import Subscription
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import WorkflowSpec
from zeromind.workflows.executor import NodeExecutionContext, WorkflowExecutor
from zeromind.workflows.repository import InMemoryWorkflowRepository
from zeromind.workflows.service import WorkflowRunService

NOW = datetime(2026, 7, 31, 2, tzinfo=UTC)


async def build_service(
    *,
    valid_output: bool = True,
    body_like_output: bool = False,
    projected: bool = True,
) -> tuple[
    WorkflowRunService,
    InMemoryWorkflowRepository,
    InMemoryAnalysisRepository,
    WorkflowDefinition,
    UUID,
]:
    subscriptions = InMemorySubscriptionRepository()
    subscription = Subscription.create(
        feed_url="https://example.com/feed",
        title="Example Engineering",
        now=NOW,
    )
    await subscriptions.add(subscription)
    references = InMemoryReferenceRepository()
    await IngestionService(references).ingest(
        subscription_id=subscription.id,
        entries=(
            FeedEntry(
                guid="service",
                url="https://example.com/service",
                title="Service article",
                summary="RSS summary",
                author="Ada",
                published_at=NOW,
                updated_at=None,
            ),
        ),
        fetched_at=NOW,
    )
    reference = (await references.list_references())[0]
    output: dict[str, object] = {
        "schema_version": 1,
        "status": "initial_rejected",
        "reference": {
            "reference_id": str(reference.id),
            "revision": 1,
            "subscription_id": str(subscription.id),
            "url": "https://example.com/service",
            "title": "Service article",
            "summary": "RSS summary",
            "author": "Ada",
            "published_at": NOW.isoformat(),
            "updated_at": None,
            "observed_at": NOW.isoformat(),
        },
        "screening": {
            "score": 20,
            "reason": "Not sufficiently valuable",
            "summary": "Low information density",
            "_execution": {
                "agent_id": "33333333-3333-3333-3333-333333333333",
                "agent_version": 1,
                "provider": "openai",
                "model": "gpt-5-mini",
                "usage": {"input": 50, "output": 10},
            },
        },
    }
    if not valid_output:
        output.pop("screening")
    if body_like_output:
        output["screening"]["summary"] = (  # type: ignore[index]
            "ARTICLE BODY MUST NOT BE STORED"
        )
    spec_payload: dict[str, object] = {
        "name": "projected-service",
        "trigger": {"events": ["manual"]},
        "nodes": [{"id": "noop", "type": "parallel"}],
        "output": output,
    }
    if projected:
        spec_payload["projection"] = "content_analysis_v1"
    definition = WorkflowDefinition.create(
        WorkflowSpec.model_validate(spec_payload),
        now=NOW,
    )
    workflows = InMemoryWorkflowRepository()
    await workflows.add_definition(definition)

    async def noop(
        _: dict[str, object], __: NodeExecutionContext
    ) -> dict[str, object]:
        return {}

    executor = WorkflowExecutor(workflows, handlers={"parallel": noop})
    analyses = InMemoryAnalysisRepository()
    projector = AnalysisProjector(analyses, references, subscriptions)
    service = WorkflowRunService(
        workflows,
        executor,
        projectors={"content_analysis_v1": projector},
    )
    return service, workflows, analyses, definition, reference.id


@pytest.mark.asyncio
async def test_service_projects_completed_run_once() -> None:
    service, _, analyses, definition, reference_id = await build_service()

    first = await service.execute(
        definition.id,
        trigger={
            "event": "manual",
            "reference_id": str(reference_id),
            "revision": 1,
        },
        idempotency_key="manual:analysis-1",
    )
    replayed = await service.execute(
        definition.id,
        trigger={
            "event": "manual",
            "reference_id": str(reference_id),
            "revision": 1,
        },
        idempotency_key="manual:analysis-1",
    )

    assert first.status == "completed"
    assert replayed.id == first.id
    assert len(await analyses.list(AnalysisQuery(effective_decision=None))) == 1


@pytest.mark.asyncio
async def test_service_marks_run_failed_when_projection_is_invalid() -> None:
    service, workflows, analyses, definition, reference_id = await build_service(
        valid_output=False
    )

    with pytest.raises(ValueError, match="analysis_projection_invalid"):
        await service.execute(
            definition.id,
            trigger={
                "event": "manual",
                "reference_id": str(reference_id),
                "revision": 1,
            },
            idempotency_key="manual:invalid-analysis",
        )

    stored = (await workflows.list_runs())[0]
    assert stored.status == "failed"
    assert stored.error is not None
    assert "analysis_projection_invalid" in stored.error
    assert await analyses.get_by_run(stored.id) is None


@pytest.mark.asyncio
async def test_projection_failure_removes_untrusted_output_from_durable_run() -> None:
    service, workflows, analyses, definition, reference_id = await build_service(
        body_like_output=True
    )

    with pytest.raises(ValueError, match="analysis_projection_invalid"):
        await service.execute(
            definition.id,
            trigger={
                "event": "manual",
                "reference_id": str(reference_id),
                "revision": 1,
            },
            idempotency_key="manual:body-like-analysis",
        )

    stored = (await workflows.list_runs())[0]
    assert stored.output is None
    assert "ARTICLE BODY" not in str(stored)
    assert await analyses.get_by_run(stored.id) is None


@pytest.mark.asyncio
async def test_service_preserves_non_projected_workflow_behavior() -> None:
    service, _, analyses, definition, reference_id = await build_service(
        projected=False
    )

    run = await service.execute(
        definition.id,
        trigger={
            "event": "manual",
            "reference_id": str(reference_id),
            "revision": 1,
        },
        idempotency_key="manual:plain",
    )

    assert run.status == "completed"
    assert await analyses.list(AnalysisQuery(effective_decision=None)) == ()


@pytest.mark.asyncio
async def test_service_rejects_unknown_workflow_definition() -> None:
    service, _, _, _, _ = await build_service()

    with pytest.raises(KeyError):
        await service.execute(
            UUID("99999999-9999-9999-9999-999999999999"),
            trigger={"event": "manual"},
            idempotency_key="manual:missing",
        )
