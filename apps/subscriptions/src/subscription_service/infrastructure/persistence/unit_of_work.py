"""一次业务用例的本地事务；没有显式 commit 就回滚。"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from subscription_service.infrastructure.persistence.common import flush
from subscription_service.infrastructure.persistence.item_repository import (
    SqlAlchemySubscriptionItemRepository,
)
from subscription_service.infrastructure.persistence.subscription_repository import (
    SqlAlchemySubscriptionRepository,
)


class SqlAlchemyUnitOfWork:
    """两个仓储共享一个 session，确保来源、条目和修订能够原子提交。

    每个用例创建新工作单元；不跨任务共享，不自动提交，不吞掉异常。
    领域对象在 commit 后可读取，但后续修改应在新的工作单元重新加载。
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        if self._session is not None:
            raise RuntimeError("工作单元不能重复使用")
        self._session = self._sessions()
        self.subscriptions = SqlAlchemySubscriptionRepository(self._session)
        self.items = SqlAlchemySubscriptionItemRepository(self._session)
        return self

    async def commit(self) -> None:
        """显式提交；数据库约束或乐观锁冲突由仓储翻译后交给调用方。"""
        if self._session is None or self._committed:
            raise RuntimeError("工作单元未开始或已经提交")
        await flush(self._session)
        await self._session.commit()
        self._committed = True

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        assert self._session is not None
        try:
            await self._session.rollback()
        finally:
            await self._session.close()
