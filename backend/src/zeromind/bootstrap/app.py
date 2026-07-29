from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
