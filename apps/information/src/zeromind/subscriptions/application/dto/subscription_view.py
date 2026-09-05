import uuid
from dataclasses import dataclass
from datetime import datetime

from zeromind.subscriptions.domain.aggregates.subscription import Subscription


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    """Detached subscription snapshot for HTTP and cross-context consumers."""

    id: uuid.UUID
    feed_url: str
    title: str
    enabled: bool
    health: str
    next_poll_at: datetime
    created_at: datetime
    updated_at: datetime
    site_url: str | None
    etag: str | None
    last_modified: str | None
    last_checked_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int
    categories: tuple[str, ...]

    @classmethod
    def from_domain(cls, subscription: Subscription) -> "SubscriptionView":
        return cls(
            id=subscription.id,
            feed_url=subscription.feed_url.value,
            title=subscription.title,
            enabled=subscription.enabled,
            health=subscription.health.value,
            next_poll_at=subscription.next_poll_at,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
            site_url=subscription.site_url,
            etag=subscription.etag,
            last_modified=subscription.last_modified,
            last_checked_at=subscription.last_checked_at,
            last_success_at=subscription.last_success_at,
            consecutive_failures=subscription.consecutive_failures,
            categories=subscription.categories,
        )
