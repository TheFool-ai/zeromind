from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from zeromind.subscriptions.domain import DuplicateSubscriptionError, Subscription
from zeromind.subscriptions.opml import (
    InvalidOpmlEntry,
    InvalidOpmlError,
    OpmlEntry,
    OpmlPreview,
    preview_opml,
)
from zeromind.subscriptions.service import ImportItemResult, SubscriptionService


class CreateSubscriptionRequest(BaseModel):
    feed_url: str
    title: str = Field(min_length=1, max_length=300)
    site_url: str | None = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feed_url: str
    title: str
    site_url: str | None
    categories: tuple[str, ...]
    enabled: bool
    health: str
    next_poll_at: datetime
    last_checked_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int

    @classmethod
    def from_domain(cls, subscription: Subscription) -> "SubscriptionResponse":
        return cls.model_validate(subscription)


class SubscriptionListResponse(BaseModel):
    items: list[SubscriptionResponse]


class OpmlEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    feed_url: str
    site_url: str | None
    categories: tuple[str, ...]


class InvalidOpmlEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    feed_url: str
    reason: str


class OpmlPreviewResponse(BaseModel):
    title: str | None
    entries: list[OpmlEntryResponse]
    invalid_entries: list[InvalidOpmlEntryResponse]
    duplicate_count: int

    @classmethod
    def from_domain(cls, value: OpmlPreview) -> "OpmlPreviewResponse":
        return cls(
            title=value.title,
            entries=[OpmlEntryResponse.model_validate(entry) for entry in value.entries],
            invalid_entries=[
                InvalidOpmlEntryResponse.model_validate(entry)
                for entry in value.invalid_entries
            ],
            duplicate_count=value.duplicate_count,
        )


class ImportItemResponse(BaseModel):
    feed_url: str
    status: Literal["created", "duplicate"]
    subscription_id: str | None

    @classmethod
    def from_domain(cls, value: ImportItemResult) -> "ImportItemResponse":
        return cls.model_validate(value, from_attributes=True)


class ImportResponse(BaseModel):
    created: int
    duplicates: int
    invalid: int
    items: list[ImportItemResponse]
    invalid_entries: list[InvalidOpmlEntryResponse]


def _invalid_opml(error: InvalidOpmlError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "invalid_opml", "message": str(error)},
    )


def create_subscription_router(service: SubscriptionService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])

    @router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
    async def create_subscription(
        request: CreateSubscriptionRequest,
    ) -> SubscriptionResponse:
        try:
            subscription = await service.create(
                feed_url=request.feed_url,
                title=request.title,
                site_url=request.site_url,
            )
        except DuplicateSubscriptionError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "subscription_already_exists",
                    "feed_url": str(error),
                },
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_subscription", "message": str(error)},
            ) from error
        return SubscriptionResponse.from_domain(subscription)

    @router.get("", response_model=SubscriptionListResponse)
    async def list_subscriptions() -> SubscriptionListResponse:
        subscriptions = await service.list()
        return SubscriptionListResponse(
            items=[
                SubscriptionResponse.from_domain(subscription)
                for subscription in subscriptions
            ]
        )

    async def change_enabled(
        subscription_id: UUID,
        *,
        enabled: bool,
    ) -> SubscriptionResponse:
        try:
            subscription = await service.set_enabled(
                subscription_id,
                enabled=enabled,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "subscription_not_found"},
            ) from error
        return SubscriptionResponse.from_domain(subscription)

    @router.post("/{subscription_id}/disable", response_model=SubscriptionResponse)
    async def disable_subscription(
        subscription_id: UUID,
    ) -> SubscriptionResponse:
        return await change_enabled(subscription_id, enabled=False)

    @router.post("/{subscription_id}/enable", response_model=SubscriptionResponse)
    async def enable_subscription(
        subscription_id: UUID,
    ) -> SubscriptionResponse:
        return await change_enabled(subscription_id, enabled=True)

    async def read_preview(file: UploadFile) -> OpmlPreview:
        try:
            return preview_opml(await file.read())
        except InvalidOpmlError as error:
            raise _invalid_opml(error) from error

    @router.post("/opml/preview", response_model=OpmlPreviewResponse)
    async def preview_opml_file(
        file: Annotated[UploadFile, File()],
    ) -> OpmlPreviewResponse:
        return OpmlPreviewResponse.from_domain(await read_preview(file))

    @router.post("/opml/import", response_model=ImportResponse)
    async def import_opml_file(
        file: Annotated[UploadFile, File()],
    ) -> ImportResponse:
        preview = await read_preview(file)
        result = await service.import_entries(preview.entries)
        return ImportResponse(
            created=result.created,
            duplicates=result.duplicates,
            invalid=len(preview.invalid_entries),
            items=[ImportItemResponse.from_domain(item) for item in result.items],
            invalid_entries=[
                InvalidOpmlEntryResponse.model_validate(item)
                for item in preview.invalid_entries
            ],
        )

    return router


__all__ = [
    "InvalidOpmlEntry",
    "OpmlEntry",
    "create_subscription_router",
]
