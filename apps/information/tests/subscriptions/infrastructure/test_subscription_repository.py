from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.subscriptions.domain.aggregates.subscription import Subscription
from zeromind.subscriptions.domain.exceptions.duplicate_subscription_error import (
    DuplicateSubscriptionError,
)
from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress
from zeromind.subscriptions.infrastructure.persistence.in_memory_subscription_repository import (
    InMemorySubscriptionRepository,
)
from zeromind.subscriptions.infrastructure.persistence.sqlalchemy_subscription_repository import (
    SqlAlchemySubscriptionRepository,
)
from zeromind.subscriptions.infrastructure.persistence.subscription_model import SubscriptionModel


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

    assert loaded is not None
    assert asdict(loaded) == asdict(subscription)


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


@pytest_asyncio.fixture(params=["memory", "sql"])
async def repository(request, sessions):
    return (
        InMemorySubscriptionRepository()
        if request.param == "memory"
        else SqlAlchemySubscriptionRepository(sessions)
    )


@pytest.mark.asyncio
async def test_full_state_roundtrip_and_detached_reads_writes(repository):
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    subscription = Subscription.create(
        feed_url="RSSHUB://Twitter/User/example?z=2&a=1",
        title="Example",
        now=now,
        site_url="https://example.com",
        categories=("News", "Tech"),
    )
    subscription.mark_success(now=now, etag='"v2"', last_modified="last modified")
    subscription.mark_failure(now=now + timedelta(minutes=30))
    subscription.disable(now=now + timedelta(minutes=31))
    expected = asdict(subscription)
    await repository.add(subscription)
    subscription.title = "Unsaved change"
    loaded = await repository.get(subscription.id)
    assert asdict(loaded) == expected
    loaded.title = "Another unsaved change"
    found = await repository.find_by_url(FeedAddress.parse(expected["feed_url"]["value"]))
    assert asdict(found) == expected
    found.title = "Unsaved lookup change"
    listed = await repository.list()
    assert asdict(listed[0]) == expected
    listed[0].title = "Unsaved list change"
    assert asdict(await repository.get(subscription.id)) == expected
    await repository.save(loaded)
    saved = asdict(loaded)
    loaded.title = "Unsaved after save"
    assert asdict(await repository.get(subscription.id)) == saved


@pytest.mark.asyncio
async def test_claim_filters_sorts_limits_and_returns_detached_leases(repository):
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    items = [
        Subscription.create(
            feed_url=f"https://example.com/{i}", title=str(i), now=now + timedelta(minutes=i)
        )
        for i in range(4)
    ]
    items[0].disable(now=now)
    for item in reversed(items):
        await repository.add(item)
    claim_time = now + timedelta(minutes=2)
    claimed = await repository.claim_due(now=claim_time, limit=1, lease=timedelta(minutes=10))
    assert [item.id for item in claimed] == [items[1].id]
    assert claimed[0].next_poll_at == claim_time + timedelta(minutes=10)
    assert claimed[0].updated_at == claim_time
    claimed[0].next_poll_at = now
    second = await repository.claim_due(now=claim_time, limit=10, lease=timedelta(minutes=10))
    assert [item.id for item in second] == [items[2].id]
    assert await repository.claim_due(now=claim_time, limit=10, lease=timedelta(minutes=10)) == ()


@pytest.mark.asyncio
async def test_repository_missing_and_duplicate_behavior(repository):
    subscription = Subscription.create(feed_url="https://example.com", title="Example")
    assert await repository.get(subscription.id) is None
    assert await repository.find_by_url(subscription.feed_url) is None
    with pytest.raises(KeyError):
        await repository.save(subscription)
    await repository.add(subscription)
    with pytest.raises(DuplicateSubscriptionError):
        await repository.add(
            Subscription.create(feed_url="HTTPS://EXAMPLE.COM:443/", title="Duplicate")
        )


@pytest.mark.asyncio
async def test_ipv6_subscription_survives_database_rehydration(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemySubscriptionRepository(sessions)
    created = Subscription.create(feed_url="https://[2001:db8::1]/feed", title="IPv6 feed")
    await repository.add(created)
    loaded = await repository.get(created.id)
    assert loaded is not None
    assert loaded.feed_url.value == "https://[2001:db8::1]/feed"
    assert [item.id for item in await repository.list()] == [created.id]
    due = await repository.claim_due(
        now=created.next_poll_at,
        limit=1,
        lease=timedelta(minutes=30),
    )
    assert due[0].feed_url == created.feed_url
