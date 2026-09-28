"""来源 SQL 仓储；领域对象显式 save，事务由工作单元统一提交。"""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from subscription_service.domain.aggregates.subscription import Subscription
from subscription_service.domain.value_objects.feed_address import FeedAddress
from subscription_service.infrastructure.persistence.common import flush, validate_page
from subscription_service.infrastructure.persistence.mappers import (
    digest,
    subscription_values,
    to_subscription,
)
from subscription_service.infrastructure.persistence.models import SubscriptionModel


class SqlAlchemySubscriptionRepository:
    """同一工作单元内维护领域身份映射，防止用脱离会话的旧对象覆盖新值。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._loaded: dict[UUID, tuple[Subscription, SubscriptionModel]] = {}

    def _remember(self, row: SubscriptionModel) -> Subscription:
        if row.id not in self._loaded:
            self._loaded[row.id] = (to_subscription(row), row)
        return self._loaded[row.id][0]

    async def add(self, subscription: Subscription) -> None:
        """插入来源并立即验证约束，尚未 commit。"""
        if subscription.id in self._loaded:
            raise ValueError("来源已经属于当前工作单元")
        validated = replace(subscription)
        row = SubscriptionModel(**subscription_values(validated))
        self._session.add(row)
        await flush(self._session)
        self._loaded[subscription.id] = (subscription, row)

    async def get(self, subscription_id: UUID) -> Subscription | None:
        """读取聚合，不存在返回 None。返回对象修改后必须显式 save。"""
        if subscription_id in self._loaded:
            return self._loaded[subscription_id][0]
        row = await self._session.get(SubscriptionModel, subscription_id)
        return self._remember(row) if row is not None else None

    async def find_by_address(self, address: FeedAddress) -> Subscription | None:
        """哈希索引定位后核对原地址，避免返回理论上哈希碰撞的另一来源。"""
        row = await self._session.scalar(
            select(SubscriptionModel).where(
                SubscriptionModel.address_digest == digest(address.value),
                SubscriptionModel.feed_address == address.value,
            )
        )
        return self._remember(row) if row is not None else None

    async def list(
        self, *, enabled: bool | None = None, limit: int = 100, offset: int = 0
    ) -> tuple[Subscription, ...]:
        """稳定分页查询；只在来源表内查询，不跨服务访问。"""
        validate_page(limit, offset)
        query = (
            select(SubscriptionModel)
            .order_by(SubscriptionModel.created_at, SubscriptionModel.id)
            .limit(limit)
            .offset(offset)
        )
        if enabled is not None:
            query = query.where(SubscriptionModel.enabled == enabled)
        return tuple(self._remember(row) for row in await self._session.scalars(query))

    async def save(self, subscription: Subscription) -> None:
        """使用 ORM 行版本执行乐观更新；冲突使整个事务回滚，不能盲目重试旧对象。"""
        tracked = self._loaded.get(subscription.id)
        if tracked is None or tracked[0] is not subscription:
            raise ValueError("只能保存当前工作单元加载或添加的来源实例")
        row = tracked[1]
        validated = replace(subscription)
        if validated.created_at != row.created_at:
            raise ValueError("不能修改来源创建时间")
        for key, value in subscription_values(validated).items():
            if key != "id":
                setattr(row, key, value)
        await flush(self._session)
