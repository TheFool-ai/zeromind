import uuid
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timedelta

from zeromind.subscriptions.domain.aggregates.subscription import Subscription
from zeromind.subscriptions.domain.exceptions.duplicate_subscription_error import (
    DuplicateSubscriptionError,
)
from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress


class InMemorySubscriptionRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Subscription] = {}
        self._by_url: dict[FeedAddress, uuid.UUID] = {}

    async def add(self, subscription: Subscription) -> None:
        if subscription.feed_url in self._by_url:
            raise DuplicateSubscriptionError(subscription.feed_url.value)
        self._items[subscription.id] = deepcopy(subscription)
        self._by_url[subscription.feed_url] = subscription.id

    async def get(self, subscription_id: uuid.UUID) -> Subscription | None:
        return deepcopy(self._items.get(subscription_id))

    async def find_by_url(self, feed_url: FeedAddress) -> Subscription | None:
        identifier = self._by_url.get(feed_url)
        return deepcopy(self._items.get(identifier)) if identifier else None

    async def list(self) -> Sequence[Subscription]:
        return deepcopy(tuple(sorted(self._items.values(), key=lambda item: item.created_at)))

    async def save(self, subscription: Subscription) -> None:
        if subscription.id not in self._items:
            raise KeyError(subscription.id)
        self._items[subscription.id] = deepcopy(subscription)

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease: timedelta,
    ) -> Sequence[Subscription]:
        due = tuple(
            item
            for item in sorted(
                self._items.values(),
                key=lambda value: value.next_poll_at,
            )
            if item.enabled and item.next_poll_at <= now
        )[:limit]
        for item in due:
            item.next_poll_at = now + lease
            item.updated_at = now
        return deepcopy(due)
