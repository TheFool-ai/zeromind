import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from zeromind.subscriptions.domain import normalize_feed_url


@dataclass(frozen=True, slots=True)
class FeedEntry:
    guid: str | None
    url: str | None
    title: str
    summary: str | None
    author: str | None
    published_at: datetime | None
    updated_at: datetime | None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def normalized_entry_url(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    try:
        return normalize_feed_url(cleaned)
    except ValueError:
        return None


def derive_entry_identity(subscription_id: uuid.UUID, entry: FeedEntry) -> str:
    guid = _clean(entry.guid)
    if guid:
        return f"guid:{guid}"
    normalized_url = normalized_entry_url(entry.url)
    if normalized_url:
        return f"url:{normalized_url}"
    fallback = json.dumps(
        {
            "subscription_id": str(subscription_id),
            "title": entry.title.strip(),
            "published_at": _timestamp(entry.published_at),
            "original_link": _clean(entry.url),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"hash:{hashlib.sha256(fallback.encode()).hexdigest()}"


def metadata_fingerprint(entry: FeedEntry) -> str:
    serialized = json.dumps(
        {
            "url": normalized_entry_url(entry.url) or _clean(entry.url),
            "title": entry.title.strip(),
            "summary": _clean(entry.summary),
            "author": _clean(entry.author),
            "published_at": _timestamp(entry.published_at),
            "updated_at": _timestamp(entry.updated_at),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


@dataclass(slots=True)
class ContentReference:
    id: uuid.UUID
    subscription_id: uuid.UUID
    identity_key: str
    original_url: str | None
    current_revision: int
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class ReferenceRevision:
    id: uuid.UUID
    reference_id: uuid.UUID
    number: int
    fingerprint: str
    url: str | None
    title: str
    summary: str | None
    author: str | None
    published_at: datetime | None
    updated_at: datetime | None
    observed_at: datetime

    @classmethod
    def from_entry(
        cls,
        *,
        reference_id: uuid.UUID,
        number: int,
        entry: FeedEntry,
        observed_at: datetime,
    ) -> "ReferenceRevision":
        return cls(
            id=uuid.uuid4(),
            reference_id=reference_id,
            number=number,
            fingerprint=metadata_fingerprint(entry),
            url=normalized_entry_url(entry.url) or _clean(entry.url),
            title=entry.title.strip(),
            summary=_clean(entry.summary),
            author=_clean(entry.author),
            published_at=entry.published_at,
            updated_at=entry.updated_at,
            observed_at=observed_at,
        )


@dataclass(frozen=True, slots=True)
class ReferenceEvent:
    event_type: str
    reference_id: uuid.UUID
    revision: int
    idempotency_key: str

