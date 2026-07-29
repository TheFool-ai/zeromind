import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.subscriptions.domain import (
    DuplicateSubscriptionError,
    Subscription,
    SubscriptionHealth,
    normalize_feed_url,
)
from zeromind.subscriptions.models import SubscriptionModel


class SubscriptionRepository(Protocol):
    async def add(self, subscription: Subscription) -> None: ...

    async def get(self, subscription_id: uuid.UUID) -> Subscription | None: ...

    async def find_by_url(self, feed_url: str) -> Subscription | None: ...

    async def list(self) -> Sequence[Subscription]: ...

    async def save(self, subscription: Subscription) -> None: ...


class InMemorySubscriptionRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Subscription] = {}
        self._by_url: dict[str, uuid.UUID] = {}

    async def add(self, subscription: Subscription) -> None:
        if subscription.feed_url in self._by_url:
            raise DuplicateSubscriptionError(subscription.feed_url)
        self._items[subscription.id] = subscription
        self._by_url[subscription.feed_url] = subscription.id

    async def get(self, subscription_id: uuid.UUID) -> Subscription | None:
        return self._items.get(subscription_id)

    async def find_by_url(self, feed_url: str) -> Subscription | None:
        identifier = self._by_url.get(normalize_feed_url(feed_url))
        return self._items.get(identifier) if identifier else None

    async def list(self) -> Sequence[Subscription]:
        return tuple(sorted(self._items.values(), key=lambda item: item.created_at))

    async def save(self, subscription: Subscription) -> None:
        if subscription.id not in self._items:
            raise KeyError(subscription.id)
        self._items[subscription.id] = subscription


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _required_utc(value: datetime) -> datetime:
    normalized = _as_utc(value)
    if normalized is None:  # pragma: no cover - protected by database constraints
        raise ValueError("required timestamp is missing")
    return normalized


def _to_domain(model: SubscriptionModel) -> Subscription:
    return Subscription(
        id=model.id,
        feed_url=model.feed_url,
        title=model.title,
        site_url=model.site_url,
        categories=tuple(model.categories),
        enabled=model.enabled,
        health=SubscriptionHealth(model.health),
        etag=model.etag,
        last_modified=model.last_modified,
        last_checked_at=_as_utc(model.last_checked_at),
        last_success_at=_as_utc(model.last_success_at),
        consecutive_failures=model.consecutive_failures,
        next_poll_at=_required_utc(model.next_poll_at),
        created_at=_required_utc(model.created_at),
        updated_at=_required_utc(model.updated_at),
    )


def _to_model(subscription: Subscription) -> SubscriptionModel:
    return SubscriptionModel(
        id=subscription.id,
        feed_url=subscription.feed_url,
        title=subscription.title,
        site_url=subscription.site_url,
        categories=list(subscription.categories),
        enabled=subscription.enabled,
        health=subscription.health.value,
        etag=subscription.etag,
        last_modified=subscription.last_modified,
        last_checked_at=subscription.last_checked_at,
        last_success_at=subscription.last_success_at,
        consecutive_failures=subscription.consecutive_failures,
        next_poll_at=subscription.next_poll_at,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


class SqlAlchemySubscriptionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, subscription: Subscription) -> None:
        async with self._sessions() as session, session.begin():
            session.add(_to_model(subscription))
            try:
                await session.flush()
            except IntegrityError as error:
                raise DuplicateSubscriptionError(subscription.feed_url) from error

    async def get(self, subscription_id: uuid.UUID) -> Subscription | None:
        async with self._sessions() as session:
            model = await session.get(SubscriptionModel, subscription_id)
            return _to_domain(model) if model else None

    async def find_by_url(self, feed_url: str) -> Subscription | None:
        normalized = normalize_feed_url(feed_url)
        async with self._sessions() as session:
            model = await session.scalar(
                select(SubscriptionModel).where(SubscriptionModel.feed_url == normalized)
            )
            return _to_domain(model) if model else None

    async def list(self) -> Sequence[Subscription]:
        async with self._sessions() as session:
            result = await session.scalars(
                select(SubscriptionModel).order_by(SubscriptionModel.created_at)
            )
            return tuple(_to_domain(model) for model in result)

    async def save(self, subscription: Subscription) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(SubscriptionModel, subscription.id)
            if model is None:
                raise KeyError(subscription.id)
            replacement = _to_model(subscription)
            for column in SubscriptionModel.__table__.columns:
                if column.name != "id":
                    setattr(model, column.name, getattr(replacement, column.name))
