from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from zeromind.ingestion.analysis_queue import InMemoryReferenceAnalysisQueue
from zeromind.ingestion.backfill import backfill_reference_analysis
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.lifecycle import (
    InMemoryReferenceAnalysisLifecycleRepository,
)
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.shared.outbox import InMemoryOutboxRepository

NOW = datetime(2026, 8, 4, tzinfo=UTC)


async def _setup() -> tuple[
    InMemoryReferenceAnalysisQueue,
    InMemoryReferenceRepository,
    InMemoryOutboxRepository,
]:
    references = InMemoryReferenceRepository()
    for index in range(5):
        await IngestionService(references).ingest(
            subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
            entries=(
                FeedEntry(
                    guid=f"backfill-{index}",
                    url=f"https://example.com/{index}",
                    title=f"Article {index}",
                    summary=None,
                    author=None,
                    published_at=NOW + timedelta(minutes=index),
                    updated_at=None,
                ),
            ),
            fetched_at=NOW,
        )
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)
    items = await references.list_references()
    await lifecycle.transition(
        items[1].id,
        revision=1,
        status="completed",
        workflow_run_id=None,
        now=NOW,
    )
    await lifecycle.transition(
        items[2].id,
        revision=1,
        status="initial_rejected",
        workflow_run_id=None,
        now=NOW,
    )
    await lifecycle.transition(
        items[3].id,
        revision=1,
        status="failed",
        workflow_run_id=None,
        error_code="workflow_failed",
        error_message="failed",
        now=NOW,
    )
    await lifecycle.transition(
        items[4].id,
        revision=1,
        status="analyzing",
        workflow_run_id=None,
        now=NOW,
    )
    outbox = InMemoryOutboxRepository()
    return (
        InMemoryReferenceAnalysisQueue(references, lifecycle, outbox),
        references,
        outbox,
    )


@pytest.mark.asyncio
async def test_dry_run_counts_without_writing() -> None:
    queue, references, outbox = await _setup()

    result = await backfill_reference_analysis(
        queue,
        references,
        all_references=True,
        batch_size=2,
        limit=None,
        generation="dry-run",
        dry_run=True,
        workflow_version=4,
    )

    assert result.scanned == 5
    assert result.enqueued == 4
    assert result.skipped == 1
    assert result.status_counts == {
        "pending": 1,
        "queued": 0,
        "processing": 1,
        "completed": 1,
        "rejected": 1,
        "failed": 1,
    }
    assert await outbox.claim(now=NOW, limit=10, lease=timedelta(minutes=1)) == ()


@pytest.mark.asyncio
async def test_default_skips_completed_rejected_and_processing() -> None:
    queue, references, outbox = await _setup()

    result = await backfill_reference_analysis(
        queue,
        references,
        all_references=False,
        batch_size=100,
        limit=None,
        generation="default",
        dry_run=False,
        workflow_version=4,
    )

    events = await outbox.claim(
        now=datetime.now(UTC),
        limit=10,
        lease=timedelta(minutes=1),
    )
    assert result.enqueued == 2
    assert len(events) == 2


@pytest.mark.asyncio
async def test_generation_is_idempotent_and_new_generation_requeues() -> None:
    queue, references, outbox = await _setup()
    arguments = {
        "all_references": True,
        "batch_size": 2,
        "limit": None,
        "dry_run": False,
        "workflow_version": 4,
    }

    await backfill_reference_analysis(
        queue,
        references,
        generation="generation-a",
        **arguments,
    )
    await backfill_reference_analysis(
        queue,
        references,
        generation="generation-a",
        **arguments,
    )
    first_generation = await outbox.claim(
        now=datetime.now(UTC),
        limit=20,
        lease=timedelta(minutes=1),
    )
    assert len(first_generation) == 4

    await backfill_reference_analysis(
        queue,
        references,
        generation="generation-b",
        **arguments,
    )
    second_generation = await outbox.claim(
        now=datetime.now(UTC),
        limit=20,
        lease=timedelta(minutes=1),
    )
    assert len(second_generation) == 4


@pytest.mark.asyncio
async def test_limit_caps_work_across_small_batches() -> None:
    queue, references, outbox = await _setup()

    result = await backfill_reference_analysis(
        queue,
        references,
        all_references=True,
        batch_size=1,
        limit=2,
        generation="limited",
        dry_run=False,
    )

    events = await outbox.claim(
        now=datetime.now(UTC),
        limit=10,
        lease=timedelta(minutes=1),
    )
    assert result.enqueued == 2
    assert len(events) == 2
