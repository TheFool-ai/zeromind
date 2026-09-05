import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol

from zeromind.subscriptions.domain.aggregates.subscription import Subscription
from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress


class SubscriptionRepository(Protocol):
    async def add(self, subscription: Subscription) -> None: ...

    async def get(self, subscription_id: uuid.UUID) -> Subscription | None: ...

    async def find_by_url(self, feed_url: FeedAddress) -> Subscription | None: ...

    async def list(self) -> Sequence[Subscription]: ...

    async def save(self, subscription: Subscription) -> None: ...

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease: timedelta,
    ) -> Sequence[Subscription]: ...
