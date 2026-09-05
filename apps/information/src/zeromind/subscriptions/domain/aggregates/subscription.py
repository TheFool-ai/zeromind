import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress
from zeromind.subscriptions.domain.value_objects.subscription_health import SubscriptionHealth


@dataclass(slots=True, eq=False)
class Subscription:
    id: uuid.UUID
    feed_url: FeedAddress
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

    def __post_init__(self) -> None:
        if isinstance(self.feed_url, str):
            self.feed_url = FeedAddress.parse(self.feed_url)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Subscription):
            return NotImplemented
        return self.id == other.id

    @classmethod
    def create(
        cls,
        *,
        feed_url: str | FeedAddress,
        title: str,
        now: datetime | None = None,
        site_url: str | None = None,
        categories: tuple[str, ...] = (),
    ) -> "Subscription":
        current = now or datetime.now(UTC)
        normalized = feed_url if isinstance(feed_url, FeedAddress) else FeedAddress.parse(feed_url)
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("subscription title is required")
        return cls(
            id=uuid.uuid4(),
            feed_url=normalized,
            title=clean_title,
            site_url=site_url,
            categories=tuple(
                dict.fromkeys(category.strip() for category in categories if category.strip())
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
