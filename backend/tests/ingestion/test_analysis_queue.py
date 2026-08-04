from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.ingestion.analysis_queue import (
    AnalysisAlreadyProcessing,
    InMemoryReferenceAnalysisQueue,
    SqlAlchemyReferenceAnalysisQueue,
    recover_reference_analyses,
)
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.lifecycle import (
    InMemoryReferenceAnalysisLifecycleRepository,
)
from zeromind.ingestion.models import ContentReferenceModel
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.shared.models import OutboxEventModel
from zeromind.shared.outbox import InMemoryOutboxRepository
from zeromind.workflows.domain import WorkflowRun
from zeromind.workflows.repository import InMemoryWorkflowRepository

NOW = datetime(2026, 8, 4, 10, tzinfo=UTC)
REQUEST_ID = UUID("33333333-3333-3333-3333-333333333333")


async def _queue() -> tuple[
    InMemoryReferenceAnalysisQueue,
    InMemoryReferenceRepository,
    InMemoryOutboxRepository,
    UUID,
]:
    references = InMemoryReferenceRepository()
    await IngestionService(references).ingest(
        subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
        entries=(
            FeedEntry(
                guid="queue",
                url="https://example.com/queue",
                title="Queued article",
                summary=None,
                author=None,
                published_at=NOW,
                updated_at=None,
            ),
        ),
        fetched_at=NOW,
    )
    reference = (await references.list_references())[0]
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)
    await lifecycle.transition(
        reference.id,
        revision=1,
        status="completed",
        workflow_run_id=UUID("22222222-2222-2222-2222-222222222222"),
        now=NOW,
    )
    outbox = InMemoryOutboxRepository()
    return (
        InMemoryReferenceAnalysisQueue(references, lifecycle, outbox),
        references,
        outbox,
        reference.id,
    )


@pytest.mark.asyncio
async def test_request_atomically_resets_and_enqueues_current_revision() -> None:
    queue, references, outbox, reference_id = await _queue()

    event = await queue.request(
        reference_id,
        1,
        REQUEST_ID,
        "manual",
        now=NOW + timedelta(minutes=1),
    )

    reference = await references.get_reference(reference_id)
    assert reference is not None
    assert reference.analysis_status == "pending"
    assert reference.analysis_workflow_run_id is None
    assert reference.analysis_completed_at is None
    assert event.event_type == "reference.analysis.requested"
    assert event.payload == {
        "reference_id": str(reference_id),
        "revision": 1,
        "request_id": str(REQUEST_ID),
        "reason": "manual",
    }
    assert await outbox.get_by_idempotency_key(event.idempotency_key) == event


@pytest.mark.asyncio
async def test_repeated_request_id_is_idempotent() -> None:
    queue, _, _, reference_id = await _queue()

    first = await queue.request(reference_id, 1, REQUEST_ID, "backfill")
    second = await queue.request(reference_id, 1, REQUEST_ID, "backfill")

    assert second.id == first.id


