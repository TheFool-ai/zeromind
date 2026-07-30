from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.models import ContentReferenceModel, ReferenceRevisionModel
from zeromind.ingestion.repository import (
    InMemoryReferenceRepository,
    SqlAlchemyReferenceRepository,
)
from zeromind.ingestion.service import IngestionService
from zeromind.shared.models import OutboxEventModel


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(OutboxEventModel.__table__.create)
        await connection.run_sync(ContentReferenceModel.__table__.create)
        await connection.run_sync(ReferenceRevisionModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_repository_preserves_ingestion_idempotency(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyReferenceRepository(sessions)
    service = IngestionService(repository)
    entry = FeedEntry(
        guid="42",
        url="https://example.com/42",
        title="Post",
        summary=None,
        author=None,
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=None,
    )
    subscription_id = UUID("11111111-1111-1111-1111-111111111111")

    await service.ingest(
        subscription_id=subscription_id,
        entries=(entry,),
        fetched_at=datetime(2026, 7, 29, 12, tzinfo=UTC),
    )
    result = await service.ingest(
        subscription_id=subscription_id,
        entries=(entry,),
        fetched_at=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
    )

    references = await repository.list_references()
    assert result.unchanged == 1
    assert len(references) == 1
    assert len(await repository.list_revisions(references[0].id)) == 1
    async with sessions() as session:
        event_count = await session.scalar(
            select(func.count()).select_from(OutboxEventModel)
        )
    assert event_count == 1


@pytest.mark.asyncio
async def test_memory_repository_reads_a_specific_reference_revision() -> None:
    repository = InMemoryReferenceRepository()
    service = IngestionService(repository)
    subscription_id = UUID("11111111-1111-1111-1111-111111111111")
    first = FeedEntry(
        guid="42",
        url="https://example.com/42",
        title="First title",
        summary=None,
        author=None,
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=None,
    )
    second = FeedEntry(
        guid="42",
        url="https://example.com/42",
        title="Second title",
        summary=None,
        author=None,
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )

    await service.ingest(
        subscription_id=subscription_id,
        entries=(first,),
        fetched_at=datetime(2026, 7, 29, 12, tzinfo=UTC),
    )
    await service.ingest(
        subscription_id=subscription_id,
        entries=(second,),
        fetched_at=datetime(2026, 7, 30, 12, tzinfo=UTC),
    )
    reference = (await repository.list_references())[0]

    assert (await repository.get_revision(reference.id, 1)).title == "First title"
    assert (await repository.get_revision(reference.id, 2)).title == "Second title"
    with pytest.raises(KeyError, match=str(reference.id)):
        await repository.get_revision(reference.id, 3)


@pytest.mark.asyncio
async def test_sql_repository_reads_a_specific_reference_revision(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyReferenceRepository(sessions)
    service = IngestionService(repository)
    subscription_id = UUID("11111111-1111-1111-1111-111111111111")
    first = FeedEntry(
        guid="revision",
        url="https://example.com/revision",
        title="Version one",
        summary=None,
        author=None,
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=None,
    )
    second = FeedEntry(
        guid="revision",
        url="https://example.com/revision",
        title="Version two",
        summary=None,
        author=None,
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )

    await service.ingest(
        subscription_id=subscription_id,
        entries=(first,),
        fetched_at=datetime(2026, 7, 29, 12, tzinfo=UTC),
    )
    await service.ingest(
        subscription_id=subscription_id,
        entries=(second,),
        fetched_at=datetime(2026, 7, 30, 12, tzinfo=UTC),
    )
    reference = (await repository.list_references())[0]

    assert (await repository.get_revision(reference.id, 1)).title == "Version one"
    assert (await repository.get_revision(reference.id, 2)).title == "Version two"
    with pytest.raises(KeyError, match=str(reference.id)):
        await repository.get_revision(reference.id, 99)
