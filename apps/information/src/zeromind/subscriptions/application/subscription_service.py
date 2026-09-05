import uuid
from datetime import datetime, timedelta

from zeromind.subscriptions.application.dto.import_item_result import ImportItemResult
from zeromind.subscriptions.application.dto.import_result import ImportResult
from zeromind.subscriptions.application.dto.opml_entry import OpmlEntry
from zeromind.subscriptions.application.dto.opml_preview import OpmlPreview
from zeromind.subscriptions.application.dto.subscription_view import SubscriptionView
from zeromind.subscriptions.application.ports.opml_parser import OpmlParser
from zeromind.subscriptions.domain.aggregates.subscription import Subscription
from zeromind.subscriptions.domain.exceptions.duplicate_subscription_error import (
    DuplicateSubscriptionError,
)
from zeromind.subscriptions.domain.repositories.subscription_repository import (
    SubscriptionRepository,
)
from zeromind.subscriptions.domain.value_objects.feed_address import FeedAddress


class SubscriptionService:
    def __init__(
        self,
        repository: SubscriptionRepository,
        *,
        opml_parser: OpmlParser | None = None,
    ) -> None:
        self._repository = repository
        self._opml_parser = opml_parser

    async def create(
        self,
        *,
        feed_url: str,
        title: str,
        site_url: str | None = None,
        categories: tuple[str, ...] = (),
    ) -> SubscriptionView:
        normalized = FeedAddress.parse(feed_url)
        if await self._repository.find_by_url(normalized):
            raise DuplicateSubscriptionError(normalized.value)
        subscription = Subscription.create(
            feed_url=normalized,
            title=title,
            site_url=site_url,
            categories=categories,
        )
        await self._repository.add(subscription)
        return SubscriptionView.from_domain(subscription)

    async def list(self) -> tuple[SubscriptionView, ...]:
        return tuple(SubscriptionView.from_domain(item) for item in await self._repository.list())

    async def set_enabled(
        self,
        subscription_id: uuid.UUID,
        *,
        enabled: bool,
    ) -> SubscriptionView:
        subscription = await self._repository.get(subscription_id)
        if subscription is None:
            raise KeyError(subscription_id)
        if enabled:
            subscription.enable()
        else:
            subscription.disable()
        await self._repository.save(subscription)
        return SubscriptionView.from_domain(subscription)

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
                items.append(ImportItemResult(entry.feed_url, "created", str(subscription.id)))
        return ImportResult(created=created, duplicates=duplicates, items=tuple(items))

    async def get(self, subscription_id: uuid.UUID) -> SubscriptionView | None:
        subscription = await self._repository.get(subscription_id)
        return SubscriptionView.from_domain(subscription) if subscription is not None else None

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease: timedelta,
    ) -> tuple[SubscriptionView, ...]:
        subscriptions = await self._repository.claim_due(now=now, limit=limit, lease=lease)
        return tuple(SubscriptionView.from_domain(item) for item in subscriptions)

    async def record_success(
        self,
        subscription_id: uuid.UUID,
        *,
        now: datetime,
        etag: str | None,
        last_modified: str | None,
        poll_interval: timedelta = timedelta(minutes=30),
    ) -> SubscriptionView:
        subscription = await self._require(subscription_id)
        subscription.mark_success(
            now=now,
            etag=etag,
            last_modified=last_modified,
            poll_interval=poll_interval,
        )
        await self._repository.save(subscription)
        return SubscriptionView.from_domain(subscription)

    async def record_failure(
        self,
        subscription_id: uuid.UUID,
        *,
        now: datetime,
    ) -> SubscriptionView:
        subscription = await self._require(subscription_id)
        subscription.mark_failure(now=now)
        await self._repository.save(subscription)
        return SubscriptionView.from_domain(subscription)

    async def _require(self, subscription_id: uuid.UUID) -> Subscription:
        subscription = await self._repository.get(subscription_id)
        if subscription is None:
            raise KeyError(subscription_id)
        return subscription

    def preview_opml(self, data: bytes) -> OpmlPreview:
        if self._opml_parser is None:
            raise RuntimeError("OPML parser has not been configured")
        return self._opml_parser.preview(data)

    async def import_opml(self, data: bytes) -> tuple[OpmlPreview, ImportResult]:
        preview = self.preview_opml(data)
        return preview, await self.import_entries(preview.entries)
