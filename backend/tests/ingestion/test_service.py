from datetime import UTC, datetime
from uuid import UUID

import pytest

from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService

SUBSCRIPTION_ID = UUID("11111111-1111-1111-1111-111111111111")
FETCHED_AT = datetime(2026, 7, 29, 12, tzinfo=UTC)


def make_entry(*, title: str = "Original") -> FeedEntry:
    return FeedEntry(
        guid="post-42",
        url="https://example.com/posts/42",
        title=title,
        summary="Summary",
        author="Ada",
        published_at=datetime(2026, 7, 28, tzinfo=UTC),
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_repeated_payload_creates_one_reference_revision_and_event() -> None:
    repository = InMemoryReferenceRepository()
    service = IngestionService(repository)

    first = await service.ingest(
        subscription_id=SUBSCRIPTION_ID,
        entries=(make_entry(),),
        fetched_at=FETCHED_AT,
    )
    repeated = await service.ingest(
        subscription_id=SUBSCRIPTION_ID,
        entries=(make_entry(),),
        fetched_at=FETCHED_AT,
    )

    assert first.discovered == 1
    assert first.events[0].event_type == "reference.discovered"
    assert repeated.unchanged == 1
    assert repeated.events == ()
    assert len(await repository.list_references()) == 1
    reference = (await repository.list_references())[0]
    assert len(await repository.list_revisions(reference.id)) == 1


@pytest.mark.asyncio
async def test_changed_metadata_creates_exactly_one_update_revision() -> None:
    repository = InMemoryReferenceRepository()
    service = IngestionService(repository)
    await service.ingest(
        subscription_id=SUBSCRIPTION_ID,
        entries=(make_entry(),),
        fetched_at=FETCHED_AT,
    )
    existing = (await repository.list_references())[0]
    existing.analysis_status = "completed"
    existing.analysis_workflow_run_id = UUID(
        "22222222-2222-2222-2222-222222222222"
    )
    existing.analysis_error_code = "old_error"
    existing.analysis_error_message = "old error"
    existing.analysis_started_at = FETCHED_AT
    existing.analysis_completed_at = FETCHED_AT

    changed = await service.ingest(
        subscription_id=SUBSCRIPTION_ID,
        entries=(make_entry(title="Corrected"),),
        fetched_at=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
    )
    repeated = await service.ingest(
        subscription_id=SUBSCRIPTION_ID,
        entries=(make_entry(title="Corrected"),),
        fetched_at=datetime(2026, 7, 29, 13, tzinfo=UTC),
    )

    reference = (await repository.list_references())[0]
    revisions = await repository.list_revisions(reference.id)
    assert changed.updated == 1
    assert changed.events[0].event_type == "reference.updated"
    assert [revision.number for revision in revisions] == [1, 2]
    assert repeated.unchanged == 1
    assert repeated.events == ()
    assert reference.analysis_status == "pending"
    assert reference.analysis_status_revision == 2
    assert reference.analysis_workflow_run_id is None
    assert reference.analysis_error_code is None
    assert reference.analysis_started_at is None
    assert reference.analysis_completed_at is None


@pytest.mark.asyncio
async def test_old_unseen_entry_is_still_discovered() -> None:
    repository = InMemoryReferenceRepository()
    service = IngestionService(repository)
    old = make_entry()

    result = await service.ingest(
        subscription_id=SUBSCRIPTION_ID,
        entries=(old,),
        fetched_at=datetime(2026, 8, 29, tzinfo=UTC),
        window_start=datetime(2026, 8, 28, tzinfo=UTC),
    )

    assert result.discovered == 1
