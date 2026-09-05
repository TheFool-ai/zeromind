import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.subscriptions.domain.aggregates.subscription import Subscription
from zeromind.subscriptions.domain.exceptions.duplicate_subscription_error import (
    DuplicateSubscriptionError,
)
from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress
from zeromind.subscriptions.infrastructure.persistence.subscription_mapper import (
    to_domain,
    to_model,
)
from zeromind.subscriptions.infrastructure.persistence.subscription_model import SubscriptionModel


class SqlAlchemySubscriptionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, subscription: Subscription) -> None:
        async with self._sessions() as session, session.begin():
            session.add(to_model(subscription))
            try:
                await session.flush()
            except IntegrityError as error:
                raise DuplicateSubscriptionError(subscription.feed_url.value) from error

    async def get(self, subscription_id: uuid.UUID) -> Subscription | None:
        async with self._sessions() as session:
            model = await session.get(SubscriptionModel, subscription_id)
            return to_domain(model) if model else None

    async def find_by_url(self, feed_url: FeedAddress) -> Subscription | None:
        normalized = feed_url.value
        async with self._sessions() as session:
            model = await session.scalar(
                select(SubscriptionModel).where(SubscriptionModel.feed_url == normalized)
            )
            return to_domain(model) if model else None

    async def list(self) -> Sequence[Subscription]:
        async with self._sessions() as session:
            result = await session.scalars(
                select(SubscriptionModel).order_by(SubscriptionModel.created_at)
            )
            return tuple(to_domain(model) for model in result)

    async def save(self, subscription: Subscription) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(SubscriptionModel, subscription.id)
            if model is None:
                raise KeyError(subscription.id)
            replacement = to_model(subscription)
            for column in SubscriptionModel.__table__.columns:
                if column.name != "id":
                    setattr(model, column.name, getattr(replacement, column.name))

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease: timedelta,
    ) -> Sequence[Subscription]:
        async with self._sessions() as session, session.begin():
            result = await session.scalars(
                select(SubscriptionModel)
                .where(
                    SubscriptionModel.enabled.is_(True),
                    SubscriptionModel.next_poll_at <= now,
                )
                .order_by(SubscriptionModel.next_poll_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            models = tuple(result)
            for model in models:
                model.next_poll_at = now + lease
                model.updated_at = now
            await session.flush()
            return tuple(to_domain(model) for model in models)
