from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from zeromind.agents.domain import AgentDefinition, AgentVersion, ProviderProfile
from zeromind.agents.registry import AgentRegistry, DuplicateAgentError
from zeromind.agents.session_domain import AgentSession, AgentSessionStatus
from zeromind.agents.session_repository import AgentSessionRepository


class CreateProviderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=255)
    api_key_env: str = Field(min_length=1, max_length=255)
    thinking_level: str = "off"
    parameters: dict[str, object] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    provider: str
    model: str
    api_key_env: str
    thinking_level: str
    parameters: dict[str, object]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ProviderListResponse(BaseModel):
    items: list[ProviderResponse]


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=1000)
    capabilities: tuple[str, ...]
    system_prompt: str = Field(min_length=1, max_length=50_000)
    provider_profile_id: UUID
    input_schema: dict[str, object]
    output_schema: dict[str, object]


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    capabilities: tuple[str, ...]
    system_prompt: str
    provider_profile_id: UUID
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    enabled: bool
    version: int
    version_id: UUID
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    items: list[AgentResponse]


class AgentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    version: int
    capabilities: tuple[str, ...]
    system_prompt: str
    provider_profile_id: UUID
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    created_at: datetime


class AgentVersionListResponse(BaseModel):
    items: list[AgentVersionResponse]


class AgentSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_run_id: UUID
    step_run_id: UUID
    agent_id: UUID
    agent_version_id: UUID
    attempt: int
    provider: str
    model: str
    thinking_level: str
    sanitized_input: dict[str, object]
    document_sha256: str | None
    document_character_count: int | None
    output: dict[str, object] | None
    response_sha256: str | None
    response_character_count: int | None
    usage: dict[str, int | float] | None
    status: AgentSessionStatus
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class AgentSessionListResponse(BaseModel):
    items: list[AgentSessionResponse]


class UpdateAgentRequest(BaseModel):
    system_prompt: str = Field(min_length=1, max_length=50_000)
    capabilities: tuple[str, ...]


def create_agent_router(
    registry: AgentRegistry,
    sessions: AgentSessionRepository | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["agents"])

    @router.post(
        "/providers",
        response_model=ProviderResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_provider(request: CreateProviderRequest) -> ProviderProfile:
        try:
            profile = ProviderProfile.create(**request.model_dump())
            await registry.register_provider(profile)
        except DuplicateAgentError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "provider_name_exists"},
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_provider", "message": str(error)},
            ) from error
        return profile

    @router.get("/providers", response_model=ProviderListResponse)
    async def list_providers() -> ProviderListResponse:
        return ProviderListResponse(
            items=[
                ProviderResponse.model_validate(item)
                for item in await registry.list_providers()
            ]
        )

    @router.post(
        "/agents",
        response_model=AgentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_agent(request: CreateAgentRequest) -> AgentDefinition:
        try:
            definition = AgentDefinition.create(**request.model_dump())
            await registry.register_agent(definition)
        except DuplicateAgentError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "agent_name_exists"},
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_agent", "message": str(error)},
            ) from error
        return definition

    @router.get("/agents", response_model=AgentListResponse)
    async def list_agents() -> AgentListResponse:
        return AgentListResponse(
            items=[
                AgentResponse.model_validate(item)
                for item in await registry.list_agents()
            ]
        )

    @router.patch("/agents/{agent_id}", response_model=AgentResponse)
    async def update_agent(
        agent_id: UUID,
        request: UpdateAgentRequest,
    ) -> AgentDefinition:
        try:
            return await registry.update_agent(agent_id, **request.model_dump())
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "agent_not_found"},
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_agent", "message": str(error)},
            ) from error

    @router.get(
        "/agents/{agent_id}/versions",
        response_model=AgentVersionListResponse,
    )
    async def list_agent_versions(agent_id: UUID) -> AgentVersionListResponse:
        try:
            versions: tuple[AgentVersion, ...] = await registry.list_agent_versions(
                agent_id
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "agent_not_found"},
            ) from error
        return AgentVersionListResponse(
            items=[AgentVersionResponse.model_validate(item) for item in versions]
        )

    async def change_agent_enabled(
        agent_id: UUID,
        *,
        enabled: bool,
    ) -> AgentDefinition:
        try:
            return await registry.set_agent_enabled(agent_id, enabled=enabled)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "agent_not_found"},
            ) from error

    @router.post("/agents/{agent_id}/disable", response_model=AgentResponse)
    async def disable_agent(agent_id: UUID) -> AgentDefinition:
        return await change_agent_enabled(agent_id, enabled=False)

    @router.post("/agents/{agent_id}/enable", response_model=AgentResponse)
    async def enable_agent(agent_id: UUID) -> AgentDefinition:
        return await change_agent_enabled(agent_id, enabled=True)

    @router.get("/agents/discover", response_model=AgentListResponse)
    async def discover_agents(
        capability: Annotated[list[str] | None, Query()] = None,
    ) -> AgentListResponse:
        agents = await registry.discover(tuple(capability or ()))
        return AgentListResponse(
            items=[AgentResponse.model_validate(item) for item in agents]
        )

    @router.get("/agent-sessions", response_model=AgentSessionListResponse)
    async def list_agent_sessions(
        workflow_run_id: UUID | None = None,
        agent_id: UUID | None = None,
        session_status: Annotated[
            AgentSessionStatus | None, Query(alias="status")
        ] = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
    ) -> AgentSessionListResponse:
        if sessions is None:
            return AgentSessionListResponse(items=[])
        values = await sessions.list(
            workflow_run_id=workflow_run_id,
            agent_id=agent_id,
            status=session_status,
            started_from=started_from,
            started_to=started_to,
        )
        return AgentSessionListResponse(
            items=[AgentSessionResponse.model_validate(item) for item in values]
        )

    @router.get("/agent-sessions/{session_id}", response_model=AgentSessionResponse)
    async def get_agent_session(session_id: UUID) -> AgentSession:
        value = await sessions.get(session_id) if sessions is not None else None
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "agent_session_not_found"},
            )
        return value

    return router
