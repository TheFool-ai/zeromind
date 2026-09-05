from dataclasses import FrozenInstanceError

import pytest

from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress


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
    assert FeedAddress.parse(raw).value == expected


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
    assert FeedAddress.parse(raw).value == expected


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
        FeedAddress.parse(raw)


def test_address_direct_construction_is_normalized_immutable_and_hashable():
    address = FeedAddress(" HTTPS://Example.com:443 ")
    assert address == FeedAddress.parse("https://example.com/")
    assert len({address, FeedAddress("https://example.com/")}) == 1
    assert address.is_rsshub is False
    assert FeedAddress("RSSHUB://Twitter/User/Example").is_rsshub is True
    with pytest.raises(FrozenInstanceError):
        address.value = "https://other.example/"
    with pytest.raises(ValueError):
        FeedAddress("ftp://example.com/feed")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://[2001:db8::1]/feed", "https://[2001:db8::1]/feed"),
        ("https://[2001:db8::1]:443/feed", "https://[2001:db8::1]/feed"),
        ("https://[2001:db8::1]:8443/feed", "https://[2001:db8::1]:8443/feed"),
        ("http://[2001:db8::1]:80/feed", "http://[2001:db8::1]/feed"),
    ],
)
def test_ipv6_address_normalization_is_idempotent(raw: str, expected: str) -> None:
    address = FeedAddress.parse(raw)
    assert address.value == expected
    assert FeedAddress.parse(address.value) == address
