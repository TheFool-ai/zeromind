from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from zeromind.subscriptions.application.dto.opml_preview import OpmlPreview
from zeromind.subscriptions.application.exceptions.invalid_opml_error import InvalidOpmlError
from zeromind.subscriptions.application.subscription_service import SubscriptionService
from zeromind.subscriptions.domain.exceptions.duplicate_subscription_error import (
    DuplicateSubscriptionError,
)
from zeromind.subscriptions.interfaces.http.schemas import (
    CreateSubscriptionRequest,
    ImportItemResponse,
    ImportResponse,
    InvalidOpmlEntryResponse,
    OpmlPreviewResponse,
    SubscriptionListResponse,
    SubscriptionResponse,
)


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
        return SubscriptionResponse.from_dto(subscription)

    @router.get("", response_model=SubscriptionListResponse)
    async def list_subscriptions() -> SubscriptionListResponse:
        subscriptions = await service.list()
        return SubscriptionListResponse(
            items=[SubscriptionResponse.from_dto(subscription) for subscription in subscriptions]
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
        return SubscriptionResponse.from_dto(subscription)

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
            return service.preview_opml(await file.read())
        except InvalidOpmlError as error:
            raise _invalid_opml(error) from error

    @router.post("/opml/preview", response_model=OpmlPreviewResponse)
    async def preview_opml_file(
        file: Annotated[UploadFile, File()],
    ) -> OpmlPreviewResponse:
        return OpmlPreviewResponse.from_dto(await read_preview(file))

    @router.post("/opml/import", response_model=ImportResponse)
    async def import_opml_file(
        file: Annotated[UploadFile, File()],
    ) -> ImportResponse:
        try:
            preview, result = await service.import_opml(await file.read())
        except InvalidOpmlError as error:
            raise _invalid_opml(error) from error
        return ImportResponse(
            created=result.created,
            duplicates=result.duplicates,
            invalid=len(preview.invalid_entries),
            items=[ImportItemResponse.from_dto(item) for item in result.items],
            invalid_entries=[
                InvalidOpmlEntryResponse.model_validate(item) for item in preview.invalid_entries
            ],
        )

    return router
