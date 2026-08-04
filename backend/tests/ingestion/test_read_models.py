from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from zeromind.analysis.domain import ContentAnalysis, ScoreDimension
from zeromind.analysis.repository import InMemoryAnalysisRepository
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.lifecycle import (
    InMemoryReferenceAnalysisLifecycleRepository,
)
from zeromind.ingestion.read_models import ReferenceListQuery, ReferenceReadService
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.subscriptions.domain import Subscription
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.workflows.constants import MAIN_ANALYSIS_WORKFLOW_NAME
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import WorkflowSpec
from zeromind.workflows.repository import InMemoryWorkflowRepository

NOW = datetime(2026, 8, 4, tzinfo=UTC)


async def _service() -> tuple[ReferenceReadService, tuple[UUID, UUID]]:
    subscriptions = InMemorySubscriptionRepository()
    subscription = Subscription.create(
        feed_url="https://example.com/feed",
        title="Example Engineering",
        now=NOW,
    )
    await subscriptions.add(subscription)
    references = InMemoryReferenceRepository()
    for index in range(2):
        await IngestionService(references).ingest(
            subscription_id=subscription.id,
            entries=(
                FeedEntry(
                    guid=f"read-{index}",
                    url=f"https://example.com/article-{index}",
                    title=f"Article {index}",
                    summary=f"Summary {index}",
                    author="Ada",
                    published_at=NOW + timedelta(days=index),
                    updated_at=None,
                ),
            ),
            fetched_at=NOW,
        )
    first, second = await references.list_references()
    workflows = InMemoryWorkflowRepository()
    workflow = WorkflowDefinition.create(
        WorkflowSpec.model_validate(
            {
                "name": MAIN_ANALYSIS_WORKFLOW_NAME,
                "trigger": {"events": ["manual"]},
                "nodes": [{"id": "noop", "type": "parallel"}],
            }
        ),
        now=NOW,
    )
    workflow.activate(now=NOW)
    await workflows.add_definition(workflow)
    analyses = InMemoryAnalysisRepository()
    await analyses.add(
        ContentAnalysis(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            reference_id=second.id,
            reference_revision=1,
            subscription_id=subscription.id,
            workflow_definition_id=workflow.id,
            workflow_definition_version=workflow.version,
            workflow_run_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            generated_status="qualified",
            source_name=subscription.title,
            source_feed_url=subscription.feed_url,
            title="Article 1",
            original_url="https://example.com/article-1",
            author="Ada",
            published_at=NOW + timedelta(days=1),
            observed_at=NOW,
            screening_score=90,
            screening_reason="Strong",
            screening_summary="Useful",
            primary_category="AI",
            secondary_categories=("Software",),
            tags=("agents",),
            one_sentence_summary="A strong article.",
            summary="Structured analysis summary.",
            viewpoints=(),
            key_quotes=(),
            total_score=88,
            dimensions={
                "depth": ScoreDimension(
                    value=88,
                    weight=1,
                    reason="Detailed",
                )
            },
            recommendation_level="recommended",
            recommendation_reason="High value",
            provenance={},
            created_at=NOW,
        )
    )
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)
    await lifecycle.transition(
        second.id,
        revision=1,
        status="completed",
        workflow_run_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        now=NOW,
    )
    return (
        ReferenceReadService(references, subscriptions, analyses, workflows),
        (first.id, second.id),
    )


@pytest.mark.asyncio
async def test_list_keeps_pending_and_uses_current_main_analysis_preview() -> None:
    service, _ = await _service()

    items = await service.list(ReferenceListQuery())

    assert len(items) == 2
    assert items[0].analysis is None
    assert items[1].analysis is not None
    assert items[1].analysis.one_sentence_summary == "A strong article."
    assert items[1].subscription is not None
    assert items[1].subscription.title == "Example Engineering"


@pytest.mark.asyncio
async def test_list_filters_lifecycle_category_score_subscription_and_date() -> None:
    service, _ = await _service()
    all_items = await service.list(ReferenceListQuery())
    subscription_id = all_items[0].reference.subscription_id

    filtered = await service.list(
        ReferenceListQuery(
            status="completed",
            category="Software",
            minimum_score=85,
            subscription_id=subscription_id,
            published_from=NOW + timedelta(hours=12),
            published_to=NOW + timedelta(days=2),
        )
    )

    assert [item.revision.title for item in filtered] == ["Article 1"]


@pytest.mark.asyncio
async def test_reading_detail_normalizes_iframe_and_returns_analysis() -> None:
    service, (_, completed_id) = await _service()

    detail = await service.get(completed_id)

    assert detail.iframe_url == "https://example.com/article-1"
    assert detail.revision.summary == "Summary 1"
    assert detail.analysis is not None
    assert detail.analysis.total_score == 88
