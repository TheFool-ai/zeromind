from datetime import UTC, datetime

import pytest

from zeromind.subscriptions.domain import (
    Subscription,
    SubscriptionHealth,
    normalize_feed_url,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "HTTPS://Example.COM:443/feed.xml?b=2&a=1#latest",
            "https://example.com/feed.xml?a=1&b=2",
        ),
        ("http://Example.com:80/rss", "http://example.com/rss"),
        ("https://例子.测试/feed", "https://xn--fsqu00a.xn--0zwm56d/feed"),
    ],
)
def test_normalize_feed_url_collapses_equivalent_urls(raw: str, expected: str) -> None:
    assert normalize_feed_url(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "RSSHUB://twitter/user/vista8?mode=full&lang=zh",
            "rsshub://twitter/user/vista8?mode=full&lang=zh",
        ),
        (
            "rsshub://Twitter/User/Vista8/%2Fencoded",
            "rsshub://Twitter/User/Vista8/%2Fencoded",
        ),
    ],
)
def test_normalize_feed_url_preserves_rsshub_route(
    raw: str,
    expected: str,
) -> None:
    assert normalize_feed_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://example.com/feed",
        "https://user:secret@example.com/feed",
        "https:///missing-host",
        "rsshub://twitter",
        "rsshub:///twitter/user/vista8",
        "rsshub://user:secret@twitter/user/vista8",
        "rsshub://twitter:443/user/vista8",
        "rsshub://twitter/user/../vista8",
        "rsshub://twitter/user/%2E%2E/vista8",
        "rsshub://twitter/user/vista8#latest",
    ],
)
def test_normalize_feed_url_rejects_unsafe_or_invalid_urls(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_feed_url(raw)


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
