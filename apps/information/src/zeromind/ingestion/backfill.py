import uuid
from dataclasses import dataclass

from zeromind.ingestion.analysis_queue import ReferenceAnalysisQueue
from zeromind.ingestion.domain import PROCESSING_ANALYSIS_STATUSES, ContentReference
from zeromind.ingestion.repository import ReferenceRepository

BACKFILL_NAMESPACE = uuid.UUID("35bf0c49-1dd7-4c3f-8cf9-50756a54c896")


@dataclass(frozen=True, slots=True)
class BackfillResult:
    scanned: int
    enqueued: int
    skipped: int
    status_counts: dict[str, int]


def _status_group(reference: ContentReference) -> str:
    status = reference.analysis_status
    if status == "pending":
        return "pending"
    if status == "queued":
        return "queued"
    if status in PROCESSING_ANALYSIS_STATUSES:
        return "processing"
    if status == "completed":
        return "completed"
    if status in {"initial_rejected", "fine_rejected"}:
        return "rejected"
    return "failed"


def backfill_request_id(
    reference: ContentReference,
    *,
    workflow_version: int,
    generation: str,
) -> uuid.UUID:
    return uuid.uuid5(
        BACKFILL_NAMESPACE,
        f"{reference.id}:{reference.current_revision}:{workflow_version}:{generation}",
    )


async def backfill_reference_analysis(
    queue: ReferenceAnalysisQueue,
    references: ReferenceRepository,
    *,
    all_references: bool,
    batch_size: int,
    limit: int | None,
    generation: str,
    dry_run: bool,
    workflow_version: int = 1,
) -> BackfillResult:
    if batch_size < 1:
        raise ValueError("batch size must be positive")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    if workflow_version < 1:
        raise ValueError("workflow version must be positive")
    normalized_generation = generation.strip()
    if not normalized_generation or len(normalized_generation) > 100:
        raise ValueError("backfill generation is invalid")

    items = await references.list_references()
    counts = {
        "pending": 0,
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "rejected": 0,
        "failed": 0,
    }
    for reference in items:
        counts[_status_group(reference)] += 1

    selected = [
        reference
        for reference in items
        if reference.analysis_status not in PROCESSING_ANALYSIS_STATUSES
        and (
            all_references
            or reference.analysis_status in {"pending", "failed"}
        )
    ]
    if limit is not None:
        selected = selected[:limit]
    enqueued = 0
    for offset in range(0, len(selected), batch_size):
        for reference in selected[offset : offset + batch_size]:
            if not dry_run:
                await queue.request(
                    reference.id,
                    reference.current_revision,
                    backfill_request_id(
                        reference,
                        workflow_version=workflow_version,
                        generation=normalized_generation,
                    ),
                    f"backfill:{normalized_generation}",
                )
            enqueued += 1
    return BackfillResult(
        scanned=len(items),
        enqueued=enqueued,
        skipped=len(items) - len(selected),
        status_counts=counts,
    )
