"""来源条目聚合：稳定身份、观察时间和修订号，不包含分析状态。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from subscription_service.domain.entities.item_revision import ItemRevision
from subscription_service.domain.validation import positive, utc_time
from subscription_service.domain.value_objects.item_identity import ItemIdentity
from subscription_service.domain.value_objects.item_metadata import ItemMetadata


@dataclass(slots=True, eq=False)
class SubscriptionItem:
    """通过来源 ID 关联 Subscription，不持有全部历史修订。"""

    id: UUID  # 系统稳定条目 ID。
    subscription_id: UUID  # 来源 ID。
    identity: ItemIdentity  # 同一来源内的去重身份。
    current_revision: int  # 最新修订号，从 1 开始。
    first_seen_at: datetime  # 首次观察时间，UTC。
    last_seen_at: datetime  # 最近实际观察时间；304 不逐条更新。

    def __post_init__(self) -> None:
        positive(self.current_revision, "当前修订号")
        self.first_seen_at = utc_time(self.first_seen_at)
        self.last_seen_at = utc_time(self.last_seen_at)
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("最近观察时间不能早于首次观察")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SubscriptionItem):
            return NotImplemented
        return self.id == other.id

    @classmethod
    def discover(
        cls,
        *,
        subscription_id: UUID,
        identity: ItemIdentity,
        metadata: ItemMetadata,
        observed_at: datetime,
    ) -> tuple["SubscriptionItem", ItemRevision]:
        """创建条目及版本 1；两个对象必须在同一个事务保存。"""
        observed_at = utc_time(observed_at)
        item = cls(uuid4(), subscription_id, identity, 1, observed_at, observed_at)
        revision = ItemRevision.create(
            item_id=item.id, revision_number=1, metadata=metadata, observed_at=observed_at
        )
        return item, revision

    def observe(
        self, *, current_revision: ItemRevision, metadata: ItemMetadata, observed_at: datetime
    ) -> ItemRevision | None:
        """校验当前修订并观察新数据，变化时返回新修订，否则仅更新最后观察时间。

        任何校验失败都不改变聚合；None 结果仍必须保存 last_seen_at。
        仓储乐观锁防止不同工作单元相互覆盖。
        """
        if (
            current_revision.item_id != self.id
            or current_revision.revision_number != self.current_revision
        ):
            raise ValueError("当前修订不属于本条目或版本已过期")
        observed_at = utc_time(observed_at)
        if observed_at < self.last_seen_at:
            raise ValueError("观察时间不能倒退")
        revision = None
        if not current_revision.metadata.has_same_content_as(metadata):
            revision = ItemRevision.create(
                item_id=self.id,
                revision_number=self.current_revision + 1,
                metadata=metadata,
                observed_at=observed_at,
            )
        if revision is not None:
            self.current_revision = revision.revision_number
        self.last_seen_at = observed_at
        return revision
