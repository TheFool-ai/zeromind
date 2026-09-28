"""验证领域规则，使用固定时间，避免网络和数据库依赖。"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from subscription_service.domain.aggregates.subscription import Subscription
from subscription_service.domain.aggregates.subscription_item import SubscriptionItem
from subscription_service.domain.entities.item_revision import ItemRevision
from subscription_service.domain.value_objects.feed_address import FeedAddress
from subscription_service.domain.value_objects.fetch_checkpoint import FetchCheckpoint
from subscription_service.domain.value_objects.item_identity import ItemIdentity
from subscription_service.domain.value_objects.item_metadata import ItemMetadata

NOW = datetime(2026, 9, 28, 10, tzinfo=UTC)


def source():
    return Subscription.create(
        name=" 新闻 ",
        feed_address=FeedAddress("https://example.com"),
        categories=(" 技术 ", "技术", ""),
        now=NOW,
    )


def metadata(**changes):
    return replace(
        ItemMetadata("  标题 ", "HTTPS://EXAMPLE.com:443/a#part", " 摘要 ", " ", NOW, None),
        **changes,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" HTTPS://ExAmple.com:443?b=2&a=1#x ", "https://example.com/?a=1&b=2"),
        ("http://[::1]:80/feed", "http://[::1]/feed"),
        ("https://例子.测试/feed", "https://xn--fsqu00a.xn--0zwm56d/feed"),
        ("RSSHUB://Twitter/User/X?b=2&a=1", "rsshub://Twitter/User/X?b=2&a=1"),
    ],
)
def test_address_normalization_is_idempotent(raw, expected):
    assert FeedAddress.parse(raw).value == expected
    assert FeedAddress(expected).value == expected
    assert FeedAddress(expected).is_rsshub == expected.startswith("rsshub://")


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://example.com/feed",
        "https://user:pw@example.com/feed",
        "http://example.com:99999",
        "https://exa mple.com/feed",
        "https://example.com/\nfeed",
        "rsshub://twitter",
        "rsshub://twitter/user/../x",
        "rsshub://twitter/user/%2e%2e/x",
        "rsshub://twitter:80/user/x",
        "rsshub://twitter/user/x#part",
        "rsshub://twitter/user/x?%6bey=secret",
        "rsshub://twitter/user/x?CODE=secret",
        "rsshub://twitter/user/%2f..%2fx",
        "https://example.com\\@evil.com/feed",
    ],
)
def test_invalid_addresses_rejected_even_by_constructor(raw):
    with pytest.raises(ValueError):
        FeedAddress(raw)


def test_subscription_idempotent_changes_and_checkpoint_separation():
    sub = source()
    assert (sub.name, sub.categories, sub.configuration_version, sub.address_version) == (
        "新闻",
        ("技术",),
        1,
        1,
    )
    sub.enable(now=NOW)
    sub.update_details(name="新闻", categories=("技术",), now=NOW)
    assert sub.configuration_version == 1
    sub.disable(now=NOW + timedelta(minutes=1))
    sub.disable(now=NOW + timedelta(minutes=2))
    assert sub.configuration_version == 2
    modified_at = sub.updated_at
    sub.record_fetch_success(etag="v1", last_modified=None, completed_at=NOW + timedelta(minutes=3))
    assert sub.enabled is False
    assert sub.updated_at == modified_at
    assert sub.configuration_version == 2
    assert sub.fetch_checkpoint.etag == "v1"
    sub.update_details(name="新名字", categories=(), now=NOW + timedelta(minutes=4))
    assert sub.address_version == 1
    assert sub.fetch_checkpoint.etag == "v1"
    sub.change_address(
        feed_address=FeedAddress("https://example.com/new"), now=NOW + timedelta(minutes=5)
    )
    assert sub.fetch_checkpoint == FetchCheckpoint()
    assert sub.address_version == 2
    sub.change_address(
        feed_address=FeedAddress("https://example.com/"), now=NOW + timedelta(minutes=6)
    )
    assert sub.address_version == 3  # 地址改走又改回，也不能接受旧响应。


def test_bad_name_does_not_partially_update_subscription():
    sub = source()
    with pytest.raises(ValueError):
        sub.update_details(name=" ", categories=("other",), now=NOW)
    assert sub.name == "新闻" and sub.categories == ("技术",)


def test_naive_time_and_backwards_checkpoint_rejected():
    with pytest.raises(ValueError):
        Subscription.create(
            name="a", feed_address=FeedAddress("https://a.test"), now=datetime(2026, 1, 1)
        )
    sub = source()
    sub.record_fetch_success(etag="a", last_modified=None, completed_at=NOW)
    with pytest.raises(ValueError):
        sub.record_fetch_success(
            etag="b", last_modified=None, completed_at=NOW - timedelta(seconds=1)
        )
    assert sub.fetch_checkpoint.etag == "a"


def test_metadata_equivalent_representations_have_same_fingerprint():
    original = metadata()
    clean = ItemMetadata(
        "标题",
        "https://example.com/a",
        "摘要",
        None,
        NOW.astimezone(timezone(timedelta(hours=8))),
        None,
    )
    assert original.normalized() == clean.normalized()
    assert original.has_same_content_as(clean)
    assert original.fingerprint() == clean.fingerprint()
    assert not original.has_same_content_as(replace(clean, summary="不同内容"))
    assert original.title == "  标题 "  # 规范化不修改原值对象。


def test_observation_creates_revision_only_for_changed_metadata():
    item, first = SubscriptionItem.discover(
        subscription_id=uuid4(),
        identity=ItemIdentity("guid", "one"),
        metadata=metadata(),
        observed_at=NOW,
    )
    later = NOW + timedelta(minutes=10)
    assert (
        item.observe(current_revision=first, metadata=metadata().normalized(), observed_at=later)
        is None
    )
    assert item.last_seen_at == later and item.current_revision == 1
    second = item.observe(
        current_revision=first, metadata=metadata(title="新标题"), observed_at=later
    )
    assert second.revision_number == 2 and first.revision_number == 1
    assert first.metadata.title == "标题" and second.metadata.title == "新标题"


def test_stale_or_foreign_revision_cannot_mutate_item():
    item, first = SubscriptionItem.discover(
        subscription_id=uuid4(),
        identity=ItemIdentity("guid", "one"),
        metadata=metadata(),
        observed_at=NOW,
    )
    with pytest.raises(ValueError):
        item.observe(
            current_revision=replace(first, item_id=uuid4()), metadata=metadata(), observed_at=NOW
        )
    second = item.observe(current_revision=first, metadata=metadata(title="new"), observed_at=NOW)
    with pytest.raises(ValueError):
        item.observe(current_revision=first, metadata=metadata(), observed_at=NOW)
    with pytest.raises(ValueError):
        item.observe(
            current_revision=second, metadata=metadata(), observed_at=NOW - timedelta(seconds=1)
        )
    assert item.current_revision == 2 and item.last_seen_at == NOW


def test_identity_and_revision_validation():
    for kind, value in [("bad", "x"), ("guid", " ")]:
        with pytest.raises(ValueError):
            ItemIdentity(kind, value)
    with pytest.raises(ValueError):
        ItemRevision.create(
            item_id=uuid4(), revision_number=0, metadata=metadata(), observed_at=NOW
        )


def test_entities_compare_by_identity():
    sub = source()
    assert sub == replace(sub, name="changed")
    with pytest.raises(TypeError):
        hash(sub)
    item, rev = SubscriptionItem.discover(
        subscription_id=sub.id,
        identity=ItemIdentity("guid", "one"),
        metadata=metadata(),
        observed_at=NOW,
    )
    assert item == replace(item, current_revision=2)
    assert rev == replace(rev, metadata=metadata(title="other"))


def test_old_address_checkpoint_rejected_but_rename_does_not_invalidate_request():
    sub = source()
    request_version = sub.address_version
    sub.update_details(name="改名", categories=(), now=NOW)
    sub.record_fetch_success(
        etag="new", last_modified=None, completed_at=NOW, expected_address_version=request_version
    )
    sub.change_address(feed_address=FeedAddress("https://other.example/feed"), now=NOW)
    sub.change_address(feed_address=FeedAddress("https://example.com"), now=NOW)
    with pytest.raises(ValueError):
        sub.record_fetch_success(
            etag="stale",
            last_modified=None,
            completed_at=NOW,
            expected_address_version=request_version,
        )
    assert sub.fetch_checkpoint == FetchCheckpoint()


def test_config_clock_cannot_regress_or_partially_change_state():
    sub = source()
    with pytest.raises(ValueError):
        sub.disable(now=NOW - timedelta(seconds=1))
    assert sub.enabled and sub.configuration_version == 1


def test_invalid_metadata_cannot_advance_revision():
    sub = source()
    item, first = SubscriptionItem.discover(
        subscription_id=sub.id,
        identity=ItemIdentity("guid", "one"),
        metadata=metadata(),
        observed_at=NOW,
    )
    with pytest.raises(ValueError):
        item.observe(
            current_revision=first,
            metadata=metadata(original_url="javascript:evil"),
            observed_at=NOW + timedelta(seconds=1),
        )
    assert item.current_revision == 1 and item.last_seen_at == NOW
