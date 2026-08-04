import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.ingestion.domain import (
    ANALYSIS_STATUSES,
    TERMINAL_ANALYSIS_STATUSES,
    AnalysisStatus,
    ContentReference,
)
from zeromind.ingestion.models import ContentReferenceModel
from zeromind.ingestion.repository import ReferenceRepository

MAX_ERROR_CODE_LENGTH = 64
MAX_ERROR_MESSAGE_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class AnalysisTransition:
    reference_id: uuid.UUID
    revision: int
    status: AnalysisStatus
    workflow_run_id: uuid.UUID | None
    error_code: str | None = None
    error_message: str | None = None


class ReferenceAnalysisLifecycleRepository(Protocol):
    async def transition(
        self,
        reference_id: uuid.UUID,
        *,
        revision: int,
        status: AnalysisStatus,
        workflow_run_id: uuid.UUID | None,
        error_code: str | None = None,
        error_message: str | None = None,
        now: datetime | None = None,
    ) -> bool: ...


def _clean_error(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] or None


def _validated_transition(
    reference_id: uuid.UUID,
    *,
    revision: int,
    status: AnalysisStatus,
    workflow_run_id: uuid.UUID | None,
    error_code: str | None,
    error_message: str | None,
) -> AnalysisTransition:
    if revision < 1:
        raise ValueError("analysis revision must be positive")
    if status not in ANALYSIS_STATUSES:
        raise ValueError(f"unsupported analysis status: {status}")
    cleaned_code = _clean_error(error_code, limit=MAX_ERROR_CODE_LENGTH)
    cleaned_message = _clean_error(error_message, limit=MAX_ERROR_MESSAGE_LENGTH)
    if status == "failed":
        if cleaned_code is None or cleaned_message is None:
            raise ValueError("failed transition requires error code and message")
    elif cleaned_code is not None or cleaned_message is not None:
        raise ValueError("error fields are only valid for failed transitions")
    return AnalysisTransition(
        reference_id=reference_id,
        revision=revision,
        status=status,
        workflow_run_id=workflow_run_id,
        error_code=cleaned_code,
        error_message=cleaned_message,
    )


def _apply_transition(
    reference: ContentReference,
    transition: AnalysisTransition,
    *,
    now: datetime,
) -> None:
    reference.analysis_status = transition.status
    reference.analysis_status_revision = transition.revision
    reference.analysis_workflow_run_id = transition.workflow_run_id
    reference.analysis_error_code = transition.error_code
    reference.analysis_error_message = transition.error_message
    reference.analysis_status_updated_at = now
    if transition.status == "pending":
        reference.analysis_started_at = None
        reference.analysis_completed_at = None
    elif transition.status == "queued":
        reference.analysis_started_at = now
        reference.analysis_completed_at = None
    elif transition.status in TERMINAL_ANALYSIS_STATUSES:
        reference.analysis_completed_at = now


class InMemoryReferenceAnalysisLifecycleRepository:
    def __init__(self, references: ReferenceRepository) -> None:
        self._references = references

    async def transition(
        self,
        reference_id: uuid.UUID,
        *,
        revision: int,
        status: AnalysisStatus,
        workflow_run_id: uuid.UUID | None,
        error_code: str | None = None,
        error_message: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        transition = _validated_transition(
            reference_id,
            revision=revision,
            status=status,
            workflow_run_id=workflow_run_id,
            error_code=error_code,
            error_message=error_message,
        )
        reference = await self._references.get_reference(reference_id)
        if reference is None:
            raise KeyError(reference_id)
        if (
            reference.current_revision != revision
            or reference.analysis_status_revision != revision
        ):
            return False
        _apply_transition(reference, transition, now=now or datetime.now(UTC))
        return True


class SqlAlchemyReferenceAnalysisLifecycleRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def transition(
        self,
        reference_id: uuid.UUID,
        *,
        revision: int,
        status: AnalysisStatus,
        workflow_run_id: uuid.UUID | None,
        error_code: str | None = None,
        error_message: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        transition = _validated_transition(
            reference_id,
            revision=revision,
            status=status,
            workflow_run_id=workflow_run_id,
            error_code=error_code,
            error_message=error_message,
        )
        changed_at = now or datetime.now(UTC)
        values: dict[str, object] = {
            "analysis_status": transition.status,
            "analysis_status_revision": transition.revision,
            "analysis_workflow_run_id": transition.workflow_run_id,
            "analysis_error_code": transition.error_code,
            "analysis_error_message": transition.error_message,
            "analysis_status_updated_at": changed_at,
        }
        if status == "pending":
            values.update(
                analysis_started_at=None,
                analysis_completed_at=None,
            )
        elif status == "queued":
            values.update(
                analysis_started_at=changed_at,
                analysis_completed_at=None,
            )
        elif status in TERMINAL_ANALYSIS_STATUSES:
            values["analysis_completed_at"] = changed_at

        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(ContentReferenceModel)
                .where(
                    ContentReferenceModel.id == reference_id,
                    ContentReferenceModel.current_revision == revision,
                    ContentReferenceModel.analysis_status_revision == revision,
                )
                .values(**values)
            )
            if cast(int, result.rowcount or 0) > 0:  # type: ignore[attr-defined]
                return True
            exists = await session.scalar(
                select(ContentReferenceModel.id).where(
                    ContentReferenceModel.id == reference_id
                )
            )
            if exists is None:
                raise KeyError(reference_id)
            return False
