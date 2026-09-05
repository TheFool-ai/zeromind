from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from zeromind.analysis.projector import AnalysisProjector
from zeromind.analysis.repository import AnalysisQuery, InMemoryAnalysisRepository
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.subscriptions.domain.aggregates.subscription import Subscription
from zeromind.subscriptions.infrastructure.persistence.in_memory_subscription_repository import (
    InMemorySubscriptionRepository,
)
from zeromind.subscriptions.public import SubscriptionService
from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import parse_workflow_yaml

NOW = datetime(2026, 7, 31, 1, tzinfo=UTC)


async def source_repositories() -> tuple[
    InMemoryReferenceRepository,
    InMemorySubscriptionRepository,
    UUID,
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
                guid="article",
                url="https://example.com/article",
                title="A useful article",
                summary="RSS summary",
                author="Ada",
                published_at=datetime(2026, 7, 30, tzinfo=UTC),
                updated_at=None,
            ),
        ),
        fetched_at=NOW,
    )
    reference = (await references.list_references())[0]
    return references, subscriptions, reference.id, subscription.id


def analysis_definition(*, projected: bool = True) -> WorkflowDefinition:
    projection = "projection: content_analysis_v1" if projected else ""
    return WorkflowDefinition.create(
        parse_workflow_yaml(
            f"""
name: project-analysis
trigger: {{events: [manual]}}
{projection}
nodes: [{{id: result, type: parallel}}]
output: {{}}
"""
        ),
        now=NOW,
    )


def qualified_output(
    *,
    reference_id: UUID,
    subscription_id: UUID,
    revision: int = 1,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "qualified",
        "reference": {
            "reference_id": str(reference_id),
            "revision": revision,
            "subscription_id": str(subscription_id),
            "url": "https://example.com/article",
            "title": "A useful article",
            "summary": "RSS summary",
            "author": "Ada",
            "published_at": "2026-07-30T00:00:00+00:00",
            "updated_at": None,
            "observed_at": NOW.isoformat(),
        },
        "screening": {
            "score": 85,
            "reason": "Relevant and substantial",
            "summary": "Metadata screening summary",
            "_execution": {
                "agent_id": "33333333-3333-3333-3333-333333333333",
                "agent_version": 1,
                "provider": "openai",
                "model": "gpt-5-mini",
                "usage": {"input": 50, "output": 10},
            },
        },
        "content": {
            "primary_category": "AI",
            "secondary_categories": ["Engineering"],
            "tags": ["agents", "workflows"],
            "one_sentence_summary": "A practical Agent workflow guide.",
            "summary": "The article explains a practical workflow architecture.",
            "viewpoints": [
                {
                    "statement": "Deterministic gates improve explainability.",
                    "explanation": "Thresholds remain visible and testable.",
                }
            ],
            "key_quotes": [
                {
                    "text": "Keep model judgment separate from deterministic policy.",
                    "context": "The author discusses scoring.",
                }
            ],
            "recommendation_level": "recommended",
            "recommendation_reason": "High information density",
            "scores": {
                "depth": {"value": 90, "reason": "Detailed evidence"},
                "clarity": {"value": 80, "reason": "Clear structure"},
            },
            "_execution": {
                "agent_id": "44444444-4444-4444-4444-444444444444",
                "agent_version": 2,
                "provider": "openai",
                "model": "gpt-5",
                "usage": {"input": 500, "output": 100},
            },
        },
        "score": {
            "total": 86,
            "dimensions": {
                "depth": {
                    "value": 90,
                    "weight": 0.6,
                    "reason": "Detailed evidence",
                },
                "clarity": {
                    "value": 80,
                    "weight": 0.4,
                    "reason": "Clear structure",
                },
            },
        },
    }


def completed_run(
    definition: WorkflowDefinition,
    *,
    reference_id: UUID,
    output: dict[str, object],
    revision: int = 1,
    identifier: UUID | None = None,
) -> WorkflowRun:
    return WorkflowRun(
        id=identifier or uuid4(),
        definition_id=definition.id,
        definition_version=definition.version,
        idempotency_key=f"manual:{identifier or 'one'}",
        trigger={
            "event": "manual",
            "reference_id": str(reference_id),
            "revision": revision,
        },
        status="completed",
        output=output,
        error=None,
        started_at=NOW,
        completed_at=NOW,
    )


@pytest.mark.asyncio
async def test_projector_persists_completed_run_once_with_provenance() -> None:
    references, subscriptions, reference_id, subscription_id = (
        await source_repositories()
    )
    analyses = InMemoryAnalysisRepository()
    projector = AnalysisProjector(analyses, references, SubscriptionService(subscriptions))
    definition = analysis_definition()
    run = completed_run(
        definition,
        reference_id=reference_id,
        output=qualified_output(
            reference_id=reference_id,
            subscription_id=subscription_id,
        ),
    )

    projected = await projector.project(definition, run)
    replayed = await projector.project(definition, run)

    assert projected is not None
    assert replayed is not None
    assert replayed.id == projected.id
    assert projected.reference_id == reference_id
    assert projected.reference_revision == 1
    assert projected.source_name == "Example Engineering"
    assert projected.source_feed_url == "https://example.com/feed"
    assert projected.provenance["screening"]["agent_version"] == 1  # type: ignore[index]
    assert projected.provenance["analysis"]["agent_version"] == 2  # type: ignore[index]
    assert len(await analyses.list(AnalysisQuery(effective_decision=None))) == 1


