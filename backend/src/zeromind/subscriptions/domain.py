import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class DuplicateSubscriptionError(ValueError):
    pass


class SubscriptionHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ERROR = "error"
    DISABLED = "disabled"


def normalize_feed_url(value: str) -> str:
    raw = value.strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("feed URL must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("feed URL must not contain credentials")

    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as error:
        raise ValueError("feed URL contains an invalid host or port") from error

    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


@dataclass(slots=True)
class Subscription:
    id: uuid.UUID
    feed_url: str
    title: str
    enabled: bool
    health: SubscriptionHealth
    next_poll_at: datetime
    created_at: datetime
    updated_at: datetime
    site_url: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int = 0
    categories: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        feed_url: str,
        title: str,
        now: datetime | None = None,
        site_url: str | None = None,
        categories: tuple[str, ...] = (),
    ) -> "Subscription":
        current = now or datetime.now(UTC)
        normalized = normalize_feed_url(feed_url)
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("subscription title is required")
        return cls(
            id=uuid.uuid4(),
            feed_url=normalized,
            title=clean_title,
            site_url=site_url,
            categories=tuple(
                dict.fromkeys(
                    category.strip() for category in categories if category.strip()
                )
            ),
            enabled=True,
            health=SubscriptionHealth.HEALTHY,
            next_poll_at=current,
            created_at=current,
            updated_at=current,
        )

    def disable(self, *, now: datetime | None = None) -> None:
        self.enabled = False
        self.health = SubscriptionHealth.DISABLED
        self.updated_at = now or datetime.now(UTC)

    def enable(self, *, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        self.enabled = True
        self.health = SubscriptionHealth.HEALTHY
        self.next_poll_at = current
        self.updated_at = current

    def mark_success(
        self,
        *,
        now: datetime,
        etag: str | None,
        last_modified: str | None,
        poll_interval: timedelta = timedelta(minutes=30),
    ) -> None:
        self.last_checked_at = now
        self.last_success_at = now
        self.etag = etag
        self.last_modified = last_modified
        self.consecutive_failures = 0
        self.health = SubscriptionHealth.HEALTHY
        self.next_poll_at = now + poll_interval
        self.updated_at = now

    def mark_failure(self, *, now: datetime) -> None:
        self.last_checked_at = now
        self.consecutive_failures += 1
        self.health = (
            SubscriptionHealth.ERROR
            if self.consecutive_failures >= 3
            else SubscriptionHealth.DEGRADED
        )
        delay_minutes = min(30 * (2 ** (self.consecutive_failures - 1)), 24 * 60)
        self.next_poll_at = now + timedelta(minutes=delay_minutes)
        self.updated_at = now
