from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from zeromind.agents.api import create_agent_router
from zeromind.agents.registry import (
    AgentRegistry,
    InMemoryAgentRepository,
    SqlAlchemyAgentRepository,
)
from zeromind.bootstrap.runtime import build_workflow_executor
from zeromind.content.network_policy import NetworkPolicy
from zeromind.delivery.api import create_delivery_router
from zeromind.delivery.repository import (
    InMemoryWebhookRepository,
    SqlAlchemyWebhookRepository,
    WebhookRepository,
)
from zeromind.identity.api import create_identity_router
from zeromind.identity.tokens import InvalidToken, TokenService
from zeromind.ingestion.api import create_reference_router
from zeromind.ingestion.repository import (
    InMemoryReferenceRepository,
    ReferenceRepository,
    SqlAlchemyReferenceRepository,
)
from zeromind.rsshub.api import create_rsshub_router
from zeromind.rsshub.credentials import CredentialCipher
from zeromind.rsshub.repository import (
    InMemoryRSSHubInstanceRepository,
    SqlAlchemyRSSHubInstanceRepository,
)
from zeromind.rsshub.service import RSSHubInstanceService
from zeromind.shared.config import get_settings
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
    token_service: TokenService | None = None,
    webhook_repository: WebhookRepository | None = None,
    webhook_network_policy: NetworkPolicy | None = None,
    rsshub_service: RSSHubInstanceService | None = None,
    require_auth: bool = False,
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
    settings = get_settings()
    resolved_token_service = token_service or TokenService(settings)

    @app.middleware("http")
    async def authenticate_admin_api(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        protected = (
            require_auth
            and request.method != "OPTIONS"
            and request.url.path.startswith("/api/v1/")
            and request.url.path != "/api/v1/auth/token"
        )
        if protected:
            authorization = request.headers.get("authorization", "")
            scheme, _, token = authorization.partition(" ")
            try:
                if scheme.lower() != "bearer" or not token:
                    raise InvalidToken("bearer token is required")
                resolved_token_service.verify(token)
            except InvalidToken:
                return JSONResponse(
                    status_code=401,
                    content={"detail": {"code": "authentication_required"}},
                )
        return await call_next(request)

    app.include_router(create_subscription_router(subscription_service))
    if rsshub_service is None:
        rsshub_service = RSSHubInstanceService(
            (
                SqlAlchemyRSSHubInstanceRepository(resolved_database.sessions)
                if resolved_database is not None
                else InMemoryRSSHubInstanceRepository()
            ),
            CredentialCipher(settings.credential_secret),
        )
    app.include_router(create_rsshub_router(rsshub_service))
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
    workflow_executor = workflow_executor or build_workflow_executor(
        workflow_repository=workflow_repository,
        reference_repository=reference_repository,
        agent_registry=agent_registry,
        settings=get_settings(),
    )
    app.include_router(
        create_workflow_router(
            workflow_repository,
            workflow_executor,
            agent_registry,
        )
    )
    app.include_router(create_identity_router(resolved_token_service))
    if webhook_repository is None:
        webhook_repository = (
            SqlAlchemyWebhookRepository(resolved_database.sessions)
            if resolved_database is not None
            else InMemoryWebhookRepository()
        )
    app.include_router(
        create_delivery_router(
            webhook_repository,
            webhook_network_policy or NetworkPolicy(),
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


app = create_app(require_auth=True)
