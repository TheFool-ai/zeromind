from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.ingestion.domain import ContentReference
from zeromind.ingestion.lifecycle import (
    InMemoryReferenceAnalysisLifecycleRepository,
    SqlAlchemyReferenceAnalysisLifecycleRepository,
)
from zeromind.ingestion.models import ContentReferenceModel
from zeromind.ingestion.repository import InMemoryReferenceRepository

REFERENCE_ID = UUID("11111111-1111-1111-1111-111111111111")
SUBSCRIPTION_ID = UUID("22222222-2222-2222-2222-222222222222")
RUN_ID = UUID("33333333-3333-3333-3333-333333333333")
OLD_RUN_ID = UUID("44444444-4444-4444-4444-444444444444")
NOW = datetime(2026, 8, 4, 10, tzinfo=UTC)


def _reference(*, revision: int = 2) -> ContentReference:
    return ContentReference(
        id=REFERENCE_ID,
        subscription_id=SUBSCRIPTION_ID,
        identity_key="guid:article",
        original_url="https://example.com/article",
        current_revision=revision,
        first_seen_at=NOW,
        last_seen_at=NOW,
        analysis_status_revision=revision,
    )


@pytest.mark.asyncio
async def test_transition_updates_matching_revision() -> None:
    references = InMemoryReferenceRepository()
    references._references[REFERENCE_ID] = _reference()  # noqa: SLF001
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)

    changed = await lifecycle.transition(
        REFERENCE_ID,
        revision=2,
        status="screening",
        workflow_run_id=RUN_ID,
        now=NOW,
    )

    reference = await references.get_reference(REFERENCE_ID)
    assert changed is True
    assert reference is not None
    assert reference.analysis_status == "screening"
    assert reference.analysis_workflow_run_id == RUN_ID


@pytest.mark.asyncio
async def test_transition_ignores_stale_revision() -> None:
    references = InMemoryReferenceRepository()
    references._references[REFERENCE_ID] = _reference()  # noqa: SLF001
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)

    changed = await lifecycle.transition(
        REFERENCE_ID,
        revision=1,
        status="completed",
        workflow_run_id=OLD_RUN_ID,
        now=NOW,
    )

    reference = await references.get_reference(REFERENCE_ID)
    assert changed is False
    assert reference is not None
    assert reference.analysis_status == "pending"
    assert reference.analysis_workflow_run_id is None


@pytest.mark.asyncio
async def test_transition_sets_timing_and_error_fields() -> None:
    references = InMemoryReferenceRepository()
    references._references[REFERENCE_ID] = _reference()  # noqa: SLF001
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)

    await lifecycle.transition(
        REFERENCE_ID,
        revision=2,
        status="queued",
        workflow_run_id=RUN_ID,
        now=NOW,
    )
    await lifecycle.transition(
        REFERENCE_ID,
        revision=2,
        status="failed",
        workflow_run_id=RUN_ID,
        error_code=" workflow_failed ",
        error_message="  provider unavailable  ",
        now=NOW,
    )

    reference = await references.get_reference(REFERENCE_ID)
    assert reference is not None
    assert reference.analysis_started_at == NOW
    assert reference.analysis_completed_at == NOW
    assert reference.analysis_error_code == "workflow_failed"
    assert reference.analysis_error_message == "provider unavailable"

    await lifecycle.transition(
        REFERENCE_ID,
        revision=2,
        status="completed",
        workflow_run_id=RUN_ID,
        now=NOW,
    )
    assert reference.analysis_error_code is None
    assert reference.analysis_error_message is None


@pytest.mark.asyncio
async def test_failed_transition_requires_both_error_fields() -> None:
    references = InMemoryReferenceRepository()
    references._references[REFERENCE_ID] = _reference()  # noqa: SLF001
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(references)

    with pytest.raises(ValueError, match="error code and message"):
        await lifecycle.transition(
            REFERENCE_ID,
            revision=2,
            status="failed",
            workflow_run_id=RUN_ID,
            error_code="workflow_failed",
            now=NOW,
        )


@pytest_asyncio.fixture
async def sessions() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ContentReferenceModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_transition_is_revision_safe(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, session.begin():
        reference = _reference()
        session.add(
            ContentReferenceModel(
                id=reference.id,
                subscription_id=reference.subscription_id,
                identity_key=reference.identity_key,
                original_url=reference.original_url,
                current_revision=reference.current_revision,
                first_seen_at=reference.first_seen_at,
                last_seen_at=reference.last_seen_at,
                analysis_status=reference.analysis_status,
                analysis_status_revision=reference.analysis_status_revision,
                analysis_workflow_run_id=None,
                analysis_error_code=None,
                analysis_error_message=None,
                analysis_status_updated_at=reference.analysis_status_updated_at,
                analysis_started_at=None,
                analysis_completed_at=None,
            )
        )
    lifecycle = SqlAlchemyReferenceAnalysisLifecycleRepository(sessions)

    assert await lifecycle.transition(
        REFERENCE_ID,
        revision=1,
        status="completed",
        workflow_run_id=OLD_RUN_ID,
        now=NOW,
    ) is False
    assert await lifecycle.transition(
        REFERENCE_ID,
        revision=2,
        status="scoring",
        workflow_run_id=RUN_ID,
        now=NOW,
    ) is True

    async with sessions() as session:
        stored = await session.get(ContentReferenceModel, REFERENCE_ID)
    assert stored is not None
    assert stored.analysis_status == "scoring"
    assert stored.analysis_workflow_run_id == RUN_ID


@pytest.mark.asyncio
async def test_transition_raises_for_missing_reference() -> None:
    lifecycle = InMemoryReferenceAnalysisLifecycleRepository(
        InMemoryReferenceRepository()
    )
    with pytest.raises(KeyError, match=str(REFERENCE_ID)):
        await lifecycle.transition(
            REFERENCE_ID,
            revision=2,
            status="queued",
            workflow_run_id=RUN_ID,
            now=NOW,
        )
