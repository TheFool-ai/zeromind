import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

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


AnalysisStatus = Literal[
    "pending",
    "queued",
    "screening",
    "resolving",
    "analyzing",
    "classifying",
    "scoring",
    "reviewing",
    "finalizing",
    "initial_rejected",
    "fine_rejected",
    "completed",
    "failed",
]
ANALYSIS_STATUSES = frozenset(
    {
        "pending",
        "queued",
        "screening",
        "resolving",
        "analyzing",
        "classifying",
        "scoring",
        "reviewing",
        "finalizing",
        "initial_rejected",
        "fine_rejected",
        "completed",
        "failed",
    }
)
PROCESSING_ANALYSIS_STATUSES = frozenset(
    {
        "queued",
        "screening",
        "resolving",
        "analyzing",
        "classifying",
        "scoring",
        "reviewing",
        "finalizing",
    }
)
TERMINAL_ANALYSIS_STATUSES = frozenset(
    {"initial_rejected", "fine_rejected", "completed", "failed"}
)


@dataclass(slots=True)
class ContentReference:
    id: uuid.UUID
    subscription_id: uuid.UUID
    identity_key: str
    original_url: str | None
    current_revision: int
    first_seen_at: datetime
    last_seen_at: datetime
    analysis_status: AnalysisStatus = "pending"
    analysis_status_revision: int = 1
    analysis_workflow_run_id: uuid.UUID | None = None
    analysis_error_code: str | None = None
    analysis_error_message: str | None = None
    analysis_status_updated_at: datetime = field(
        default_factory=lambda: datetime.min.replace(tzinfo=UTC)
    )
    analysis_started_at: datetime | None = None
    analysis_completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.analysis_status_updated_at == datetime.min.replace(tzinfo=UTC):
            self.analysis_status_updated_at = self.first_seen_at

    @classmethod
    def create(
        cls,
        *,
        subscription_id: uuid.UUID,
        identity_key: str,
        original_url: str | None,
        now: datetime,
        identifier: uuid.UUID | None = None,
    ) -> "ContentReference":
        return cls(
            id=identifier or uuid.uuid4(),
            subscription_id=subscription_id,
            identity_key=identity_key,
            original_url=original_url,
            current_revision=1,
            first_seen_at=now,
            last_seen_at=now,
            analysis_status="pending",
            analysis_status_revision=1,
            analysis_status_updated_at=now,
        )

    def reset_analysis(self, *, revision: int, now: datetime) -> None:
        if revision != self.current_revision or revision < 1:
            raise ValueError("analysis reset revision must be current")
        self.analysis_status = "pending"
        self.analysis_status_revision = revision
        self.analysis_workflow_run_id = None
        self.analysis_error_code = None
        self.analysis_error_message = None
        self.analysis_status_updated_at = now
        self.analysis_started_at = None
        self.analysis_completed_at = None


@dataclass(frozen=True, slots=True)
class ReferenceSummary:
    reference: ContentReference
    published_at: datetime | None


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
