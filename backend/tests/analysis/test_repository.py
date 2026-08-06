from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.analysis.domain import ContentAnalysis, KeyQuote, ScoreDimension, Viewpoint
from zeromind.analysis.models import (
    AnalysisDecisionOverrideModel,
    ContentAnalysisModel,
    ContentAnalysisTagModel,
)
from zeromind.analysis.repository import (
    AnalysisQuery,
    InMemoryAnalysisRepository,
    SqlAlchemyAnalysisRepository,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)


def make_analysis(
    *,
    identifier: int = 1,
    reference_id: int = 101,
    reference_revision: int = 1,
    workflow_run_id: int = 201,
    status: str = "qualified",
    total_score: int | None = 86,
    primary_category: str | None = "AI",
    secondary_categories: tuple[str, ...] = ("Engineering",),
    tags: tuple[str, ...] = ("agents", "workflows"),
    observed_at: datetime = NOW,
    published_at: datetime | None = NOW - timedelta(hours=1),
) -> ContentAnalysis:
    return ContentAnalysis(
        id=UUID(int=identifier),
        reference_id=UUID(int=reference_id),
        reference_revision=reference_revision,
        subscription_id=UUID(int=301),
        workflow_definition_id=UUID(int=401),
        workflow_definition_version=1,
        workflow_run_id=UUID(int=workflow_run_id),
        generated_status=status,  # type: ignore[arg-type]
        source_name="Example Engineering",
        source_feed_url="https://example.com/feed",
        title=f"Article {identifier}",
        original_url=f"https://example.com/articles/{identifier}",
        author="Ada",
        published_at=published_at,
        observed_at=observed_at,
        screening_score=85,
        screening_reason="Relevant and substantial",
        screening_summary="Metadata screening summary",
        primary_category=primary_category,
        secondary_categories=secondary_categories,
        tags=tags,
        one_sentence_summary="A practical Agent workflow guide.",
        summary="The article explains a practical workflow architecture.",
        viewpoints=(
            Viewpoint(
                statement="Deterministic gates improve explainability.",
                explanation="Thresholds remain visible and testable.",
            ),
        ),
        key_quotes=(
            KeyQuote(
                text="Keep model judgment separate from deterministic policy.",
                context="The author discusses scoring.",
            ),
        ),
        total_score=total_score,
        dimensions=(
            {
                "depth": ScoreDimension(
                    value=90,
                    weight=1.0,
                    reason="Detailed evidence",
                )
            }
            if total_score is not None
            else {}
        ),
        recommendation_level="recommended" if total_score is not None else None,
        recommendation_reason=(
            "High information density" if total_score is not None else None
        ),
        provenance={
            "screening": {"agent_version": 1},
            "analysis": {"agent_version": 2},
        },
        created_at=observed_at + timedelta(minutes=1),
    )


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ContentAnalysisModel.__table__.create)
        await connection.run_sync(ContentAnalysisTagModel.__table__.create)
        await connection.run_sync(AnalysisDecisionOverrideModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_repository_round_trips_the_complete_analysis(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAnalysisRepository(sessions)
    analysis = make_analysis()

    await repository.add(analysis)
    restored = await repository.get(analysis.id)

    assert restored is not None
    assert restored.reference_id == analysis.reference_id
    assert restored.tags == ("agents", "workflows")
    assert restored.dimensions["depth"].value == 90
    assert restored.key_quotes[0].context == "The author discusses scoring."
    assert restored.effective_decision == "qualified"


@pytest.mark.asyncio
async def test_sql_repository_enforces_business_and_run_idempotency(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAnalysisRepository(sessions)
    analysis = make_analysis()
    await repository.add(analysis)

    with pytest.raises(ValueError, match="duplicate analysis"):
        await repository.add(
            replace(
                analysis,
                id=UUID(int=2),
                workflow_run_id=UUID(int=202),
            )
        )
    with pytest.raises(ValueError, match="duplicate analysis"):
        await repository.add(
            replace(
                analysis,
                id=UUID(int=3),
                reference_revision=2,
            )
        )


@pytest.mark.asyncio
async def test_sql_repository_finds_analysis_by_run_and_business_identity(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAnalysisRepository(sessions)
    analysis = make_analysis()
    await repository.add(analysis)

    by_run = await repository.get_by_run(analysis.workflow_run_id)
    by_identity = await repository.get_by_identity(
        analysis.reference_id,
        analysis.reference_revision,
        analysis.workflow_definition_id,
        analysis.workflow_definition_version,
    )

    assert by_run is not None
    assert by_identity is not None
    assert by_run.id == analysis.id
    assert by_identity.id == analysis.id


@pytest.mark.asyncio
async def test_sql_repository_appends_override_and_updates_effective_decision(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAnalysisRepository(sessions)
    await repository.add(make_analysis(status="fine_rejected"))
    analysis = await repository.get(UUID(int=1))
    assert analysis is not None

    first = analysis.add_override(
        decision="qualified",
        reason="Manual review found original evidence.",
        actor_subject="admin",
        now=NOW + timedelta(hours=1),
    )
    after_first = await repository.add_override(first)
    second = after_first.add_override(
        decision="rejected",
        reason="The cited evidence is now outdated.",
        actor_subject="reviewer",
        now=NOW + timedelta(hours=2),
    )
    restored = await repository.add_override(second)

    assert [item.sequence for item in restored.overrides] == [1, 2]
    assert restored.effective_decision == "rejected"
    assert restored.generated_status == "fine_rejected"


@pytest.mark.asyncio
async def test_sql_repository_filters_analysis_feed(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAnalysisRepository(sessions)
    high = make_analysis(identifier=1, total_score=92)
    rejected = make_analysis(
        identifier=2,
        reference_id=102,
        workflow_run_id=202,
        status="fine_rejected",
        total_score=80,
        primary_category="Product",
        secondary_categories=("Strategy",),
        tags=("product",),
        observed_at=NOW - timedelta(days=1),
    )
    low = make_analysis(
        identifier=3,
        reference_id=103,
        workflow_run_id=203,
        total_score=70,
        primary_category="Research",
        secondary_categories=(),
        tags=("papers",),
        observed_at=NOW - timedelta(days=2),
    )
    for item in (high, rejected, low):
        await repository.add(item)

    assert [item.id for item in await repository.list(AnalysisQuery())] == [
        high.id,
        low.id,
    ]
    assert [
        item.id
        for item in await repository.list(
            AnalysisQuery(effective_decision="rejected")
        )
    ] == [rejected.id]
    assert [
        item.id
        for item in await repository.list(
            AnalysisQuery(effective_decision=None, minimum_score=90)
        )
    ] == [high.id]
    assert [
        item.id
        for item in await repository.list(
            AnalysisQuery(effective_decision=None, category="Engineering")
        )
    ] == [high.id]
    assert [
        item.id
        for item in await repository.list(
            AnalysisQuery(effective_decision=None, tag="product")
        )
    ] == [rejected.id]
    assert [
        item.id
        for item in await repository.list(
            AnalysisQuery(
                effective_decision=None,
                reference_id=low.reference_id,
                observed_to=NOW - timedelta(days=1, hours=12),
            )
        )
    ] == [low.id]


@pytest.mark.asyncio
async def test_sql_repository_uses_stable_score_time_id_cursor_order(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAnalysisRepository(sessions)
    first = make_analysis(identifier=3, total_score=90)
    second = make_analysis(
        identifier=2,
        reference_id=102,
        workflow_run_id=202,
        total_score=90,
    )
    third = make_analysis(
        identifier=1,
        reference_id=103,
        workflow_run_id=203,
        total_score=None,
        status="initial_rejected",
    )
    for item in (third, second, first):
        await repository.add(item)

    ordered = await repository.list(
        AnalysisQuery(effective_decision=None, limit=10)
    )
    after_first = await repository.list(
        AnalysisQuery(
            effective_decision=None,
            limit=10,
            cursor=(90, first.published_at or first.observed_at, first.id),
        )
    )

    assert [item.id for item in ordered] == [first.id, second.id, third.id]
    assert [item.id for item in after_first] == [second.id, third.id]


@pytest.mark.asyncio
async def test_sql_repository_supports_stable_time_score_id_order(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAnalysisRepository(sessions)
    newest_low = make_analysis(identifier=3, total_score=70)
    older_high = make_analysis(
        identifier=2,
        reference_id=102,
        workflow_run_id=202,
        total_score=95,
        published_at=NOW - timedelta(days=1),
    )
    same_time_no_score = make_analysis(
        identifier=1,
        reference_id=103,
        workflow_run_id=203,
        total_score=None,
        status="initial_rejected",
        published_at=NOW - timedelta(days=1),
    )
    for item in (same_time_no_score, older_high, newest_low):
        await repository.add(item)

    ordered = await repository.list(
        AnalysisQuery(effective_decision=None, sort="time", limit=10)
    )
    after_first = await repository.list(
        AnalysisQuery(
            effective_decision=None,
            sort="time",
            limit=10,
            cursor=(
                newest_low.total_score or -1,
                newest_low.published_at or newest_low.observed_at,
                newest_low.id,
            ),
        )
    )

    assert [item.id for item in ordered] == [
        newest_low.id,
        older_high.id,
        same_time_no_score.id,
    ]
    assert [item.id for item in after_first] == [
        older_high.id,
        same_time_no_score.id,
    ]


@pytest.mark.asyncio
async def test_in_memory_repository_supports_time_order_and_null_scores() -> None:
    repository = InMemoryAnalysisRepository()
    newest_low = make_analysis(identifier=3, total_score=70)
    older_high = make_analysis(
        identifier=2,
        reference_id=102,
        workflow_run_id=202,
        total_score=95,
        published_at=NOW - timedelta(days=1),
    )
    older_no_score = make_analysis(
        identifier=1,
        reference_id=103,
        workflow_run_id=203,
        total_score=None,
        status="initial_rejected",
        published_at=NOW - timedelta(days=1),
    )
    for item in (older_no_score, older_high, newest_low):
        await repository.add(item)

    ordered = await repository.list(
        AnalysisQuery(effective_decision=None, sort="time", limit=10)
    )

    assert [item.id for item in ordered] == [
        newest_low.id,
        older_high.id,
        older_no_score.id,
    ]


@pytest.mark.asyncio
async def test_in_memory_repository_matches_idempotency_and_query_contract() -> None:
    repository = InMemoryAnalysisRepository()
    high = make_analysis(identifier=1, total_score=90)
    rejected = make_analysis(
        identifier=2,
        reference_id=102,
        workflow_run_id=202,
        status="initial_rejected",
        total_score=None,
    )
    await repository.add(high)
    await repository.add(rejected)

    assert [item.id for item in await repository.list(AnalysisQuery())] == [
        high.id
    ]
    assert (await repository.get_by_run(high.workflow_run_id)).id == high.id  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="duplicate analysis"):
        await repository.add(replace(high, id=UUID(int=9)))


@pytest.mark.parametrize("limit", [0, 102])
def test_analysis_query_rejects_out_of_range_repository_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        AnalysisQuery(limit=limit)
