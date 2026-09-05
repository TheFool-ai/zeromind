from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from zeromind.analysis.domain import ContentAnalysis
from zeromind.analysis.repository import AnalysisQuery, AnalysisSort
from zeromind.analysis.service import AnalysisService, decode_cursor
from zeromind.notes.domain import Note
from zeromind.notes.service import NoteService

GeneratedStatus = Literal["initial_rejected", "fine_rejected", "qualified"]
Decision = Literal["qualified", "rejected"]


class AnalysisCardResponse(BaseModel):
    id: UUID
    reference_id: UUID
    subscription_id: UUID
    source_name: str
    source_feed_url: str
    title: str
    original_url: str | None
    author: str | None
    published_at: datetime | None
    observed_at: datetime
    generated_status: GeneratedStatus
    effective_decision: Decision
    primary_category: str | None
    tags: list[str]
    one_sentence_summary: str | None
    total_score: int | None
    recommendation_level: str | None
    recommendation_reason: str | None
    overridden: bool

    @classmethod
    def from_domain(cls, analysis: ContentAnalysis) -> "AnalysisCardResponse":
        return cls(
            id=analysis.id,
            reference_id=analysis.reference_id,
            subscription_id=analysis.subscription_id,
            source_name=analysis.source_name,
            source_feed_url=analysis.source_feed_url,
            title=analysis.title,
            original_url=analysis.original_url,
            author=analysis.author,
            published_at=analysis.published_at,
            observed_at=analysis.observed_at,
            generated_status=analysis.generated_status,
            effective_decision=analysis.effective_decision,
            primary_category=analysis.primary_category,
            tags=list(analysis.tags),
            one_sentence_summary=analysis.one_sentence_summary,
            total_score=analysis.total_score,
            recommendation_level=analysis.recommendation_level,
            recommendation_reason=analysis.recommendation_reason,
            overridden=bool(analysis.overrides),
        )


class ScreeningResponse(BaseModel):
    score: int
    reason: str
    summary: str | None


class ViewpointResponse(BaseModel):
    statement: str
    explanation: str


class KeyQuoteResponse(BaseModel):
    text: str
    context: str | None


class ScoreDimensionResponse(BaseModel):
    name: str
    value: int
    weight: float
    reason: str


class OverrideResponse(BaseModel):
    id: UUID
    sequence: int
    decision: Decision
    reason: str
    actor_subject: str
    created_at: datetime


class RelatedNoteResponse(BaseModel):
    id: UUID
    reference_id: UUID
    analysis_id: UUID | None
    owner_subject: str
    body: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, note: Note) -> "RelatedNoteResponse":
        return cls(
            id=note.id,
            reference_id=note.reference_id,
            analysis_id=note.analysis_id,
            owner_subject=note.owner_subject,
            body=note.body,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )


