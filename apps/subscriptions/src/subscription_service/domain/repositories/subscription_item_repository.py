"""条目及修订仓储接口，修订不得独立覆盖或删除。"""

from typing import Protocol
from uuid import UUID

from subscription_service.domain.aggregates.subscription_item import SubscriptionItem
from subscription_service.domain.entities.item_revision import ItemRevision
from subscription_service.domain.value_objects.item_identity import ItemIdentity


class SubscriptionItemRepository(Protocol):
    async def add(self, item: SubscriptionItem, revision: ItemRevision) -> None:
        """一起添加条目和版本 1；事务由工作单元统一提交。"""
        ...

    async def get(self, item_id: UUID) -> SubscriptionItem | None:
        """按 ID 加载，不自动加载全部历史。"""
        ...

    async def find_by_identity(
        self, subscription_id: UUID, identity: ItemIdentity
    ) -> SubscriptionItem | None:
        """同一来源内按稳定身份查找。"""
        ...

    async def save(self, item: SubscriptionItem, revision: ItemRevision | None = None) -> None:
        """保存观察时间；版本递增必须同时提供对应新修订。"""
        ...

    async def get_revision(self, item_id: UUID, number: int) -> ItemRevision | None:
        """读取指定不可变修订；不存在返回 None。"""
        ...

    async def list_revisions(
        self, item_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> tuple[ItemRevision, ...]:
        """按修订号升序分页。"""
        ...

    async def list_by_subscription(
        self, subscription_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> tuple[SubscriptionItem, ...]:
        """按首次观察时间和 ID 排序，查询来源内条目。"""
        ...
