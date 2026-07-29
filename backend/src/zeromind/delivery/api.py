from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from zeromind.content.network_policy import BlockedNetworkTarget, NetworkPolicy
from zeromind.delivery.domain import WebhookEndpoint
from zeromind.delivery.repository import WebhookRepository


class CreateWebhookRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    secret_env: str = Field(min_length=1, max_length=255)
    events: tuple[str, ...] = Field(min_length=1)
    max_attempts: int = Field(default=3, ge=1, le=5)


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    url: str
    secret_env: str
    events: tuple[str, ...]
    enabled: bool
    max_attempts: int
    created_at: datetime
    updated_at: datetime


class WebhookListResponse(BaseModel):
    items: list[WebhookResponse]


def create_delivery_router(
    repository: WebhookRepository,
    network_policy: NetworkPolicy,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

    @router.post(
        "",
        response_model=WebhookResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_webhook(request: CreateWebhookRequest) -> WebhookEndpoint:
        try:
            await network_policy.validate_url(request.url)
        except BlockedNetworkTarget as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "blocked_webhook_target", "message": str(error)},
            ) from error
        endpoint = WebhookEndpoint.create(**request.model_dump())
        try:
            await repository.add(endpoint)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "webhook_name_exists"},
            ) from error
        return endpoint

    @router.get("", response_model=WebhookListResponse)
    async def list_webhooks() -> WebhookListResponse:
        return WebhookListResponse(
            items=[
                WebhookResponse.model_validate(item)
                for item in await repository.list()
            ]
        )

    @router.post("/{endpoint_id}/disable", response_model=WebhookResponse)
    async def disable_webhook(endpoint_id: UUID) -> WebhookEndpoint:
        endpoint = await repository.get(endpoint_id)
        if endpoint is None:
            raise HTTPException(status_code=404, detail={"code": "webhook_not_found"})
        endpoint.enabled = False
        endpoint.updated_at = datetime.now(endpoint.updated_at.tzinfo)
        await repository.save(endpoint)
        return endpoint

    return router

