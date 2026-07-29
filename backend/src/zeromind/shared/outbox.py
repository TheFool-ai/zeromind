import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.shared.models import OutboxEventModel


@dataclass(slots=True)
class OutboxEvent:
    id: uuid.UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, object]
    idempotency_key: str
    status: str
    attempts: int
    occurred_at: datetime
    available_at: datetime
    lease_until: datetime | None = None
    dispatched_at: datetime | None = None
    last_error: str | None = None


class OutboxRepository(Protocol):
    async def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OutboxEvent: ...

    async def claim(
        self,
        *,
        now: datetime,
        limit: int,
        lease: timedelta,
    ) -> tuple[OutboxEvent, ...]: ...

    async def mark_dispatched(self, event_id: uuid.UUID, *, now: datetime) -> None: ...

    async def mark_failed(
        self,
        event_id: uuid.UUID,
        *,
        error: str,
        retry_at: datetime,
    ) -> None: ...


class InMemoryOutboxRepository:
    def __init__(self) -> None:
        self._events: dict[uuid.UUID, OutboxEvent] = {}
        self._keys: dict[str, uuid.UUID] = {}

    async def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OutboxEvent:
        existing_id = self._keys.get(idempotency_key)
        if existing_id:
            return self._events[existing_id]
        current = now or datetime.now(UTC)
        event = OutboxEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=idempotency_key,
            status="pending",
            attempts=0,
            occurred_at=current,
            available_at=current,
        )
        self._events[event.id] = event
        self._keys[idempotency_key] = event.id
        return event

    async def claim(
        self,
        *,
        now: datetime,
        limit: int,
        lease: timedelta,
    ) -> tuple[OutboxEvent, ...]:
        candidates = [
            event
            for event in self._events.values()
            if event.dispatched_at is None
            and event.available_at <= now
            and (event.lease_until is None or event.lease_until <= now)
        ][:limit]
        for event in candidates:
            event.status = "processing"
            event.attempts += 1
            event.lease_until = now + lease
        return tuple(candidates)

    async def mark_dispatched(self, event_id: uuid.UUID, *, now: datetime) -> None:
        event = self._events[event_id]
        event.status = "dispatched"
        event.dispatched_at = now
        event.lease_until = None
        event.last_error = None

    async def mark_failed(
        self,
        event_id: uuid.UUID,
        *,
        error: str,
        retry_at: datetime,
    ) -> None:
        event = self._events[event_id]
        event.status = "pending"
        event.available_at = retry_at
        event.lease_until = None
        event.last_error = error[:4000]


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _domain(model: OutboxEventModel) -> OutboxEvent:
    occurred_at = _as_utc(model.occurred_at)
    available_at = _as_utc(model.available_at)
    if occurred_at is None or available_at is None:
        raise ValueError("outbox timestamps are required")
    return OutboxEvent(
        id=model.id,
        event_type=model.event_type,
        aggregate_type=model.aggregate_type,
        aggregate_id=model.aggregate_id,
        payload=model.payload,
        idempotency_key=model.idempotency_key,
        status=model.status,
        attempts=model.attempts,
        occurred_at=occurred_at,
        available_at=available_at,
        lease_until=_as_utc(model.lease_until),
        dispatched_at=_as_utc(model.dispatched_at),
        last_error=model.last_error,
    )


class SqlAlchemyOutboxRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OutboxEvent:
        current = now or datetime.now(UTC)
        event = OutboxEventModel(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=idempotency_key,
            status="pending",
            attempts=0,
            occurred_at=current,
            available_at=current,
        )
        async with self._sessions() as session, session.begin():
            session.add(event)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                async with self._sessions() as lookup:
                    existing = await lookup.scalar(
                        select(OutboxEventModel).where(
                            OutboxEventModel.idempotency_key == idempotency_key
                        )
                    )
                    if existing is None:
                        raise
                    return _domain(existing)
            return _domain(event)

    async def claim(
        self,
        *,
        now: datetime,
        limit: int,
        lease: timedelta,
    ) -> tuple[OutboxEvent, ...]:
        async with self._sessions() as session, session.begin():
            models = await session.scalars(
                select(OutboxEventModel)
                .where(
                    OutboxEventModel.dispatched_at.is_(None),
                    OutboxEventModel.available_at <= now,
                    or_(
                        OutboxEventModel.lease_until.is_(None),
                        OutboxEventModel.lease_until <= now,
                    ),
                )
                .order_by(OutboxEventModel.occurred_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            claimed = tuple(models)
            for model in claimed:
                model.status = "processing"
                model.attempts += 1
                model.lease_until = now + lease
            await session.flush()
            return tuple(_domain(model) for model in claimed)

    async def mark_dispatched(self, event_id: uuid.UUID, *, now: datetime) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(OutboxEventModel, event_id)
            if model is None:
                raise KeyError(event_id)
            model.status = "dispatched"
            model.dispatched_at = now
            model.lease_until = None
            model.last_error = None

    async def mark_failed(
        self,
        event_id: uuid.UUID,
        *,
        error: str,
        retry_at: datetime,
    ) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(OutboxEventModel, event_id)
            if model is None:
                raise KeyError(event_id)
            model.status = "pending"
            model.available_at = retry_at
            model.lease_until = None
            model.last_error = error[:4000]


EventHandler = Callable[[dict[str, object]], Awaitable[None]]


class OutboxDispatcher:
    def __init__(
        self,
        repository: OutboxRepository,
        *,
        handlers: dict[str, EventHandler],
        lease: timedelta = timedelta(minutes=5),
    ) -> None:
        self._repository = repository
        self._handlers = handlers
        self._lease = lease

    async def dispatch(self, *, now: datetime | None = None, limit: int = 100) -> int:
        current = now or datetime.now(UTC)
        events = await self._repository.claim(
            now=current,
            limit=limit,
            lease=self._lease,
        )
        completed = 0
        for event in events:
            handler = self._handlers.get(event.event_type)
            try:
                if handler is None:
                    raise ValueError(f"no outbox handler for {event.event_type}")
                await handler(event.payload)
            except Exception as error:
                delay = timedelta(seconds=min(2 ** event.attempts, 300))
                await self._repository.mark_failed(
                    event.id,
                    error=str(error),
                    retry_at=current + delay,
                )
            else:
                await self._repository.mark_dispatched(event.id, now=current)
                completed += 1
        return completed

