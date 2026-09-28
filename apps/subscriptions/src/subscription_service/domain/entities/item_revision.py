"""由条目聚合管理的不可变修订实体。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from subscription_service.domain.validation import positive, utc_time
from subscription_service.domain.value_objects.item_metadata import ItemMetadata


@dataclass(frozen=True, slots=True, eq=False)
class ItemRevision:
    """以 (item_id, revision_number) 标识，不允许覆盖已有版本。"""

    item_id: UUID  # 所属条目。
    revision_number: int  # 从 1 开始的版本号。
    metadata: ItemMetadata  # 此版本完整元数据。
    observed_at: datetime  # 观察时间，UTC，不是文章发布时间。

    def __post_init__(self) -> None:
        positive(self.revision_number, "修订号")
        object.__setattr__(self, "metadata", self.metadata.normalized())
        object.__setattr__(self, "observed_at", utc_time(self.observed_at))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ItemRevision):
            return NotImplemented
        return (self.item_id, self.revision_number) == (other.item_id, other.revision_number)

    def __hash__(self) -> int:
        return hash((self.item_id, self.revision_number))

    @classmethod
    def create(
        cls, *, item_id: UUID, revision_number: int, metadata: ItemMetadata, observed_at: datetime
    ) -> "ItemRevision":
        """校验并创建快照；下一版本由聚合分配，此处不查库、不发布消息。"""
        return cls(item_id, revision_number, metadata, observed_at)
