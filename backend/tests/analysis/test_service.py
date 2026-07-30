from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from zeromind.analysis.domain import ContentAnalysis, ScoreDimension
from zeromind.analysis.repository import AnalysisQuery, InMemoryAnalysisRepository
from zeromind.analysis.service import (
    AnalysisService,
    decode_cursor,
    encode_cursor,
)

NOW = datetime(2026, 7, 31, 4, tzinfo=UTC)


def analysis(
    *,
    identifier: int,
    score: int,
    status: str = "qualified",
    category: str = "AI",
) -> ContentAnalysis:
    return ContentAnalysis(
        id=UUID(int=identifier),
        reference_id=UUID(int=100 + identifier),
        reference_revision=1,
        subscription_id=UUID(int=200),
        workflow_definition_id=UUID(int=300),
        workflow_definition_version=1,
        workflow_run_id=UUID(int=400 + identifier),
        generated_status=status,  # type: ignore[arg-type]
        source_name="Example Engineering",
        source_feed_url="https://example.com/feed",
        title=f"Article {identifier}",
        original_url=f"https://example.com/{identifier}",
        author=None,
        published_at=NOW - timedelta(minutes=identifier),
        observed_at=NOW,
        screening_score=80,
        screening_reason="Relevant metadata",
        screening_summary=None,
        primary_category=category,
        secondary_categories=(),
        tags=("agents",),
        one_sentence_summary="One sentence.",
        summary="Structured summary.",
        viewpoints=(),
        key_quotes=(),
        total_score=score,
        dimensions={
            "value": ScoreDimension(
                value=score,
                weight=1.0,
                reason="Deterministic score",
            )
        },
        recommendation_level="recommended",
        recommendation_reason="Useful",
        provenance={},
        created_at=NOW,
    )


async def service_with_items() -> tuple[
    AnalysisService,
    InMemoryAnalysisRepository,
]:
    repository = InMemoryAnalysisRepository()
    for item in (
        analysis(identifier=1, score=90),
        analysis(identifier=2, score=80, category="Product"),
        analysis(identifier=3, score=70),
        analysis(identifier=4, score=95, status="fine_rejected"),
    ):
        await repository.add(item)
    return AnalysisService(repository), repository


def test_cursor_round_trips_url_safe_sort_identity() -> None:
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    cursor = encode_cursor(86, NOW, analysis_id)

    assert "=" not in cursor
    assert decode_cursor(cursor) == (86, NOW, analysis_id)


@pytest.mark.parametrize(
    "cursor",
    ["not-base64!", "e30", "Wzg2LCJub3QtYS1kYXRlIiwibm90LWEtdXVpZCJd"],
)
def test_decode_cursor_rejects_malformed_values(cursor: str) -> None:
    with pytest.raises(ValueError, match="invalid_cursor"):
        decode_cursor(cursor)


@pytest.mark.asyncio
async def test_service_lists_default_qualified_feed_with_cursor_pagination() -> None:
    service, _ = await service_with_items()

    first = await service.list(AnalysisQuery(limit=2))
    assert [item.total_score for item in first.items] == [90, 80]
    assert first.next_cursor is not None

    second = await service.list(
        AnalysisQuery(limit=2, cursor=decode_cursor(first.next_cursor))
    )
    assert [item.total_score for item in second.items] == [70]
    assert second.next_cursor is None


@pytest.mark.asyncio
async def test_service_forwards_filters_and_can_list_rejected_items() -> None:
    service, _ = await service_with_items()

    product = await service.list(
        AnalysisQuery(category="Product", minimum_score=80)
    )
    rejected = await service.list(
        AnalysisQuery(effective_decision="rejected")
    )

    assert [item.title for item in product.items] == ["Article 2"]
    assert [item.title for item in rejected.items] == ["Article 4"]


@pytest.mark.asyncio
async def test_service_rejects_public_limit_above_one_hundred() -> None:
    service, _ = await service_with_items()

    with pytest.raises(ValueError, match="limit"):
        await service.list(AnalysisQuery(limit=101))


@pytest.mark.asyncio
async def test_service_gets_and_appends_audited_override() -> None:
    service, _ = await service_with_items()

    overridden = await service.override(
        UUID(int=2),
        decision="rejected",
        reason="Manual review found unsupported claims.",
        actor_subject="admin",
    )
    restored = await service.get(UUID(int=2))

    assert overridden.effective_decision == "rejected"
    assert restored.overrides[-1].sequence == 1
    assert restored.overrides[-1].actor_subject == "admin"
    assert restored.total_score == 80


@pytest.mark.asyncio
async def test_service_get_and_override_raise_for_missing_analysis() -> None:
    service, _ = await service_with_items()
    missing = UUID("99999999-9999-9999-9999-999999999999")

    with pytest.raises(KeyError):
        await service.get(missing)
    with pytest.raises(KeyError):
        await service.override(
            missing,
            decision="qualified",
            reason="Manual review found supporting evidence.",
            actor_subject="admin",
        )
