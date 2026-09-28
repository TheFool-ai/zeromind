"""HTTP 测试共用真实迁移数据库，每例独立，不连接业务库。"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from subscription_service.bootstrap.app import create_app
from subscription_service.infrastructure.persistence.database import create_database


@pytest.fixture
async def api_database(tmp_path):
    database = create_database(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")

    def migrate(connection):
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    try:
        async with database.engine.begin() as conn:
            await conn.run_sync(migrate)
        yield database
    finally:
        await database.dispose()


@pytest.fixture
async def api(api_database):
    app = create_app(database=api_database)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
