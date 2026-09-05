from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.notes.domain import Note
from zeromind.notes.models import NoteModel
from zeromind.notes.repository import (
    InMemoryNoteRepository,
    SqlAlchemyNoteRepository,
)

NOW = datetime(2026, 7, 31, 7, tzinfo=UTC)
REFERENCE_ID = UUID("11111111-1111-1111-1111-111111111111")
ANALYSIS_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def note(
    *,
    identifier: int,
    owner: str = "admin",
    reference_id: UUID = REFERENCE_ID,
    analysis_id: UUID | None = ANALYSIS_ID,
    body: str = "Important insight",
) -> Note:
    return Note.create(
        identifier=UUID(int=identifier),
        reference_id=reference_id,
        analysis_id=analysis_id,
        owner_subject=owner,
        body=body,
        now=NOW + timedelta(minutes=identifier),
    )


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(NoteModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_repository_round_trips_and_filters_shared_notes(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyNoteRepository(sessions)
    first = note(identifier=1)
    second = note(
        identifier=2,
        owner="other",
        reference_id=UUID(
            "22222222-2222-2222-2222-222222222222"
        ),
        analysis_id=None,
    )
    await repository.add(first)
    await repository.add(second)

    restored = await repository.get(first.id)
    by_reference = await repository.list(
        reference_id=REFERENCE_ID,
    )
    by_analysis = await repository.list(
        analysis_id=ANALYSIS_ID,
    )

    assert restored is not None
    assert restored.body == "Important insight"
    assert [item.id for item in by_reference] == [first.id]
    assert [item.id for item in by_analysis] == [first.id]
    assert [item.id for item in await repository.list()] == [first.id, second.id]


@pytest.mark.asyncio
async def test_sql_repository_updates_only_target_and_hard_deletes(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyNoteRepository(sessions)
    first = note(identifier=1)
    second = note(identifier=2, body="Keep unchanged")
    await repository.add(first)
    await repository.add(second)
    first.update(
        body="Updated insight",
        analysis_id=None,
        now=NOW + timedelta(hours=1),
    )

    await repository.save(first)
    await repository.delete(first.id)

    assert await repository.get(first.id) is None
    restored_second = await repository.get(second.id)
    assert restored_second is not None
    assert restored_second.body == "Keep unchanged"


@pytest.mark.asyncio
async def test_in_memory_repository_shares_notes_from_all_owners() -> None:
    repository = InMemoryNoteRepository()
    first = note(identifier=1)
    second = note(identifier=2, owner="other")
    await repository.add(first)
    await repository.add(second)

    restored = await repository.get(first.id)
    assert restored is not None
    assert restored.owner_subject == "admin"
    assert [item.id for item in await repository.list()] == [first.id, second.id]
    await repository.delete(first.id)
    assert await repository.get(first.id) is None
    assert await repository.get(second.id) is not None
