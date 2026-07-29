from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from zeromind.rsshub.domain import (
    DuplicateRSSHubInstanceError,
    RSSHubAuthenticationMode,
    RSSHubInstance,
    RSSHubInstanceInUseError,
)
from zeromind.rsshub.service import RSSHubInstanceService


class CreateRSSHubInstanceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str
    access_key: str | None = None
    authentication_mode: RSSHubAuthenticationMode = RSSHubAuthenticationMode.KEY
    enabled: bool = True


class UpdateRSSHubInstanceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str
    access_key: str | None = None
    authentication_mode: RSSHubAuthenticationMode
    enabled: bool


class RSSHubInstanceResponse(BaseModel):
    id: UUID
    name: str
    base_url: str
    authentication_mode: RSSHubAuthenticationMode
    enabled: bool
    active: bool
    has_access_key: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, instance: RSSHubInstance) -> "RSSHubInstanceResponse":
        return cls(
            id=instance.id,
            name=instance.name,
            base_url=instance.base_url,
            authentication_mode=instance.authentication_mode,
            enabled=instance.enabled,
            active=instance.active,
            has_access_key=instance.encrypted_access_key is not None,
            created_at=instance.created_at,
            updated_at=instance.updated_at,
        )


class RSSHubInstanceListResponse(BaseModel):
    items: list[RSSHubInstanceResponse]


def _translate_error(error: Exception) -> HTTPException:
    if isinstance(error, DuplicateRSSHubInstanceError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "rsshub_instance_already_exists"},
        )
    if isinstance(error, RSSHubInstanceInUseError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "rsshub_instance_in_use", "message": str(error)},
        )
    if isinstance(error, KeyError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "rsshub_instance_not_found"},
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "invalid_rsshub_instance", "message": str(error)},
    )


def create_rsshub_router(service: RSSHubInstanceService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/rsshub/instances", tags=["rsshub"])

    @router.get("", response_model=RSSHubInstanceListResponse)
    async def list_instances() -> RSSHubInstanceListResponse:
        return RSSHubInstanceListResponse(
            items=[
                RSSHubInstanceResponse.from_domain(instance)
                for instance in await service.list()
            ]
        )

    @router.post(
        "",
        response_model=RSSHubInstanceResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_instance(
        request: CreateRSSHubInstanceRequest,
    ) -> RSSHubInstanceResponse:
        try:
            instance = await service.create(
                name=request.name,
                base_url=request.base_url,
                access_key=request.access_key,
                authentication_mode=request.authentication_mode,
                enabled=request.enabled,
            )
        except (DuplicateRSSHubInstanceError, ValueError) as error:
            raise _translate_error(error) from error
        return RSSHubInstanceResponse.from_domain(instance)

    @router.put("/{instance_id}", response_model=RSSHubInstanceResponse)
    async def update_instance(
        instance_id: UUID,
        request: UpdateRSSHubInstanceRequest,
    ) -> RSSHubInstanceResponse:
        kwargs: dict[str, str | None] = {}
        if "access_key" in request.model_fields_set:
            kwargs["access_key"] = request.access_key
        try:
            instance = await service.update(
                instance_id,
                name=request.name,
                base_url=request.base_url,
                authentication_mode=request.authentication_mode,
                enabled=request.enabled,
                **kwargs,
            )
        except (
            DuplicateRSSHubInstanceError,
            RSSHubInstanceInUseError,
            KeyError,
            ValueError,
        ) as error:
            raise _translate_error(error) from error
        return RSSHubInstanceResponse.from_domain(instance)

    @router.post(
        "/{instance_id}/activate",
        response_model=RSSHubInstanceResponse,
    )
    async def activate_instance(instance_id: UUID) -> RSSHubInstanceResponse:
        try:
            instance = await service.activate(instance_id)
        except (KeyError, ValueError) as error:
            raise _translate_error(error) from error
        return RSSHubInstanceResponse.from_domain(instance)

    @router.delete(
        "/{instance_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    async def delete_instance(instance_id: UUID) -> Response:
        try:
            await service.delete(instance_id)
        except (RSSHubInstanceInUseError, KeyError) as error:
            raise _translate_error(error) from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