@pytest.mark.asyncio
async def test_projector_ignores_workflow_without_projection() -> None:
    references, subscriptions, reference_id, subscription_id = (
        await source_repositories()
    )
    analyses = InMemoryAnalysisRepository()
    definition = analysis_definition(projected=False)
    run = completed_run(
        definition,
        reference_id=reference_id,
        output=qualified_output(
            reference_id=reference_id,
            subscription_id=subscription_id,
        ),
    )

    projected = await AnalysisProjector(
        analyses,
        references,
        SubscriptionService(subscriptions),
    ).project(definition, run)

    assert projected is None
    assert await analyses.list(AnalysisQuery(effective_decision=None)) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch",
    ["trigger_reference", "output_revision", "subscription"],
)
async def test_projector_rejects_inconsistent_reference_provenance(
    mismatch: str,
) -> None:
    references, subscriptions, reference_id, subscription_id = (
        await source_repositories()
    )
    analyses = InMemoryAnalysisRepository()
    definition = analysis_definition()
    output = qualified_output(
        reference_id=reference_id,
        subscription_id=subscription_id,
    )
    trigger_reference = reference_id
    if mismatch == "trigger_reference":
        trigger_reference = uuid4()
    elif mismatch == "output_revision":
        output["reference"]["revision"] = 2  # type: ignore[index]
    else:
        output["reference"]["subscription_id"] = str(uuid4())  # type: ignore[index]
    run = completed_run(
        definition,
        reference_id=trigger_reference,
        output=output,
    )

    with pytest.raises(ValueError, match="reference|revision|subscription"):
        await AnalysisProjector(
            analyses,
            references,
            SubscriptionService(subscriptions),
        ).project(definition, run)

    assert await analyses.list(AnalysisQuery(effective_decision=None)) == ()


@pytest.mark.asyncio
async def test_projector_rejects_missing_reference_revision() -> None:
    references, subscriptions, reference_id, subscription_id = (
        await source_repositories()
    )
    analyses = InMemoryAnalysisRepository()
    definition = analysis_definition()
    run = completed_run(
        definition,
        reference_id=reference_id,
        revision=99,
        output=qualified_output(
            reference_id=reference_id,
            subscription_id=subscription_id,
            revision=99,
        ),
    )

    with pytest.raises(ValueError, match="revision"):
        await AnalysisProjector(
            analyses,
            references,
            SubscriptionService(subscriptions),
        ).project(definition, run)

    assert await analyses.list(AnalysisQuery(effective_decision=None)) == ()


@pytest.mark.asyncio
async def test_projector_rejects_invalid_or_transient_output_without_partial_write() -> None:
    references, subscriptions, reference_id, subscription_id = (
        await source_repositories()
    )
    analyses = InMemoryAnalysisRepository()
    definition = analysis_definition()
    output = deepcopy(
        qualified_output(
            reference_id=reference_id,
            subscription_id=subscription_id,
        )
    )
    output["content"]["summary"] = "ARTICLE BODY MUST NOT BE STORED"  # type: ignore[index]
    run = completed_run(
        definition,
        reference_id=reference_id,
        output=output,
    )

    with pytest.raises(ValueError, match="article body"):
        await AnalysisProjector(
            analyses,
            references,
            SubscriptionService(subscriptions),
        ).project(definition, run)

    assert await analyses.list(AnalysisQuery(effective_decision=None)) == ()


@pytest.mark.asyncio
async def test_projector_reuses_business_identity_across_different_runs() -> None:
    references, subscriptions, reference_id, subscription_id = (
        await source_repositories()
    )
    analyses = InMemoryAnalysisRepository()
    projector = AnalysisProjector(analyses, references, SubscriptionService(subscriptions))
    definition = analysis_definition()
    output = qualified_output(
        reference_id=reference_id,
        subscription_id=subscription_id,
    )

    first = await projector.project(
        definition,
        completed_run(
            definition,
            reference_id=reference_id,
            output=output,
            identifier=UUID(int=1),
        ),
    )
    replayed = await projector.project(
        definition,
        completed_run(
            definition,
            reference_id=reference_id,
            output=output,
            identifier=UUID(int=2),
        ),
    )

    assert first is not None
    assert replayed is not None
    assert replayed.id == first.id
    assert len(await analyses.list(AnalysisQuery(effective_decision=None))) == 1
