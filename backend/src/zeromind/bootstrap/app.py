from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

DependencyState = Literal["up", "down", "unknown"]
ReadinessProbe = Callable[[], dict[str, DependencyState]]


class LiveHealth(BaseModel):
    status: Literal["ok"]


class ReadyHealth(BaseModel):
    status: Literal["ready", "unavailable"]
    dependencies: dict[str, DependencyState]


def _default_readiness_probe() -> dict[str, DependencyState]:
    return {"database": "unknown", "redis": "unknown", "pi": "unknown"}


def create_app(readiness_probe: ReadinessProbe | None = None) -> FastAPI:
    app = FastAPI(
        title="ZeroMind API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    probe = readiness_probe or _default_readiness_probe

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

