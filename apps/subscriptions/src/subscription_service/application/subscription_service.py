"""订阅管理用例，每次调用独立事务；不执行网络采集或调度任务。"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from subscription_service.application.dto.subscription_view import SubscriptionView
from subscription_service.application.errors import (
    InvalidSubscriptionError,
    SubscriptionNotFoundError,
)
from subscription_service.application.ports.unit_of_work import UnitOfWork
from subscription_service.domain.aggregates.subscription import Subscription
from subscription_service.domain.errors import ConcurrentModificationError
from subscription_service.domain.value_objects.feed_address import FeedAddress


class SubscriptionService:
    """通过工作单元工厂和可注入时钟组织领域操作，不自行构造数据库。"""

    def __init__(
        self, unit_of_work: Callable[[], UnitOfWork], clock: Callable[[], datetime] | None = None
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    async def _require(uow: UnitOfWork, source_id: UUID) -> Subscription:
        source = await uow.subscriptions.get(source_id)
        if source is None:
            raise SubscriptionNotFoundError("订阅源不存在")
        return source

    @staticmethod
    def _check_version(source: Subscription, expected: int | None) -> None:
        """可选客户端版本防止用旧页面覆盖新配置；仓储另有事务级乐观锁。"""
        if expected is not None:
            if type(expected) is not int or expected < 1:
                raise InvalidSubscriptionError("配置版本必须为正整数")
            if source.configuration_version != expected:
                raise ConcurrentModificationError("订阅配置已改变，请重新读取后操作")

    async def create(
        self, *, name: str, feed_address: str, categories: tuple[str, ...] = ()
    ) -> SubscriptionView:
        """校验并创建来源；数据库唯一约束负责原子查重，成功提交后才返回。"""
        try:
            source = Subscription.create(
                name=name,
                feed_address=FeedAddress.parse(feed_address),
                categories=categories,
                now=self._clock(),
            )
        except ValueError as exc:
            raise InvalidSubscriptionError(str(exc)) from exc
        async with self._unit_of_work() as uow:
            await uow.subscriptions.add(source)
            await uow.commit()
        return SubscriptionView.from_domain(source)

    async def get(self, source_id: UUID) -> SubscriptionView:
        """读取单个来源；不存在抛出明确用例错误。"""
        async with self._unit_of_work() as uow:
            return SubscriptionView.from_domain(await self._require(uow, source_id))

    async def list(
        self, *, enabled: bool | None = None, limit: int = 100, offset: int = 0
    ) -> tuple[SubscriptionView, ...]:
        """按仓储稳定顺序分页，不为列表查询触发抓取。"""
        if not 1 <= limit <= 1000 or offset < 0:
            raise InvalidSubscriptionError("limit 必须为 1～1000，offset 必须非负")
        async with self._unit_of_work() as uow:
            sources = await uow.subscriptions.list(enabled=enabled, limit=limit, offset=offset)
            return tuple(SubscriptionView.from_domain(source) for source in sources)

    async def update(
        self,
        source_id: UUID,
        *,
        name: str | None = None,
        feed_address: str | None = None,
        categories: tuple[str, ...] | None = None,
        expected_configuration_version: int | None = None,
    ) -> SubscriptionView:
        """部分更新；None 表示未提供，空分类元组表示清空。地址变更表示同一来源迁移。

        名称/分类与地址变更各自推进配置版本，合并请求可能推进两次；版本用于比较，
        不是 HTTP 请求计数。任一字段或地址唯一性失败，整个事务回滚。
        """
        if name is None and feed_address is None and categories is None:
            raise InvalidSubscriptionError("至少提供一个要修改的字段")
        async with self._unit_of_work() as uow:
            source = await self._require(uow, source_id)
            self._check_version(source, expected_configuration_version)
            now = self._clock()
            try:
                address = FeedAddress.parse(feed_address) if feed_address is not None else None
                source.update_details(
                    name=source.name if name is None else name,
                    categories=source.categories if categories is None else categories,
                    now=now,
                )
                if address is not None:
                    source.change_address(feed_address=address, now=now)
            except ValueError as exc:
                raise InvalidSubscriptionError(str(exc)) from exc
            await uow.subscriptions.save(source)
            await uow.commit()
        return SubscriptionView.from_domain(source)

    async def set_enabled(
        self, source_id: UUID, *, enabled: bool, expected_configuration_version: int | None = None
    ) -> SubscriptionView:
        """幂等启停。客户端提供过期版本时仍拒绝操作，不默默跳过版本校验。"""
        async with self._unit_of_work() as uow:
            source = await self._require(uow, source_id)
            self._check_version(source, expected_configuration_version)
            if enabled:
                source.enable(now=self._clock())
            else:
                source.disable(now=self._clock())
            await uow.subscriptions.save(source)
            await uow.commit()
        return SubscriptionView.from_domain(source)
