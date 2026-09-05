from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from zeromind.subscriptions.domain.aggregates.subscription import Subscription
from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress
from zeromind.subscriptions.domain.value_objects.subscription_health import SubscriptionHealth


def test_subscription_disable_and_enable_control_polling() -> None:
    subscription = Subscription.create(
        feed_url="https://example.com/feed.xml",
        title="Example",
        now=datetime(2026, 7, 29, tzinfo=UTC),
    )

    subscription.disable()
    assert subscription.enabled is False
    assert subscription.health is SubscriptionHealth.DISABLED

    subscription.enable(now=datetime(2026, 7, 30, tzinfo=UTC))
    assert subscription.enabled is True
    assert subscription.health is SubscriptionHealth.HEALTHY
    assert subscription.next_poll_at == datetime(2026, 7, 30, tzinfo=UTC)


def test_success_resets_failures_and_persists_conditional_headers() -> None:
    subscription = Subscription.create(
        feed_url="https://example.com/feed.xml",
        title="Example",
        now=datetime(2026, 7, 29, tzinfo=UTC),
    )
    subscription.mark_failure(now=datetime(2026, 7, 29, 1, tzinfo=UTC))

    subscription.mark_success(
        now=datetime(2026, 7, 29, 2, tzinfo=UTC),
        etag='"v2"',
        last_modified="Wed, 29 Jul 2026 02:00:00 GMT",
    )

    assert subscription.consecutive_failures == 0
    assert subscription.health is SubscriptionHealth.HEALTHY
    assert subscription.etag == '"v2"'
    assert subscription.last_modified == "Wed, 29 Jul 2026 02:00:00 GMT"
    assert subscription.last_success_at == datetime(2026, 7, 29, 2, tzinfo=UTC)


def test_subscription_identity_is_its_id_and_entity_is_unhashable():
    first = Subscription.create(feed_url="https://example.com/feed", title="Example")
    assert first == replace(first, title="Changed", enabled=False)
    assert first != Subscription.create(feed_url=first.feed_url, title=first.title)
    assert first != first.id
    with pytest.raises(TypeError):
        hash(first)


def test_create_cleans_title_categories_and_uses_address():
    address = FeedAddress("https://example.com")
    subscription = Subscription.create(
        feed_url=address, title=" Example ", categories=(" News ", "News", "", "Tech")
    )
    assert subscription.feed_url == address
    assert subscription.title == "Example"
    assert subscription.categories == ("News", "Tech")
    assert replace(subscription, feed_url="HTTPS://EXAMPLE.COM:443").feed_url == address
    with pytest.raises(ValueError):
        Subscription.create(feed_url=address, title=" ")


def test_failures_escalate_health_and_cap_backoff():
    now = datetime(2026, 7, 29, tzinfo=UTC)
    subscription = Subscription.create(feed_url="https://example.com", title="Example", now=now)
    for count in range(1, 10):
        subscription.mark_failure(now=now)
        assert subscription.consecutive_failures == count
        assert subscription.health == (
            SubscriptionHealth.DEGRADED if count < 3 else SubscriptionHealth.ERROR
        )
        assert subscription.next_poll_at == now + timedelta(
            minutes=min(30 * 2 ** (count - 1), 1440)
        )
        assert subscription.updated_at == subscription.last_checked_at == now
    subscription.disable(now=now)
    subscription.enable(now=now)
    assert subscription.consecutive_failures == 9
