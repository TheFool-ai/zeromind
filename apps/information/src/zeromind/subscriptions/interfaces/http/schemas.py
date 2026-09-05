from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from zeromind.subscriptions.application.dto.import_item_result import ImportItemResult
from zeromind.subscriptions.application.dto.opml_preview import OpmlPreview
from zeromind.subscriptions.application.dto.subscription_view import SubscriptionView


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
    def from_dto(cls, subscription: SubscriptionView) -> "SubscriptionResponse":
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
    def from_dto(cls, value: OpmlPreview) -> "OpmlPreviewResponse":
        return cls(
            title=value.title,
            entries=[OpmlEntryResponse.model_validate(entry) for entry in value.entries],
            invalid_entries=[
                InvalidOpmlEntryResponse.model_validate(entry) for entry in value.invalid_entries
            ],
            duplicate_count=value.duplicate_count,
        )


class ImportItemResponse(BaseModel):
    feed_url: str
    status: Literal["created", "duplicate"]
    subscription_id: str | None

    @classmethod
    def from_dto(cls, value: ImportItemResult) -> "ImportItemResponse":
        return cls.model_validate(value, from_attributes=True)


class ImportResponse(BaseModel):
    created: int
    duplicates: int
    invalid: int
    items: list[ImportItemResponse]
    invalid_entries: list[InvalidOpmlEntryResponse]
