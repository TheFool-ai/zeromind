from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.shared.models import OutboxEventModel
from zeromind.shared.outbox import (
    InMemoryOutboxRepository,
    OutboxDispatcher,
    SqlAlchemyOutboxRepository,
)


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(OutboxEventModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_is_idempotent_and_recovers_expired_lease() -> None:
    repository = InMemoryOutboxRepository()
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    first = await repository.enqueue(
        event_type="reference.discovered",
        aggregate_type="reference",
        aggregate_id="ref-1",
        payload={"reference_id": "ref-1"},
        idempotency_key="reference.discovered:ref-1:1",
        now=now,
    )
    duplicate = await repository.enqueue(
        event_type="reference.discovered",
        aggregate_type="reference",
        aggregate_id="ref-1",
        payload={"reference_id": "ref-1"},
        idempotency_key="reference.discovered:ref-1:1",
        now=now,
    )

    claimed = await repository.claim(now=now, limit=10, lease=timedelta(minutes=5))
    recovered = await repository.claim(
        now=now + timedelta(minutes=6),
        limit=10,
        lease=timedelta(minutes=5),
    )

    assert duplicate.id == first.id
    assert [item.id for item in claimed] == [first.id]
    assert [item.id for item in recovered] == [first.id]
    assert recovered[0].attempts == 2


@pytest.mark.asyncio
async def test_dispatcher_marks_success_and_does_not_redeliver() -> None:
    repository = InMemoryOutboxRepository()
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    await repository.enqueue(
        event_type="reference.discovered",
        aggregate_type="reference",
        aggregate_id="ref-1",
        payload={"reference_id": "ref-1"},
        idempotency_key="event:1",
        now=now,
    )
    received: list[str] = []

    async def handler(payload: dict[str, object]) -> None:
        received.append(str(payload["reference_id"]))

    dispatcher = OutboxDispatcher(
        repository,
        handlers={"reference.discovered": handler},
    )
    assert await dispatcher.dispatch(now=now) == 1
    assert await dispatcher.dispatch(now=now + timedelta(minutes=1)) == 0
    assert received == ["ref-1"]


@pytest.mark.asyncio
async def test_sql_outbox_duplicate_enqueue_and_dispatch_state(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyOutboxRepository(sessions)
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    first = await repository.enqueue(
        event_type="test",
        aggregate_type="test",
        aggregate_id="one",
        payload={"value": 1},
        idempotency_key="same",
        now=now,
    )
    duplicate = await repository.enqueue(
        event_type="test",
        aggregate_type="test",
        aggregate_id="one",
        payload={"value": 2},
        idempotency_key="same",
        now=now,
    )
    claimed = await repository.claim(
        now=now,
        limit=1,
        lease=timedelta(minutes=5),
    )
    await repository.mark_dispatched(claimed[0].id, now=now)

    assert duplicate.id == first.id
    assert claimed[0].attempts == 1
    assert await repository.claim(
        now=now + timedelta(minutes=10),
        limit=1,
        lease=timedelta(minutes=5),
    ) == ()
