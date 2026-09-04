import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.analysis.repository import AnalysisRepository
from zeromind.ingestion.domain import PROCESSING_ANALYSIS_STATUSES
from zeromind.ingestion.lifecycle import ReferenceAnalysisLifecycleRepository
from zeromind.ingestion.models import ContentReferenceModel
from zeromind.ingestion.repository import ReferenceRepository
from zeromind.shared.models import OutboxEventModel
from zeromind.shared.outbox import (
    OutboxEvent,
    OutboxRepository,
    outbox_event_from_model,
)
from zeromind.workflows.repository import WorkflowRepository

ANALYSIS_REQUEST_EVENT = "reference.analysis.requested"


class AnalysisAlreadyProcessing(ValueError):
    pass


class AnalysisRevisionConflict(ValueError):
    pass


class ReferenceAnalysisQueue(Protocol):
    async def request(
        self,
        reference_id: uuid.UUID,
        revision: int,
        request_id: uuid.UUID,
        reason: str,
        *,
        now: datetime | None = None,
    ) -> OutboxEvent: ...


def analysis_request_key(
    reference_id: uuid.UUID,
    revision: int,
    request_id: uuid.UUID,
) -> str:
    return f"{ANALYSIS_REQUEST_EVENT}:{reference_id}:{revision}:{request_id}"


def analysis_request_payload(
    reference_id: uuid.UUID,
    revision: int,
    request_id: uuid.UUID,
    reason: str,
) -> dict[str, object]:
    normalized_reason = reason.strip()
    if not normalized_reason or len(normalized_reason) > 120:
        raise ValueError("analysis request reason is invalid")
    if revision < 1:
        raise ValueError("analysis revision must be positive")
    return {
        "reference_id": str(reference_id),
        "revision": revision,
        "request_id": str(request_id),
        "reason": normalized_reason,
    }


class InMemoryReferenceAnalysisQueue:
    def __init__(
        self,
        references: ReferenceRepository,
        lifecycle: ReferenceAnalysisLifecycleRepository,
        outbox: OutboxRepository,
    ) -> None:
        self._references = references
        self._lifecycle = lifecycle
        self._outbox = outbox

    async def request(
        self,
        reference_id: uuid.UUID,
        revision: int,
        request_id: uuid.UUID,
        reason: str,
        *,
        now: datetime | None = None,
    ) -> OutboxEvent:
        payload = analysis_request_payload(
            reference_id,
            revision,
            request_id,
            reason,
        )
        key = analysis_request_key(reference_id, revision, request_id)
        existing = await self._outbox.get_by_idempotency_key(key)
        if existing is not None:
            return existing
        reference = await self._references.get_reference(reference_id)
        if reference is None:
            raise KeyError(reference_id)
        if reference.current_revision != revision:
            raise AnalysisRevisionConflict(reference_id)
        if reference.analysis_status in PROCESSING_ANALYSIS_STATUSES:
            raise AnalysisAlreadyProcessing(reference_id)
        current = now or datetime.now(UTC)
        changed = await self._lifecycle.transition(
            reference_id,
            revision=revision,
            status="pending",
            workflow_run_id=None,
            now=current,
        )
        if not changed:
            raise AnalysisRevisionConflict(reference_id)
        return await self._outbox.enqueue(
            event_type=ANALYSIS_REQUEST_EVENT,
            aggregate_type="reference",
            aggregate_id=str(reference_id),
            payload=payload,
            idempotency_key=key,
            now=current,
        )


