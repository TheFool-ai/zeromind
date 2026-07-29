from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from zeromind.ingestion.domain import ContentReference, ReferenceRevision
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


class ReferenceListResponse(BaseModel):
    items: list[ReferenceResponse]


class ReferenceDetailResponse(ReferenceResponse):
    revisions: list[RevisionResponse]


def create_reference_router(repository: ReferenceRepository) -> APIRouter:
    router = APIRouter(prefix="/api/v1/references", tags=["references"])

    @router.get("", response_model=ReferenceListResponse)
    async def list_references() -> ReferenceListResponse:
        references = await repository.list_references()
        return ReferenceListResponse(
            items=[ReferenceResponse.from_domain(item) for item in references]
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

    return router