@pytest.mark.asyncio
async def test_request_rejects_reference_already_processing() -> None:
    queue, references, _, reference_id = await _queue()
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)
    await lifecycle.transition(
        reference_id,
        revision=1,
        status="reviewing",
        workflow_run_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(AnalysisAlreadyProcessing):
        await queue.request(reference_id, 1, REQUEST_ID, "manual")


@pytest_asyncio.fixture
async def sql_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(OutboxEventModel.__table__.create)
        await connection.run_sync(ContentReferenceModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_request_resets_and_enqueues_in_one_transaction(
    sql_sessions: async_sessionmaker[AsyncSession],
) -> None:
    reference_id = UUID("60000000-0000-0000-0000-000000000001")
    async with sql_sessions() as session, session.begin():
        session.add(
            ContentReferenceModel(
                id=reference_id,
                subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
                identity_key="guid:sql-queue",
                original_url=None,
                current_revision=2,
                first_seen_at=NOW,
                last_seen_at=NOW,
                analysis_status="failed",
                analysis_status_revision=2,
                analysis_workflow_run_id=None,
                analysis_error_code="workflow_failed",
                analysis_error_message="provider error",
                analysis_status_updated_at=NOW,
                analysis_started_at=NOW,
                analysis_completed_at=NOW,
            )
        )

    event = await SqlAlchemyReferenceAnalysisQueue(sql_sessions).request(
        reference_id,
        2,
        REQUEST_ID,
        "manual",
        now=NOW + timedelta(minutes=1),
    )

    async with sql_sessions() as session:
        stored = await session.get(ContentReferenceModel, reference_id)
        stored_event = await session.get(OutboxEventModel, event.id)
    assert stored is not None and stored.analysis_status == "pending"
    assert stored.analysis_error_code is None
    assert stored_event is not None
    assert stored_event.payload["request_id"] == str(REQUEST_ID)


@pytest.mark.asyncio
async def test_recovery_repairs_runs_and_requeues_missing_run() -> None:
    references = InMemoryReferenceRepository()
    subscription_id = UUID("11111111-1111-1111-1111-111111111111")
    for index in range(4):
        await IngestionService(references).ingest(
            subscription_id=subscription_id,
            entries=(
                FeedEntry(
                    guid=f"recovery-{index}",
                    url=f"https://example.com/recovery-{index}",
                    title=f"Recovery {index}",
                    summary=None,
                    author=None,
                    published_at=NOW,
                    updated_at=None,
                ),
            ),
            fetched_at=NOW,
        )
    items = await references.list_references()
    failed_reference, completed_reference, stale_reference, missing_reference = items
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)
    workflows = InMemoryWorkflowRepository()
    run_ids = [
        UUID("40000000-0000-0000-0000-000000000001"),
        UUID("40000000-0000-0000-0000-000000000002"),
        UUID("40000000-0000-0000-0000-000000000003"),
    ]
    statuses = ("failed", "completed", "running")
    for reference, run_id, status in zip(items[:3], run_ids, statuses, strict=True):
        await lifecycle.transition(
            reference.id,
            revision=1,
            status="analyzing",
            workflow_run_id=run_id,
            now=NOW,
        )
        await workflows.add_run(
            WorkflowRun(
                id=run_id,
                definition_id=UUID("50000000-0000-0000-0000-000000000001"),
                definition_version=1,
                idempotency_key=f"recovery:{run_id}",
                trigger={
                    "reference_id": str(reference.id),
                    "revision": 1,
                },
                status=status,
                output={"status": "qualified"} if status == "completed" else None,
                error="provider failed" if status == "failed" else None,
                started_at=NOW,
                completed_at=NOW if status != "running" else None,
            )
        )
    await lifecycle.transition(
        missing_reference.id,
        revision=1,
        status="queued",
        workflow_run_id=None,
        now=NOW,
    )
    outbox = InMemoryOutboxRepository()
    queue = InMemoryReferenceAnalysisQueue(references, lifecycle, outbox)

    class Analyses:
        async def get_by_run(self, run_id: UUID) -> object | None:
            return (
                SimpleNamespace(generated_status="qualified")
                if run_id == run_ids[1]
                else None
            )

    result = await recover_reference_analyses(
        references,
        lifecycle,
        workflows,
        Analyses(),  # type: ignore[arg-type]
        queue,
        before=NOW + timedelta(minutes=30),
        now=NOW + timedelta(hours=1),
    )

    failed = await references.get_reference(failed_reference.id)
    completed = await references.get_reference(completed_reference.id)
    stale = await references.get_reference(stale_reference.id)
    missing = await references.get_reference(missing_reference.id)
    assert failed is not None and failed.analysis_error_code == "workflow_failed"
    assert completed is not None and completed.analysis_status == "completed"
    assert stale is not None and stale.analysis_error_code == "stale_workflow"
    assert missing is not None and missing.analysis_status == "pending"
    assert result.repaired == 3
    assert result.requeued == 1