class SqlAlchemyReferenceAnalysisQueue:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def request(
        self,
        reference_id: uuid.UUID,
        revision: int,
        request_id: uuid.UUID,
        reason: str,
        *,
        now: datetime | None = None,
    ) -> OutboxEvent:
        payload = analysis_request_payload(
            reference_id,
            revision,
            request_id,
            reason,
        )
        key = analysis_request_key(reference_id, revision, request_id)
        current = now or datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            existing = await session.scalar(
                select(OutboxEventModel).where(
                    OutboxEventModel.idempotency_key == key
                )
            )
            if existing is not None:
                return outbox_event_from_model(existing)
            reference = await session.scalar(
                select(ContentReferenceModel)
                .where(ContentReferenceModel.id == reference_id)
                .with_for_update()
            )
            if reference is None:
                raise KeyError(reference_id)
            if reference.current_revision != revision:
                raise AnalysisRevisionConflict(reference_id)
            if reference.analysis_status in PROCESSING_ANALYSIS_STATUSES:
                raise AnalysisAlreadyProcessing(reference_id)
            reference.analysis_status = "pending"
            reference.analysis_status_revision = revision
            reference.analysis_workflow_run_id = None
            reference.analysis_error_code = None
            reference.analysis_error_message = None
            reference.analysis_status_updated_at = current
            reference.analysis_started_at = None
            reference.analysis_completed_at = None
            event = OutboxEventModel(
                id=uuid.uuid4(),
                event_type=ANALYSIS_REQUEST_EVENT,
                aggregate_type="reference",
                aggregate_id=str(reference_id),
                payload=payload,
                idempotency_key=key,
                status="pending",
                attempts=0,
                occurred_at=current,
                available_at=current,
            )
            session.add(event)
            await session.flush()
            return outbox_event_from_model(event)


@dataclass(frozen=True, slots=True)
class AnalysisRecoveryResult:
    repaired: int = 0
    requeued: int = 0
    skipped: int = 0


async def recover_reference_analyses(
    references: ReferenceRepository,
    lifecycle: ReferenceAnalysisLifecycleRepository,
    workflows: WorkflowRepository,
    analyses: AnalysisRepository,
    queue: ReferenceAnalysisQueue,
    *,
    before: datetime,
    now: datetime | None = None,
) -> AnalysisRecoveryResult:
    current = now or datetime.now(UTC)
    repaired = 0
    requeued = 0
    skipped = 0
    terminal_statuses = {
        "initial_rejected": "initial_rejected",
        "fine_rejected": "fine_rejected",
        "qualified": "completed",
    }
    for reference in await references.list_references():
        if reference.analysis_status not in PROCESSING_ANALYSIS_STATUSES:
            continue
        run = (
            await workflows.get_run(reference.analysis_workflow_run_id)
            if reference.analysis_workflow_run_id is not None
            else None
        )
        if run is None:
            if reference.analysis_status_updated_at > before:
                skipped += 1
                continue
            changed = await lifecycle.transition(
                reference.id,
                revision=reference.current_revision,
                status="pending",
                workflow_run_id=None,
                now=current,
            )
            if not changed:
                skipped += 1
                continue
            request_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"recovery:missing-run:{reference.id}:{reference.current_revision}",
            )
            await queue.request(
                reference.id,
                reference.current_revision,
                request_id,
                "recovery_missing_run",
                now=current,
            )
            requeued += 1
            continue
        if run.status == "completed":
            analysis = await analyses.get_by_run(run.id)
            generated_status = analysis.generated_status if analysis else None
            terminal = terminal_statuses.get(str(generated_status))
            if terminal is None:
                await lifecycle.transition(
                    reference.id,
                    revision=reference.current_revision,
                    status="failed",
                    workflow_run_id=run.id,
                    error_code="analysis_projection_invalid",
                    error_message="completed workflow has no projected analysis",
                    now=current,
                )
            else:
                await lifecycle.transition(
                    reference.id,
                    revision=reference.current_revision,
                    status=terminal,  # type: ignore[arg-type]
                    workflow_run_id=run.id,
                    now=current,
                )
            repaired += 1
            continue
        if run.status == "failed":
            projection_invalid = bool(
                run.error
                and run.error.startswith("analysis_projection_invalid:")
            )
            await lifecycle.transition(
                reference.id,
                revision=reference.current_revision,
                status="failed",
                workflow_run_id=run.id,
                error_code=(
                    "analysis_projection_invalid"
                    if projection_invalid
                    else "workflow_failed"
                ),
                error_message=run.error or "workflow failed",
                now=current,
            )
            repaired += 1
            continue
        if run.status == "running" and run.started_at <= before:
            await lifecycle.transition(
                reference.id,
                revision=reference.current_revision,
                status="failed",
                workflow_run_id=run.id,
                error_code="stale_workflow",
                error_message="workflow exceeded the analysis recovery window",
                now=current,
            )
            repaired += 1
            continue
        skipped += 1
    return AnalysisRecoveryResult(
        repaired=repaired,
        requeued=requeued,
        skipped=skipped,
    )
