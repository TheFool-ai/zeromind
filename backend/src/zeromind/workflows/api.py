from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from zeromind.agents.registry import AgentRegistry
from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import (
    WorkflowSpec,
    WorkflowValidationError,
    parse_workflow_yaml,
    validate_workflow,
)
from zeromind.workflows.executor import WorkflowExecutor
from zeromind.workflows.repository import WorkflowRepository


class WorkflowSourceRequest(BaseModel):
    source: str = Field(min_length=1)


class WorkflowValidationResponse(BaseModel):
    name: str
    topological_order: tuple[str, ...]
    projection: str | None
    terminal_gates: tuple[str, ...]
    warnings: tuple[str, ...]


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: int
    status: str
    created_at: datetime
    updated_at: datetime


class WorkflowListResponse(BaseModel):
    items: list[WorkflowResponse]


class RunWorkflowRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    trigger: dict[str, object] = Field(default_factory=dict)


class StepRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_id: str
    status: str
    attempts: int
    input: dict[str, object]
    output: dict[str, object] | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    definition_id: UUID
    definition_version: int
    idempotency_key: str
    trigger: dict[str, object]
    status: str
    output: dict[str, object] | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None
    steps: list[StepRunResponse]


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunResponse]


def _invalid_workflow(error: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "invalid_workflow", "message": str(error)},
    )


def _validation_warnings(spec: WorkflowSpec) -> tuple[str, ...]:
    warnings: list[str] = []
    for node in spec.nodes:
        if node.type != "gate" or node.predicate is None:
            continue
        threshold = node.predicate.right
        if (
            not isinstance(threshold, bool)
            and isinstance(threshold, int | float)
            and not 0 <= threshold <= 100
        ):
            warnings.append(
                f"gate {node.id} threshold {threshold} is outside 0 to 100"
            )
    return tuple(warnings)


def create_workflow_router(
    repository: WorkflowRepository,
    executor: WorkflowExecutor,
    agent_registry: AgentRegistry,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["workflows"])

    async def parse_and_validate(source: str) -> WorkflowSpec:
        try:
            spec = parse_workflow_yaml(source)
            await validate_workflow(spec, agent_registry)
            return spec
        except WorkflowValidationError as error:
            raise _invalid_workflow(error) from error

    @router.post("/workflows/validate", response_model=WorkflowValidationResponse)
    async def validate_source(
        request: WorkflowSourceRequest,
    ) -> WorkflowValidationResponse:
        spec = await parse_and_validate(request.source)
        return WorkflowValidationResponse(
            name=spec.name,
            topological_order=spec.topological_order(),
            projection=spec.projection,
            terminal_gates=tuple(
                node.id for node in spec.nodes if node.type == "gate"
            ),
            warnings=_validation_warnings(spec),
        )

    @router.post(
        "/workflows",
        response_model=WorkflowResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_workflow(
        request: WorkflowSourceRequest,
    ) -> WorkflowDefinition:
        spec = await parse_and_validate(request.source)
        definition = WorkflowDefinition.create(spec)
        try:
            await repository.add_definition(definition)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "workflow_name_exists"},
            ) from error
        return definition

    @router.get("/workflows", response_model=WorkflowListResponse)
    async def list_workflows() -> WorkflowListResponse:
        return WorkflowListResponse(
            items=[
                WorkflowResponse.model_validate(item)
                for item in await repository.list_definitions()
            ]
        )

    @router.post(
        "/workflows/{definition_id}/activate",
        response_model=WorkflowResponse,
    )
    async def activate_workflow(definition_id: UUID) -> WorkflowDefinition:
        definition = await repository.get_definition(definition_id)
        if definition is None:
            raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})
        definition.activate()
        await repository.save_definition(definition)
        return definition

    @router.post(
        "/workflows/{definition_id}/runs",
        response_model=WorkflowRunResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def run_workflow(
        definition_id: UUID,
        request: RunWorkflowRequest,
    ) -> WorkflowRun:
        definition = await repository.get_definition(definition_id)
        if definition is None:
            raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})
        if definition.status != "active":
            raise HTTPException(status_code=409, detail={"code": "workflow_not_active"})
        return await executor.execute(
            definition_id,
            trigger={"event": "manual", **request.trigger},
            idempotency_key=request.idempotency_key,
        )

    @router.get("/workflow-runs", response_model=WorkflowRunListResponse)
    async def list_runs() -> WorkflowRunListResponse:
        return WorkflowRunListResponse(
            items=[
                WorkflowRunResponse.model_validate(item)
                for item in await repository.list_runs()
            ]
        )

    return router
