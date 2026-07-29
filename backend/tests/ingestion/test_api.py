import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from zeromind.bootstrap.app import create_app
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService


def test_reference_list_and_detail_expose_metadata_not_article_body() -> None:
    references = InMemoryReferenceRepository()
    ingestion = IngestionService(references)

    asyncio.run(
        ingestion.ingest(
            subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
            entries=(
                FeedEntry(
                    guid="42",
                    url="https://example.com/42",
                    title="Title",
                    summary="RSS summary only",
                    author="Ada",
                    published_at=datetime(2026, 7, 29, tzinfo=UTC),
                    updated_at=None,
                ),
            ),
            fetched_at=datetime(2026, 7, 29, 12, tzinfo=UTC),
        )
    )
    app = create_app(
        subscription_service=SubscriptionService(InMemorySubscriptionRepository()),
        reference_repository=references,
    )
    client = TestClient(app)

    listed = client.get("/api/v1/references")
    reference_id = listed.json()["items"][0]["id"]
    detail = client.get(f"/api/v1/references/{reference_id}")

    assert listed.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["revisions"][0]["summary"] == "RSS summary only"
    assert "body" not in detail.text
    assert "content" not in detail.json()["revisions"][0]
