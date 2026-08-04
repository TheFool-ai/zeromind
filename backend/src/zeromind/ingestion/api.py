from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from zeromind.ingestion.analysis_queue import (
    AnalysisAlreadyProcessing,
    AnalysisRevisionConflict,
    ReferenceAnalysisQueue,
)
from zeromind.ingestion.domain import (
    AnalysisStatus,
    ContentReference,
    ReferenceRevision,
    ReferenceSummary,
)
from zeromind.ingestion.repository import ReferenceRepository


class ReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscription_id: UUID
    identity_key: str
    original_url: str | None
    current_revision: int
    first_seen_at: datetime
    last_seen_at: datetime
    analysis_status: AnalysisStatus
    analysis_status_revision: int
    analysis_workflow_run_id: UUID | None
    analysis_error_code: str | None
    analysis_error_message: str | None
    analysis_status_updated_at: datetime
    analysis_started_at: datetime | None
    analysis_completed_at: datetime | None

    @classmethod
    def from_domain(cls, value: ContentReference) -> "ReferenceResponse":
        return cls.model_validate(value)


class RevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: int
    fingerprint: str
    url: str | None
    title: str
    summary: str | None
    author: str | None
    published_at: datetime | None
    updated_at: datetime | None
    observed_at: datetime

    @classmethod
    def from_domain(cls, value: ReferenceRevision) -> "RevisionResponse":
        return cls.model_validate(value)


class ReferenceListItemResponse(ReferenceResponse):
    published_at: datetime | None

    @classmethod
    def from_summary(cls, value: ReferenceSummary) -> "ReferenceListItemResponse":
        return cls(
            **ReferenceResponse.from_domain(value.reference).model_dump(),
            published_at=value.published_at,
        )


class ReferenceListResponse(BaseModel):
    items: list[ReferenceListItemResponse]


class ReferenceDetailResponse(ReferenceResponse):
    revisions: list[RevisionResponse]


class ReanalysisResponse(BaseModel):
    reference_id: UUID
    revision: int
    request_id: UUID
    analysis_status: AnalysisStatus


def create_reference_router(
    repository: ReferenceRepository,
    analysis_queue: ReferenceAnalysisQueue | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/references", tags=["references"])

    @router.get("", response_model=ReferenceListResponse)
    async def list_references() -> ReferenceListResponse:
        summaries = await repository.list_reference_summaries()
        return ReferenceListResponse(
            items=[ReferenceListItemResponse.from_summary(item) for item in summaries]
        )

    @router.get("/{reference_id}", response_model=ReferenceDetailResponse)
    async def get_reference(reference_id: UUID) -> ReferenceDetailResponse:
        reference = await repository.get_reference(reference_id)
        if reference is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "reference_not_found"},
            )
        revisions = await repository.list_revisions(reference_id)
        return ReferenceDetailResponse(
            **ReferenceResponse.from_domain(reference).model_dump(),
            revisions=[RevisionResponse.from_domain(item) for item in revisions],
        )

    @router.post(
        "/{reference_id}/reanalyze",
        response_model=ReanalysisResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def reanalyze(reference_id: UUID) -> ReanalysisResponse:
        if analysis_queue is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "analysis_queue_unavailable"},
            )
        reference = await repository.get_reference(reference_id)
        if reference is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "reference_not_found"},
            )
        request_id = uuid4()
        try:
            await analysis_queue.request(
                reference.id,
                reference.current_revision,
                request_id,
                "manual",
            )
        except AnalysisAlreadyProcessing as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "analysis_in_progress"},
            ) from error
        except AnalysisRevisionConflict as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "reference_revision_changed"},
            ) from error
        return ReanalysisResponse(
            reference_id=reference.id,
            revision=reference.current_revision,
            request_id=request_id,
            analysis_status="pending",
        )

    return router
