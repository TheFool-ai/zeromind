"""订阅服务独立迁移入口；不导入旧应用或读取根目录环境文件。"""

import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from subscription_service.infrastructure.persistence.models import Base

config = context.config
url = os.environ.get("SUBSCRIPTIONS_DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    asyncio.run(online())
