from datetime import UTC, datetime

from zeromind.subscriptions.domain.aggregates.subscription import Subscription
from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress
from zeromind.subscriptions.domain.value_objects.subscription_health import SubscriptionHealth
from zeromind.subscriptions.infrastructure.persistence.subscription_model import SubscriptionModel


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _required_utc(value: datetime) -> datetime:
    normalized = _as_utc(value)
    if normalized is None:  # pragma: no cover - protected by database constraints
        raise ValueError("required timestamp is missing")
    return normalized


def to_domain(model: SubscriptionModel) -> Subscription:
    return Subscription(
        id=model.id,
        feed_url=FeedAddress.parse(model.feed_url),
        title=model.title,
        site_url=model.site_url,
        categories=tuple(model.categories),
        enabled=model.enabled,
        health=SubscriptionHealth(model.health),
        etag=model.etag,
        last_modified=model.last_modified,
        last_checked_at=_as_utc(model.last_checked_at),
        last_success_at=_as_utc(model.last_success_at),
        consecutive_failures=model.consecutive_failures,
        next_poll_at=_required_utc(model.next_poll_at),
        created_at=_required_utc(model.created_at),
        updated_at=_required_utc(model.updated_at),
    )


def to_model(subscription: Subscription) -> SubscriptionModel:
    return SubscriptionModel(
        id=subscription.id,
        feed_url=subscription.feed_url.value,
        title=subscription.title,
        site_url=subscription.site_url,
        categories=list(subscription.categories),
        enabled=subscription.enabled,
        health=subscription.health.value,
        etag=subscription.etag,
        last_modified=subscription.last_modified,
        last_checked_at=subscription.last_checked_at,
        last_success_at=subscription.last_success_at,
        consecutive_failures=subscription.consecutive_failures,
        next_poll_at=subscription.next_poll_at,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )
