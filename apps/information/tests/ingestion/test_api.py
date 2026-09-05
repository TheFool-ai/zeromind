import asyncio
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi.testclient import TestClient

from zeromind.bootstrap.app import create_app
from zeromind.content.network_policy import NetworkPolicy
from zeromind.content.resolver import ContentResolver
from zeromind.ingestion.analysis_queue import InMemoryReferenceAnalysisQueue
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.lifecycle import (
    InMemoryReferenceAnalysisLifecycleRepository,
)
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.shared.outbox import InMemoryOutboxRepository
from zeromind.subscriptions.infrastructure.persistence.in_memory_subscription_repository import (
    InMemorySubscriptionRepository,
)
from zeromind.subscriptions.public import SubscriptionService


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
    async def public_address(_: str) -> tuple[str, ...]:
        return ("93.184.216.34",)

    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            content=b"""<!doctype html><html lang="en"><head>
            <title>Resolved title</title><meta name="author" content="Ada">
            </head><body><article><p>This is the transient original article body.
            It is long enough for the main text extractor to identify meaningful
            editorial content without persisting it in the database.</p></article></body></html>""",
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    app = create_app(
        subscription_service=SubscriptionService(InMemorySubscriptionRepository()),
        reference_repository=references,
        content_resolver=ContentResolver(
            network_policy=NetworkPolicy(resolver=public_address),
            transport=transport,
        ),
    )
    client = TestClient(app)

    listed = client.get("/api/v1/references")
    reference_id = listed.json()["items"][0]["id"]
    detail = client.get(f"/api/v1/references/{reference_id}")
    reading = client.get(f"/api/v1/references/{reference_id}/reading-detail")
    content = client.get(f"/api/v1/references/{reference_id}/content")

    assert listed.status_code == 200
    assert listed.json()["items"][0]["published_at"] == "2026-07-29T00:00:00Z"
    assert detail.status_code == 200
    assert detail.json()["revisions"][0]["summary"] == "RSS summary only"
    assert "body" not in detail.text
    assert "content" not in detail.json()["revisions"][0]
    assert reading.status_code == 200
    assert reading.json()["revision"]["title"] == "Title"
    assert reading.json()["iframe_url"] == "https://example.com/42"
    assert reading.json()["analysis"] is None
    assert content.status_code == 200
    assert content.json()["title"] == "Resolved title"
    assert "transient original article body" in content.json()["text"]
    assert "transient original article body" not in detail.text


def test_reference_content_reports_resolution_failure_and_missing_reference() -> None:
    references = InMemoryReferenceRepository()

    async def public_address(_: str) -> tuple[str, ...]:
        return ("93.184.216.34",)

    resolver = ContentResolver(
        network_policy=NetworkPolicy(resolver=public_address),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=b"<html><body></body></html>",
                headers={"content-type": "text/html"},
            )
        ),
    )
    asyncio.run(
        IngestionService(references).ingest(
            subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
            entries=(
                FeedEntry(
                    guid="empty",
                    url="https://example.com/empty",
                    title="Empty",
                    summary=None,
                    author=None,
                    published_at=None,
                    updated_at=None,
                ),
            ),
            fetched_at=datetime(2026, 8, 5, tzinfo=UTC),
        )
    )
    reference = asyncio.run(references.list_references())[0]
    client = TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=references,
            content_resolver=resolver,
        )
    )

    failed = client.get(f"/api/v1/references/{reference.id}/content")
    missing = client.get(
        "/api/v1/references/99999999-9999-9999-9999-999999999999/content"
    )

    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == "content_resolution_failed"
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "reference_not_found"


def test_manual_reanalysis_resets_and_enqueues_current_revision() -> None:
    references = InMemoryReferenceRepository()
    asyncio.run(
        IngestionService(references).ingest(
            subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
            entries=(
                FeedEntry(
                    guid="retry",
                    url="https://example.com/retry",
                    title="Retry",
                    summary=None,
                    author=None,
                    published_at=None,
                    updated_at=None,
                ),
            ),
            fetched_at=datetime(2026, 8, 4, tzinfo=UTC),
        )
    )
    reference = asyncio.run(references.list_references())[0]
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)
    asyncio.run(
        lifecycle.transition(
            reference.id,
            revision=1,
            status="failed",
            workflow_run_id=None,
            error_code="workflow_failed",
            error_message="provider error",
        )
    )
    outbox = InMemoryOutboxRepository()
    queue = InMemoryReferenceAnalysisQueue(references, lifecycle, outbox)
    client = TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=references,
            reference_analysis_queue=queue,
        )
    )

    response = client.post(f"/api/v1/references/{reference.id}/reanalyze")

    assert response.status_code == 202
    assert response.json()["analysis_status"] == "pending"
    request_id = UUID(response.json()["request_id"])
    event = asyncio.run(
        outbox.get_by_idempotency_key(
            "reference.analysis.requested:"
            f"{reference.id}:1:{request_id}"
        )
    )
    assert event is not None
    assert event.payload["revision"] == 1


def test_manual_reanalysis_rejects_processing_reference() -> None:
    references = InMemoryReferenceRepository()
    asyncio.run(
        IngestionService(references).ingest(
            subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
            entries=(
                FeedEntry(
                    guid="processing",
                    url=None,
                    title="Processing",
                    summary=None,
                    author=None,
                    published_at=None,
                    updated_at=None,
                ),
            ),
            fetched_at=datetime(2026, 8, 4, tzinfo=UTC),
        )
    )
    reference = asyncio.run(references.list_references())[0]
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)
    asyncio.run(
        lifecycle.transition(
            reference.id,
            revision=1,
            status="analyzing",
            workflow_run_id=UUID("22222222-2222-2222-2222-222222222222"),
        )
    )
    queue = InMemoryReferenceAnalysisQueue(
        references,
        lifecycle,
        InMemoryOutboxRepository(),
    )
    client = TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=references,
            reference_analysis_queue=queue,
        )
    )

    response = client.post(f"/api/v1/references/{reference.id}/reanalyze")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "analysis_in_progress"
