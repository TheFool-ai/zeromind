"""六个管理接口；只做协议转换，事务和业务行为交给应用服务。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from subscription_service.application.subscription_service import SubscriptionService
from subscription_service.interfaces.http.schemas import (
    CreateSubscriptionRequest,
    SubscriptionListResponse,
    SubscriptionResponse,
    UpdateSubscriptionRequest,
    VersionRequest,
)


def create_router(service: SubscriptionService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/subscriptions", tags=["订阅管理"])

    @router.post("", response_model=SubscriptionResponse, status_code=201, summary="创建订阅源")
    async def create(body: CreateSubscriptionRequest, response: Response):
        result = await service.create(
            name=body.name, feed_address=body.feed_address, categories=tuple(body.categories)
        )
        response.headers["Location"] = f"/api/v1/subscriptions/{result.id}"
        return SubscriptionResponse.model_validate(result)

    @router.get("", response_model=SubscriptionListResponse, summary="分页查询订阅源")
    async def list_sources(
        enabled: bool | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        results = await service.list(enabled=enabled, limit=limit, offset=offset)
        return SubscriptionListResponse(
            items=[SubscriptionResponse.model_validate(x) for x in results],
            limit=limit,
            offset=offset,
        )

    @router.get("/{subscription_id}", response_model=SubscriptionResponse, summary="查询来源详情")
    async def get(subscription_id: UUID):
        return SubscriptionResponse.model_validate(await service.get(subscription_id))

    @router.patch("/{subscription_id}", response_model=SubscriptionResponse, summary="修改订阅源")
    async def update(subscription_id: UUID, body: UpdateSubscriptionRequest):
        result = await service.update(
            subscription_id,
            name=body.name,
            feed_address=body.feed_address,
            categories=tuple(body.categories) if body.categories is not None else None,
            expected_configuration_version=body.expected_configuration_version,
        )
        return SubscriptionResponse.model_validate(result)

    @router.post(
        "/{subscription_id}/enable", response_model=SubscriptionResponse, summary="启用来源"
    )
    async def enable(subscription_id: UUID, body: VersionRequest | None = None):
        result = await service.set_enabled(
            subscription_id,
            enabled=True,
            expected_configuration_version=body.expected_configuration_version if body else None,
        )
        return SubscriptionResponse.model_validate(result)

    @router.post(
        "/{subscription_id}/disable", response_model=SubscriptionResponse, summary="关闭来源"
    )
    async def disable(subscription_id: UUID, body: VersionRequest | None = None):
        result = await service.set_enabled(
            subscription_id,
            enabled=False,
            expected_configuration_version=body.expected_configuration_version if body else None,
        )
        return SubscriptionResponse.model_validate(result)

    return router
