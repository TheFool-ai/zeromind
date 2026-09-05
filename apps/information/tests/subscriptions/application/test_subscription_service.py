from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from zeromind.subscriptions.application.subscription_service import SubscriptionService
from zeromind.subscriptions.infrastructure.opml.xml_opml_parser import XmlOpmlParser
from zeromind.subscriptions.infrastructure.persistence.in_memory_subscription_repository import (
    InMemorySubscriptionRepository,
)


@pytest.mark.asyncio
async def test_views_are_immutable_snapshots_and_updates_are_persisted() -> None:
    service = SubscriptionService(InMemorySubscriptionRepository())
    created = await service.create(feed_url="HTTPS://Example.com:443/feed", title="Example")
    assert created.feed_url == "https://example.com/feed"
    with pytest.raises(FrozenInstanceError):
        created.title = "Changed"  # type: ignore[misc]
    disabled = await service.set_enabled(created.id, enabled=False)
    assert not disabled.enabled
    assert created.enabled
    assert await service.get(created.id) == disabled


@pytest.mark.asyncio
async def test_claim_and_poll_results_are_recorded_through_application_service() -> None:
    service = SubscriptionService(InMemorySubscriptionRepository())
    created = await service.create(feed_url="https://example.com/feed", title="Example")
    now = datetime.now(UTC)
    claimed = await service.claim_due(now=now, limit=1, lease=timedelta(minutes=30))
    assert [item.id for item in claimed] == [created.id]
    assert await service.claim_due(now=now, limit=1, lease=timedelta(minutes=30)) == ()
    await service.record_failure(created.id, now=now)
    failed = await service.get(created.id)
    assert failed is not None
    assert failed.health == "degraded"
    assert failed.consecutive_failures == 1
    await service.record_success(created.id, now=now, etag='"v2"', last_modified=None)
    success = await service.get(created.id)
    assert success is not None
    assert success.health == "healthy"
    assert success.consecutive_failures == 0
    assert success.etag == '"v2"'
    assert success.next_poll_at == now + timedelta(minutes=30)


@pytest.mark.asyncio
async def test_missing_subscription_is_not_silently_created() -> None:
    service = SubscriptionService(InMemorySubscriptionRepository())
    missing = uuid4()
    assert await service.get(missing) is None
    with pytest.raises(KeyError):
        await service.record_failure(missing, now=datetime.now(UTC))
    with pytest.raises(KeyError):
        await service.record_success(missing, now=datetime.now(UTC), etag=None, last_modified=None)
    with pytest.raises(KeyError):
        await service.set_enabled(missing, enabled=False)


@pytest.mark.asyncio
async def test_opml_application_use_case_reports_duplicates_and_invalid_entries() -> None:
    service = SubscriptionService(InMemorySubscriptionRepository(), opml_parser=XmlOpmlParser())
    data = b"""<opml><body><outline text="News">
      <outline text="One" xmlUrl="https://example.com/feed"/>
      <outline text="Same" xmlUrl="HTTPS://EXAMPLE.COM:443/feed"/>
      <outline text="Invalid" xmlUrl="ftp://example.com/feed"/>
    </outline></body></opml>"""
    preview = service.preview_opml(data)
    assert preview.duplicate_count == 1
    assert preview.entries[0].categories == ("News",)
    assert len(preview.invalid_entries) == 1
    _, imported = await service.import_opml(data)
    assert imported.created == 1
    _, repeated = await service.import_opml(data)
    assert repeated.duplicates == 1
