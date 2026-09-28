"""数据库资源工厂；显式传入连接 URL，不读取旧项目 .env，不自动建表。"""

from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from subscription_service.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork


@dataclass
class Database:
    engine: AsyncEngine
    sessions: async_sessionmaker

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        """每次返回独立事务边界。"""
        return SqlAlchemyUnitOfWork(self.sessions)

    async def dispose(self) -> None:
        """应用关闭时释放连接池；不删除数据库。"""
        await self.engine.dispose()


def create_database(url: str) -> Database:
    """支持 sqlite+aiosqlite 和 postgresql+psycopg；表由 Alembic 管理。"""
    engine = create_async_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return Database(engine, async_sessionmaker(engine, expire_on_commit=False, autoflush=False))
