from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.subscriptions.domain import DuplicateSubscriptionError, Subscription
from zeromind.subscriptions.models import SubscriptionModel
from zeromind.subscriptions.repository import SqlAlchemySubscriptionRepository


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SubscriptionModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_persists_and_rehydrates_subscription(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemySubscriptionRepository(sessions)
    subscription = Subscription.create(
        feed_url="https://example.com/feed.xml",
        title="Example",
    )

    await repository.add(subscription)
    loaded = await repository.get(subscription.id)

    assert loaded == subscription


@pytest.mark.asyncio
async def test_repository_converts_unique_violation_to_domain_error(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemySubscriptionRepository(sessions)
    first = Subscription.create(feed_url="https://example.com/feed", title="First")
    duplicate = Subscription.create(feed_url="https://example.com/feed", title="Second")
    await repository.add(first)

    with pytest.raises(DuplicateSubscriptionError):
        await repository.add(duplicate)


@pytest.mark.asyncio
async def test_repository_atomically_leases_due_subscriptions(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemySubscriptionRepository(sessions)
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    subscription = Subscription.create(
        feed_url="https://example.com/feed",
        title="Due",
        now=now,
    )
    await repository.add(subscription)

    first = await repository.claim_due(
        now=now,
        limit=10,
        lease=timedelta(minutes=30),
    )
    second = await repository.claim_due(
        now=now,
        limit=10,
        lease=timedelta(minutes=30),
    )

    assert [item.id for item in first] == [subscription.id]
    assert second == ()
