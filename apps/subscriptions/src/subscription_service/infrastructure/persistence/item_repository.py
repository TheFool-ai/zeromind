"""条目与修订仓储，版本推进和新修订必须在同一工作单元内提交。"""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from subscription_service.domain.aggregates.subscription_item import SubscriptionItem
from subscription_service.domain.entities.item_revision import ItemRevision
from subscription_service.domain.value_objects.item_identity import ItemIdentity
from subscription_service.infrastructure.persistence.common import flush, validate_page
from subscription_service.infrastructure.persistence.mappers import (
    digest,
    item_values,
    to_item,
    to_revision,
    to_revision_model,
)
from subscription_service.infrastructure.persistence.models import (
    ItemRevisionModel,
    SubscriptionItemModel,
)


class SqlAlchemySubscriptionItemRepository:
    """不提供历史修订 update/delete；调用方必须通过条目追加版本。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._loaded: dict[UUID, tuple[SubscriptionItem, SubscriptionItemModel]] = {}

    def _remember(self, row: SubscriptionItemModel) -> SubscriptionItem:
        if row.id not in self._loaded:
            self._loaded[row.id] = (to_item(row), row)
        return self._loaded[row.id][0]

    @staticmethod
    def _validate_revision(item: SubscriptionItem, revision: ItemRevision) -> None:
        if (
            revision.item_id != item.id
            or revision.revision_number != item.current_revision
            or revision.observed_at < item.first_seen_at
            or revision.observed_at > item.last_seen_at
        ):
            raise ValueError("修订的条目、版本或观察时间不匹配")

    async def add(self, item: SubscriptionItem, revision: ItemRevision) -> None:
        """先插条目再插修订，均不 commit；任一步失败由工作单元回滚全部写入。"""
        if item.id in self._loaded or item.current_revision != 1:
            raise ValueError("新条目必须从版本 1 开始且未添加过")
        validated = replace(item)
        self._validate_revision(validated, revision)
        row = SubscriptionItemModel(**item_values(validated))
        self._session.add(row)
        await flush(self._session)
        self._session.add(to_revision_model(revision))
        await flush(self._session)
        self._loaded[item.id] = (item, row)

    async def get(self, item_id: UUID) -> SubscriptionItem | None:
        if item_id in self._loaded:
            return self._loaded[item_id][0]
        row = await self._session.get(SubscriptionItemModel, item_id)
        return self._remember(row) if row is not None else None

    async def find_by_identity(
        self, subscription_id: UUID, identity: ItemIdentity
    ) -> SubscriptionItem | None:
        """限定来源，索引匹配后仍核对身份原值。"""
        row = await self._session.scalar(
            select(SubscriptionItemModel).where(
                SubscriptionItemModel.subscription_id == subscription_id,
                SubscriptionItemModel.identity_kind == identity.kind,
                SubscriptionItemModel.identity_digest == digest(identity.value),
                SubscriptionItemModel.identity_value == identity.value,
            )
        )
        return self._remember(row) if row is not None else None

    async def save(self, item: SubscriptionItem, revision: ItemRevision | None = None) -> None:
        """保存当前工作单元的条目；先以行版本抢占更新，再插新修订。

        即使内容没变化也持久化 last_seen_at。任意错误后调用方应退出工作单元，
        不在失败事务内继续处理其他条目。
        """
        tracked = self._loaded.get(item.id)
        if tracked is None or tracked[0] is not item:
            raise ValueError("只能保存当前工作单元加载或添加的条目实例")
        row = tracked[1]
        validated = replace(item)
        if (
            validated.subscription_id != row.subscription_id
            or validated.identity != ItemIdentity(row.identity_kind, row.identity_value)
            or validated.first_seen_at != row.first_seen_at
        ):
            raise ValueError("不能改变条目的来源、身份或首次观察时间")
        if validated.last_seen_at < row.last_seen_at:
            raise ValueError("观察时间不能倒退")
        if revision is None:
            if validated.current_revision != row.current_revision:
                raise ValueError("版本变更必须同时保存新修订")
        else:
            self._validate_revision(validated, revision)
            if validated.current_revision != row.current_revision + 1:
                raise ValueError("新修订必须连续递增，不能覆盖历史版本")
        row.current_revision = validated.current_revision
        row.last_seen_at = validated.last_seen_at
        await flush(self._session)
        if revision is not None:
            self._session.add(to_revision_model(revision))
            await flush(self._session)

    async def get_revision(self, item_id: UUID, number: int) -> ItemRevision | None:
        row = await self._session.get(ItemRevisionModel, (item_id, number))
        return to_revision(row) if row is not None else None

    async def list_revisions(
        self, item_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> tuple[ItemRevision, ...]:
        validate_page(limit, offset)
        rows = await self._session.scalars(
            select(ItemRevisionModel)
            .where(ItemRevisionModel.item_id == item_id)
            .order_by(ItemRevisionModel.revision_number)
            .limit(limit)
            .offset(offset)
        )
        return tuple(to_revision(row) for row in rows)

    async def list_by_subscription(
        self, subscription_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> tuple[SubscriptionItem, ...]:
        validate_page(limit, offset)
        rows = await self._session.scalars(
            select(SubscriptionItemModel)
            .where(SubscriptionItemModel.subscription_id == subscription_id)
            .order_by(SubscriptionItemModel.first_seen_at, SubscriptionItemModel.id)
            .limit(limit)
            .offset(offset)
        )
        return tuple(self._remember(row) for row in rows)
