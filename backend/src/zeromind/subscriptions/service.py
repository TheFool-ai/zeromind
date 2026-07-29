import uuid
from dataclasses import dataclass

from zeromind.subscriptions.domain import (
    DuplicateSubscriptionError,
    Subscription,
    normalize_feed_url,
)
from zeromind.subscriptions.opml import OpmlEntry
from zeromind.subscriptions.repository import SubscriptionRepository


@dataclass(frozen=True, slots=True)
class ImportItemResult:
    feed_url: str
    status: str
    subscription_id: str | None


@dataclass(frozen=True, slots=True)
class ImportResult:
    created: int
    duplicates: int
    items: tuple[ImportItemResult, ...]


class SubscriptionService:
    def __init__(self, repository: SubscriptionRepository) -> None:
        self._repository = repository

    async def create(
        self,
        *,
        feed_url: str,
        title: str,
        site_url: str | None = None,
        categories: tuple[str, ...] = (),
    ) -> Subscription:
        normalized = normalize_feed_url(feed_url)
        if await self._repository.find_by_url(normalized):
            raise DuplicateSubscriptionError(normalized)
        subscription = Subscription.create(
            feed_url=normalized,
            title=title,
            site_url=site_url,
            categories=categories,
        )
        await self._repository.add(subscription)
        return subscription

    async def list(self) -> tuple[Subscription, ...]:
        return tuple(await self._repository.list())

    async def set_enabled(
        self,
        subscription_id: uuid.UUID,
        *,
        enabled: bool,
    ) -> Subscription:
        subscription = await self._repository.get(subscription_id)
        if subscription is None:
            raise KeyError(subscription_id)
        if enabled:
            subscription.enable()
        else:
            subscription.disable()
        await self._repository.save(subscription)
        return subscription

    async def import_entries(self, entries: tuple[OpmlEntry, ...]) -> ImportResult:
        created = 0
        duplicates = 0
        items: list[ImportItemResult] = []
        for entry in entries:
            try:
                subscription = await self.create(
                    feed_url=entry.feed_url,
                    title=entry.title,
                    site_url=entry.site_url,
                    categories=entry.categories,
                )
            except DuplicateSubscriptionError:
                duplicates += 1
                items.append(ImportItemResult(entry.feed_url, "duplicate", None))
            else:
                created += 1
                items.append(
                    ImportItemResult(entry.feed_url, "created", str(subscription.id))
                )
        return ImportResult(created=created, duplicates=duplicates, items=tuple(items))