class AnalysisDetailResponse(AnalysisCardResponse):
    reference_revision: int
    workflow_definition_id: UUID
    workflow_definition_version: int
    workflow_run_id: UUID
    screening: ScreeningResponse
    secondary_categories: list[str]
    summary: str | None
    viewpoints: list[ViewpointResponse]
    key_quotes: list[KeyQuoteResponse]
    dimensions: list[ScoreDimensionResponse]
    provenance: dict[str, object]
    overrides: list[OverrideResponse]
    notes: list[RelatedNoteResponse]
    created_at: datetime

    @classmethod
    def from_domain(
        cls,
        analysis: ContentAnalysis,
        *,
        notes: tuple[Note, ...] = (),
    ) -> "AnalysisDetailResponse":
        card = AnalysisCardResponse.from_domain(analysis)
        return cls(
            **card.model_dump(),
            reference_revision=analysis.reference_revision,
            workflow_definition_id=analysis.workflow_definition_id,
            workflow_definition_version=analysis.workflow_definition_version,
            workflow_run_id=analysis.workflow_run_id,
            screening=ScreeningResponse(
                score=analysis.screening_score,
                reason=analysis.screening_reason,
                summary=analysis.screening_summary,
            ),
            secondary_categories=list(analysis.secondary_categories),
            summary=analysis.summary,
            viewpoints=[
                ViewpointResponse(
                    statement=item.statement,
                    explanation=item.explanation,
                )
                for item in analysis.viewpoints
            ],
            key_quotes=[
                KeyQuoteResponse(text=item.text, context=item.context)
                for item in analysis.key_quotes
            ],
            dimensions=[
                ScoreDimensionResponse(
                    name=name,
                    value=item.value,
                    weight=item.weight,
                    reason=item.reason,
                )
                for name, item in analysis.dimensions.items()
            ],
            provenance=dict(analysis.provenance),
            overrides=[
                OverrideResponse(
                    id=item.id,
                    sequence=item.sequence,
                    decision=item.decision,
                    reason=item.reason,
                    actor_subject=item.actor_subject,
                    created_at=item.created_at,
                )
                for item in analysis.overrides
            ],
            notes=[RelatedNoteResponse.from_domain(note) for note in notes],
            created_at=analysis.created_at,
        )


class AnalysisListResponse(BaseModel):
    items: list[AnalysisCardResponse]
    next_cursor: str | None


class CreateOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    reason: str = Field(min_length=10, max_length=2000)


def create_analysis_router(
    service: AnalysisService,
    note_service: NoteService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])

    @router.get("", response_model=AnalysisListResponse)
    async def list_analyses(
        generated_status: GeneratedStatus | None = None,
        effective_decision: Decision | None = "qualified",
        minimum_score: int | None = Query(default=None, ge=0, le=100),
        category: str | None = Query(default=None, min_length=1, max_length=160),
        tag: str | None = Query(default=None, min_length=1, max_length=80),
        subscription_id: UUID | None = None,
        reference_id: UUID | None = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        sort: AnalysisSort = "score",
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = None,
    ) -> AnalysisListResponse:
        decoded_cursor = None
        if cursor is not None:
            try:
                decoded_cursor = decode_cursor(cursor, expected_sort=sort)
            except ValueError as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={"code": "invalid_cursor"},
                ) from error
        page = await service.list(
            AnalysisQuery(
                generated_status=generated_status,
                effective_decision=effective_decision,
                minimum_score=minimum_score,
                category=category,
                tag=tag,
                subscription_id=subscription_id,
                reference_id=reference_id,
                observed_from=observed_from,
                observed_to=observed_to,
                sort=sort,
                limit=limit,
                cursor=decoded_cursor,
            )
        )
        return AnalysisListResponse(
            items=[
                AnalysisCardResponse.from_domain(item)
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )

    @router.get("/{analysis_id}", response_model=AnalysisDetailResponse)
    async def get_analysis(
        analysis_id: UUID,
    ) -> AnalysisDetailResponse:
        try:
            analysis = await service.get(analysis_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "analysis_not_found"},
            ) from error
        notes: tuple[Note, ...] = ()
        if note_service is not None:
            notes = await note_service.list(
                reference_id=analysis.reference_id,
            )
        return AnalysisDetailResponse.from_domain(analysis, notes=notes)

    @router.post(
        "/{analysis_id}/overrides",
        response_model=AnalysisDetailResponse,
    )
    async def override_analysis(
        analysis_id: UUID,
        payload: CreateOverrideRequest,
    ) -> AnalysisDetailResponse:
        try:
            analysis = await service.override(
                analysis_id,
                decision=payload.decision,
                reason=payload.reason,
                actor_subject="local",
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "analysis_not_found"},
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_override", "message": str(error)},
            ) from error
        notes = (
            await note_service.list(
                reference_id=analysis.reference_id,
            )
            if note_service is not None
            else ()
        )
        return AnalysisDetailResponse.from_domain(analysis, notes=notes)

    return router
