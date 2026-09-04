from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from zeromind.analysis.api import AnalysisCardResponse, AnalysisDetailResponse
from zeromind.content.network_policy import BlockedNetworkTarget
from zeromind.content.resolver import ContentResolutionError, ResolvedDocument
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
from zeromind.ingestion.read_models import (
    ContentResolverUnavailable,
    ReferenceListItem,
    ReferenceListQuery,
    ReferenceReadService,
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
    title: str | None = None
    summary: str | None = None
    author: str | None = None
    source_name: str | None = None
    source_feed_url: str | None = None
    analysis: AnalysisCardResponse | None = None

    @classmethod
    def from_summary(cls, value: ReferenceSummary) -> "ReferenceListItemResponse":
        return cls(
            **ReferenceResponse.from_domain(value.reference).model_dump(),
            published_at=value.published_at,
        )

    @classmethod
    def from_read_model(cls, value: ReferenceListItem) -> "ReferenceListItemResponse":
        return cls(
            **ReferenceResponse.from_domain(value.reference).model_dump(),
            published_at=value.revision.published_at,
            title=value.revision.title,
            summary=value.revision.summary,
            author=value.revision.author,
            source_name=value.subscription.title if value.subscription else None,
            source_feed_url=(
                value.subscription.feed_url if value.subscription else None
            ),
            analysis=(
                AnalysisCardResponse.from_domain(value.analysis)
                if value.analysis
                else None
            ),
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


class ReferenceReadingDetailResponse(ReferenceResponse):
    revision: RevisionResponse
    source_name: str | None
    source_feed_url: str | None
    source_site_url: str | None
    iframe_url: str | None
    analysis: AnalysisDetailResponse | None


class ReferenceContentResponse(BaseModel):
    source_url: str
    final_url: str
    canonical_url: str | None
    title: str | None
    author: str | None
    language: str | None
    text: str

    @classmethod
    def from_document(cls, value: ResolvedDocument) -> "ReferenceContentResponse":
        return cls(
            source_url=value.source_url,
            final_url=value.final_url,
            canonical_url=value.canonical_url,
            title=value.title,
            author=value.author,
            language=value.language,
            text=value.text,
        )


def create_reference_router(
    repository: ReferenceRepository,
    analysis_queue: ReferenceAnalysisQueue | None = None,
    read_service: ReferenceReadService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/references", tags=["references"])

    @router.get("", response_model=ReferenceListResponse)
    async def list_references(
        analysis_status: Annotated[
            AnalysisStatus | None,
            Query(alias="status"),
        ] = None,
        category: Annotated[
            str | None,
            Query(min_length=1, max_length=160),
        ] = None,
        minimum_score: Annotated[
            int | None,
            Query(ge=0, le=100),
        ] = None,
        subscription_id: UUID | None = None,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
    ) -> ReferenceListResponse:
        if read_service is not None:
            items = await read_service.list(
                ReferenceListQuery(
                    status=analysis_status,
                    category=category,
                    minimum_score=minimum_score,
                    subscription_id=subscription_id,
                    published_from=published_from,
                    published_to=published_to,
                )
            )
            return ReferenceListResponse(
                items=[ReferenceListItemResponse.from_read_model(item) for item in items]
            )
        summaries = await repository.list_reference_summaries()
        return ReferenceListResponse(
            items=[ReferenceListItemResponse.from_summary(item) for item in summaries]
        )

    @router.get(
        "/{reference_id}/reading-detail",
        response_model=ReferenceReadingDetailResponse,
    )
    async def get_reading_detail(
        reference_id: UUID,
    ) -> ReferenceReadingDetailResponse:
        if read_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "reference_read_service_unavailable"},
            )
        try:
            detail = await read_service.get(reference_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "reference_not_found"},
            ) from error
        subscription = detail.subscription
        return ReferenceReadingDetailResponse(
            **ReferenceResponse.from_domain(detail.reference).model_dump(),
            revision=RevisionResponse.from_domain(detail.revision),
            source_name=subscription.title if subscription else None,
            source_feed_url=subscription.feed_url if subscription else None,
            source_site_url=subscription.site_url if subscription else None,
            iframe_url=detail.iframe_url,
            analysis=(
                AnalysisDetailResponse.from_domain(detail.analysis)
                if detail.analysis
                else None
            ),
        )

    @router.get(
        "/{reference_id}/content",
        response_model=ReferenceContentResponse,
    )
    async def get_reference_content(
        reference_id: UUID,
    ) -> ReferenceContentResponse:
        if read_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "reference_read_service_unavailable"},
            )
        try:
            document = await read_service.resolve_content(reference_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "reference_not_found"},
            ) from error
        except ContentResolverUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "content_resolver_unavailable"},
            ) from error
        except (BlockedNetworkTarget, ContentResolutionError, httpx.HTTPError) as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "content_resolution_failed",
                    "message": str(error),
                },
            ) from error
        return ReferenceContentResponse.from_document(document)

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
