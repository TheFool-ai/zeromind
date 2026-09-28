"""FastAPI 工厂：显式配置独立数据库，不自动建表或读取旧项目 .env。"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from subscription_service.application.errors import (
    InvalidSubscriptionError,
    SubscriptionNotFoundError,
)
from subscription_service.application.opml_import_service import OpmlImportService
from subscription_service.application.subscription_service import SubscriptionService
from subscription_service.domain.errors import (
    ConcurrentModificationError,
    DuplicateSubscriptionError,
)
from subscription_service.infrastructure.opml.reader import SafeOpmlReader
from subscription_service.infrastructure.persistence.database import Database, create_database
from subscription_service.interfaces.http.opml_routes import create_opml_router
from subscription_service.interfaces.http.routes import create_router


def create_app(*, database: Database | None = None) -> FastAPI:
    """生产由 uvicorn --factory 调用，测试可注入临时数据库。

    工厂拥有的连接池在应用退出时释放；注入连接池由调用者释放。
    启动前须运行 Alembic；不对用户数据库执行隐式迁移。
    """
    owned = database is None
    if database is None:
        url = os.environ.get("SUBSCRIPTIONS_DATABASE_URL", "sqlite+aiosqlite:///subscriptions.db")
        database = create_database(url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            if owned:
                await database.dispose()

    app = FastAPI(
        title="ZeroMind 订阅服务",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.include_router(create_router(SubscriptionService(database.unit_of_work)))
    app.include_router(
        create_opml_router(OpmlImportService(database.unit_of_work, SafeOpmlReader()))
    )

    def error(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status, content={"detail": {"code": code, "message": message}}
        )

    @app.exception_handler(SubscriptionNotFoundError)
    async def not_found(request: Request, exc: SubscriptionNotFoundError):
        return error(404, "subscription_not_found", "订阅源不存在")

    @app.exception_handler(DuplicateSubscriptionError)
    async def duplicate(request: Request, exc: DuplicateSubscriptionError):
        return error(409, "subscription_already_exists", "订阅地址已存在")

    @app.exception_handler(ConcurrentModificationError)
    async def conflict(request: Request, exc: ConcurrentModificationError):
        return error(409, "subscription_version_conflict", "订阅已改变，请重新读取后操作")

    @app.exception_handler(InvalidSubscriptionError)
    async def invalid_domain_input(request: Request, exc: InvalidSubscriptionError):
        return error(422, "invalid_subscription", str(exc))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # 不回显完整输入或校验上下文，避免 URL 内误填的凭据被响应带出。
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "invalid_request",
                    "message": "请求参数不符合接口要求",
                    "fields": [
                        {"location": list(item["loc"]), "type": item["type"]}
                        for item in exc.errors()
                    ],
                }
            },
        )

    return app
