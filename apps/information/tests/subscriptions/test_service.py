import pytest

from zeromind.subscriptions.domain import DuplicateSubscriptionError
from zeromind.subscriptions.opml import OpmlEntry
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService


@pytest.mark.asyncio
async def test_create_rejects_an_equivalent_feed_url() -> None:
    service = SubscriptionService(InMemorySubscriptionRepository())
    await service.create(feed_url="https://example.com/feed.xml", title="First")

    with pytest.raises(DuplicateSubscriptionError):
        await service.create(
            feed_url="HTTPS://EXAMPLE.COM:443/feed.xml#latest",
            title="Duplicate",
        )


@pytest.mark.asyncio
async def test_import_reports_created_and_duplicate_entries() -> None:
    service = SubscriptionService(InMemorySubscriptionRepository())
    entries = (
        OpmlEntry("One", "https://example.com/one.xml", None, ("News",)),
        OpmlEntry("One again", "HTTPS://EXAMPLE.COM:443/one.xml", None, ("News",)),
        OpmlEntry("Two", "https://example.com/two.xml", None, ()),
    )

    result = await service.import_entries(entries)

    assert result.created == 2
    assert result.duplicates == 1
    assert [item.status for item in result.items] == ["created", "duplicate", "created"]
