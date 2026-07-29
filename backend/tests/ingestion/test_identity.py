from datetime import UTC, datetime
from uuid import UUID

from zeromind.ingestion.domain import FeedEntry, derive_entry_identity, metadata_fingerprint

SUBSCRIPTION_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_identity_prefers_guid_over_url() -> None:
    entry = FeedEntry(
        guid="post-42",
        url="HTTPS://EXAMPLE.COM:443/posts/42#comments",
        title="Post",
        summary=None,
        author=None,
        published_at=None,
        updated_at=None,
    )

    assert derive_entry_identity(SUBSCRIPTION_ID, entry) == "guid:post-42"


def test_identity_uses_normalized_url_without_guid() -> None:
    entry = FeedEntry(
        guid=None,
        url="HTTPS://EXAMPLE.COM:443/posts/42#comments",
        title="Post",
        summary=None,
        author=None,
        published_at=None,
        updated_at=None,
    )

    assert derive_entry_identity(SUBSCRIPTION_ID, entry) == "url:https://example.com/posts/42"


def test_identity_fallback_is_deterministic() -> None:
    entry = FeedEntry(
        guid=None,
        url=None,
        title="Undated note",
        summary="Summary",
        author=None,
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=None,
    )

    first = derive_entry_identity(SUBSCRIPTION_ID, entry)
    second = derive_entry_identity(SUBSCRIPTION_ID, entry)

    assert first == second
    assert first.startswith("hash:")


def test_metadata_fingerprint_changes_when_feed_metadata_changes() -> None:
    original = FeedEntry(
        guid="42",
        url="https://example.com/42",
        title="Original",
        summary="First",
        author="Ada",
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=None,
    )
    updated = FeedEntry(
        guid="42",
        url="https://example.com/42",
        title="Corrected",
        summary="First",
        author="Ada",
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=None,
    )

    assert metadata_fingerprint(original) != metadata_fingerprint(updated)

