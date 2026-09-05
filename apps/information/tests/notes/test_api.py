import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.analysis.domain import ContentAnalysis
from zeromind.analysis.repository import InMemoryAnalysisRepository
from zeromind.bootstrap.app import create_app
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.notes.domain import Note
from zeromind.notes.repository import InMemoryNoteRepository
from zeromind.subscriptions.infrastructure.persistence.in_memory_subscription_repository import (
    InMemorySubscriptionRepository,
)
from zeromind.subscriptions.public import SubscriptionService

NOW = datetime(2026, 7, 31, 9, tzinfo=UTC)
ANALYSIS_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def analysis(reference_id: UUID) -> ContentAnalysis:
    return ContentAnalysis(
        id=ANALYSIS_ID,
        reference_id=reference_id,
        reference_revision=1,
        subscription_id=UUID("22222222-2222-2222-2222-222222222222"),
        workflow_definition_id=UUID(
            "33333333-3333-3333-3333-333333333333"
        ),
        workflow_definition_version=1,
        workflow_run_id=UUID("44444444-4444-4444-4444-444444444444"),
        generated_status="qualified",
        source_name="Example",
        source_feed_url="https://example.com/feed",
        title="Article",
        original_url="https://example.com/article",
        author=None,
        published_at=NOW,
        observed_at=NOW,
        screening_score=80,
        screening_reason="Relevant",
        screening_summary=None,
        primary_category="AI",
        secondary_categories=(),
        tags=(),
        one_sentence_summary="Summary",
        summary="Structured summary",
        viewpoints=(),
        key_quotes=(),
        total_score=80,
        dimensions={},
        recommendation_level="recommended",
        recommendation_reason="Useful",
        provenance={},
        created_at=NOW,
    )


def make_client() -> tuple[TestClient, UUID, UUID]:
    async def arrange() -> tuple[
        InMemoryReferenceRepository,
        InMemoryAnalysisRepository,
        InMemoryNoteRepository,
        UUID,
        UUID,
    ]:
        references = InMemoryReferenceRepository()
        ingestion = IngestionService(references)
        subscription_id = UUID(
            "22222222-2222-2222-2222-222222222222"
        )
        for guid in ("one", "two"):
            await ingestion.ingest(
                subscription_id=subscription_id,
                entries=(
                    FeedEntry(
                        guid=guid,
                        url=f"https://example.com/{guid}",
                        title=guid,
                        summary=None,
                        author=None,
                        published_at=NOW,
                        updated_at=None,
                    ),
                ),
                fetched_at=NOW,
            )
        first, second = await references.list_references()
        analyses = InMemoryAnalysisRepository()
        await analyses.add(analysis(first.id))
        notes = InMemoryNoteRepository()
        await notes.add(
            Note.create(
                reference_id=first.id,
                analysis_id=ANALYSIS_ID,
                owner_subject="other",
                body="Another user's private note",
                now=NOW,
            )
        )
        return references, analyses, notes, first.id, second.id

    references, analyses, notes, reference_id, other_reference_id = asyncio.run(
        arrange()
    )
    client = TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=references,
            agent_registry=AgentRegistry(InMemoryAgentRepository()),
            analysis_repository=analyses,
            note_repository=notes,
        )
    )
    return client, reference_id, other_reference_id


def test_note_api_creates_lists_updates_and_deletes_shared_note() -> None:
    client, reference_id, _ = make_client()

    created = client.post(
        "/api/v1/notes",
        json={
            "reference_id": str(reference_id),
            "analysis_id": str(ANALYSIS_ID),
            "body": "重点关注确定性评分。",
        },
    )
    note_id = created.json()["id"]
    listed = client.get(
        f"/api/v1/notes?reference_id={reference_id}",
    )
    updated = client.put(
        f"/api/v1/notes/{note_id}",
        json={
            "analysis_id": None,
            "body": "确定性评分可以复用于项目评审。",
        },
    )
    deleted = client.delete(f"/api/v1/notes/{note_id}")
    after_delete = client.get(
        f"/api/v1/notes?reference_id={reference_id}",
    )

    assert created.status_code == 201
    assert created.json()["owner_subject"] == "local"
    assert created.json() in listed.json()["items"]
    assert updated.json()["analysis_id"] is None
    assert deleted.status_code == 204
    assert all(item["id"] != note_id for item in after_delete.json()["items"])


def test_note_api_rejects_client_owner_and_cross_reference_analysis() -> None:
    client, _, other_reference_id = make_client()

    owner = client.post(
        "/api/v1/notes",
        json={
            "reference_id": str(other_reference_id),
            "analysis_id": None,
            "owner_subject": "other",
            "body": "Insight",
        },
    )
    cross_reference = client.post(
        "/api/v1/notes",
        json={
            "reference_id": str(other_reference_id),
            "analysis_id": str(ANALYSIS_ID),
            "body": "Insight",
        },
    )

    assert owner.status_code == 422
    assert cross_reference.status_code == 422
    assert (
        cross_reference.json()["detail"]["code"]
        == "analysis_reference_mismatch"
    )


def test_note_api_allows_anonymous_access_and_validates_body() -> None:
    client, reference_id, _ = make_client()

    anonymous = client.get(f"/api/v1/notes?reference_id={reference_id}")
    empty = client.post(
        "/api/v1/notes",
        json={
            "reference_id": str(reference_id),
            "analysis_id": None,
            "body": " ",
        },
    )
    oversized = client.post(
        "/api/v1/notes",
        json={
            "reference_id": str(reference_id),
            "analysis_id": None,
            "body": "界" * 21846,
        },
    )

    assert anonymous.status_code == 200
    assert empty.status_code == 422
    assert oversized.status_code == 422


def test_analysis_detail_returns_all_related_notes() -> None:
    client, reference_id, _ = make_client()
    created = client.post(
        "/api/v1/notes",
        json={
            "reference_id": str(reference_id),
            "analysis_id": str(ANALYSIS_ID),
            "body": "My analysis note",
        },
    )

    detail = client.get(f"/api/v1/analyses/{ANALYSIS_ID}")

    assert detail.status_code == 200
    assert created.json()["id"] in [item["id"] for item in detail.json()["notes"]]
    assert "Another user's private note" in detail.text


def test_existing_note_can_be_edited_and_deleted_without_login() -> None:
    client, reference_id, _ = make_client()
    listed = client.get(f"/api/v1/notes?reference_id={reference_id}")
    assert listed.status_code == 200
    old_note = listed.json()["items"][0]
    assert old_note["owner_subject"] == "other"
    updated = client.put(
        f"/api/v1/notes/{old_note['id']}",
        json={"body": "Updated shared note", "analysis_id": None},
    )
    assert updated.status_code == 200
    assert updated.json()["owner_subject"] == "other"
    assert client.delete(f"/api/v1/notes/{old_note['id']}").status_code == 204
    assert client.get(f"/api/v1/notes?reference_id={reference_id}").json()["items"] == []
