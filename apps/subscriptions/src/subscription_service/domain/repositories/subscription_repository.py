"""来源仓储接口，事务提交由工作单元负责，仓储方法不自行 commit。"""

from typing import Protocol
from uuid import UUID

from subscription_service.domain.aggregates.subscription import Subscription
from subscription_service.domain.value_objects.feed_address import FeedAddress


class SubscriptionRepository(Protocol):
    async def add(self, subscription: Subscription) -> None:
        """添加新来源；重复地址抛出 DuplicateSubscriptionError。"""
        ...

    async def get(self, subscription_id: UUID) -> Subscription | None:
        """按 ID 加载工作单元内的聚合；不存在返回 None。"""
        ...

    async def find_by_address(self, address: FeedAddress) -> Subscription | None:
        """按规范化来源地址查找。"""
        ...

    async def list(
        self, *, enabled: bool | None = None, limit: int = 100, offset: int = 0
    ) -> tuple[Subscription, ...]:
        """按创建时间和 ID 稳定排序；limit 为 1～1000，offset 非负。"""
        ...

    async def save(self, subscription: Subscription) -> None:
        """保存本工作单元加载的同一实例，冲突时拒绝覆盖，必须显式调用。"""
        ...
