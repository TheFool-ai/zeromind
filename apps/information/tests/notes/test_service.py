from datetime import UTC, datetime
from uuid import UUID

import pytest

from zeromind.analysis.domain import ContentAnalysis
from zeromind.analysis.repository import InMemoryAnalysisRepository
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.notes.repository import InMemoryNoteRepository
from zeromind.notes.service import NoteService

NOW = datetime(2026, 7, 31, 8, tzinfo=UTC)


def analysis(reference_id: UUID) -> ContentAnalysis:
    return ContentAnalysis(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
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


async def service_context() -> tuple[
    NoteService,
    InMemoryAnalysisRepository,
    UUID,
    UUID,
]:
    references = InMemoryReferenceRepository()
    ingestion = IngestionService(references)
    subscription_id = UUID("22222222-2222-2222-2222-222222222222")
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
    return (
        NoteService(InMemoryNoteRepository(), references, analyses),
        analyses,
        first.id,
        second.id,
    )


@pytest.mark.asyncio
async def test_service_creates_lists_updates_and_deletes_shared_note() -> None:
    service, _, reference_id, _ = await service_context()

    created = await service.create(
        reference_id=reference_id,
        analysis_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        body="Initial insight",
    )
    listed = await service.list(reference_id=reference_id)
    updated = await service.update(
        created.id,
        body="Updated insight",
        analysis_id=None,
    )
    await service.delete(created.id)

    assert [item.id for item in listed] == [created.id]
    assert updated.body == "Updated insight"
    assert updated.analysis_id is None
    assert await service.list(reference_id=reference_id) == ()


@pytest.mark.asyncio
async def test_service_requires_existing_reference() -> None:
    service, _, _, _ = await service_context()

    with pytest.raises(ValueError, match="reference_not_found"):
        await service.create(
            reference_id=UUID(
                "99999999-9999-9999-9999-999999999999"
            ),
            analysis_id=None,
            body="Insight",
        )


@pytest.mark.asyncio
async def test_service_rejects_analysis_from_another_reference() -> None:
    service, _, _, second_reference_id = await service_context()

    with pytest.raises(ValueError, match="analysis_reference_mismatch"):
        await service.create(
            reference_id=second_reference_id,
            analysis_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            body="Insight",
        )


@pytest.mark.asyncio
async def test_service_rejects_missing_note() -> None:
    service, _, _, _ = await service_context()
    missing = UUID("99999999-9999-9999-9999-999999999999")
    with pytest.raises(KeyError):
        await service.update(missing, body="Changed", analysis_id=None)
    with pytest.raises(KeyError):
        await service.delete(missing)


@pytest.mark.asyncio
async def test_note_operations_do_not_modify_analysis() -> None:
    service, analyses, reference_id, _ = await service_context()
    before = await analyses.get(
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    )

    note = await service.create(
        reference_id=reference_id,
        analysis_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        body="Insight",
    )
    await service.update(
        note.id,
        body="Updated",
        analysis_id=None,
    )
    after = await analyses.get(
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    )

    assert after == before
