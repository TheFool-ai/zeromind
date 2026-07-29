from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from zeromind.agents.api import create_agent_router
from zeromind.agents.registry import (
    AgentRegistry,
    InMemoryAgentRepository,
    SqlAlchemyAgentRepository,
)
from zeromind.ingestion.api import create_reference_router
from zeromind.ingestion.repository import (
    InMemoryReferenceRepository,
    ReferenceRepository,
    SqlAlchemyReferenceRepository,
)
from zeromind.shared.database import Database, create_database
from zeromind.subscriptions.api import create_subscription_router
from zeromind.subscriptions.repository import SqlAlchemySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService
from zeromind.workflows.api import create_workflow_router
from zeromind.workflows.executor import WorkflowExecutor
from zeromind.workflows.repository import (
    InMemoryWorkflowRepository,
    SqlAlchemyWorkflowRepository,
    WorkflowRepository,
)

DependencyState = Literal["up", "down", "unknown"]
ReadinessProbe = Callable[[], dict[str, DependencyState]]


class LiveHealth(BaseModel):
    status: Literal["ok"]


class ReadyHealth(BaseModel):
    status: Literal["ready", "unavailable"]
    dependencies: dict[str, DependencyState]


def _default_readiness_probe() -> dict[str, DependencyState]:
    return {"database": "unknown", "redis": "unknown", "pi": "unknown"}


def create_app(
    readiness_probe: ReadinessProbe | None = None,
    subscription_service: SubscriptionService | None = None,
    database: Database | None = None,
    reference_repository: ReferenceRepository | None = None,
    agent_registry: AgentRegistry | None = None,
    workflow_repository: WorkflowRepository | None = None,
    workflow_executor: WorkflowExecutor | None = None,
) -> FastAPI:
    resolved_database = database
    if subscription_service is None:
        resolved_database = resolved_database or create_database()
        subscription_service = SubscriptionService(
            SqlAlchemySubscriptionRepository(resolved_database.sessions)
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if resolved_database is not None:
            await resolved_database.dispose()

    app = FastAPI(
        title="ZeroMind API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    probe = readiness_probe or _default_readiness_probe
    app.include_router(create_subscription_router(subscription_service))
    if reference_repository is None:
        reference_repository = (
            SqlAlchemyReferenceRepository(resolved_database.sessions)
            if resolved_database is not None
            else InMemoryReferenceRepository()
        )
    app.include_router(create_reference_router(reference_repository))
    if agent_registry is None:
        agent_registry = AgentRegistry(
            SqlAlchemyAgentRepository(resolved_database.sessions)
            if resolved_database is not None
            else InMemoryAgentRepository()
        )
    app.include_router(create_agent_router(agent_registry))
    if workflow_repository is None:
        workflow_repository = (
            SqlAlchemyWorkflowRepository(resolved_database.sessions)
            if resolved_database is not None
            else InMemoryWorkflowRepository()
        )
    workflow_executor = workflow_executor or WorkflowExecutor(
        workflow_repository,
        handlers={},
    )
    app.include_router(
        create_workflow_router(
            workflow_repository,
            workflow_executor,
            agent_registry,
        )
    )

    @app.get("/health/live", response_model=LiveHealth, tags=["health"])
    def live() -> LiveHealth:
        return LiveHealth(status="ok")

    @app.get(
        "/health/ready",
        response_model=ReadyHealth,
        tags=["health"],
        responses={503: {"model": ReadyHealth}},
    )
    def ready() -> ReadyHealth | JSONResponse:
        dependencies = probe()
        status: Literal["ready", "unavailable"] = (
            "ready" if all(value == "up" for value in dependencies.values()) else "unavailable"
        )
        body = ReadyHealth(status=status, dependencies=dependencies)
        if status == "unavailable":
            return JSONResponse(status_code=503, content=body.model_dump())
        return body

    return app


app = create_app()
