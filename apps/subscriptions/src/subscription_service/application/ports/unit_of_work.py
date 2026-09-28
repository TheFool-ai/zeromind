"""管理用例需要的事务端口；工厂每次调用必须返回新的工作单元。"""

from typing import Protocol, Self

from subscription_service.domain.repositories.subscription_repository import SubscriptionRepository


class UnitOfWork(Protocol):
    subscriptions: SubscriptionRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type, exc, traceback) -> None: ...

    async def commit(self) -> None:
        """显式提交；未提交或异常退出应回滚，不吞异常。"""
        ...
