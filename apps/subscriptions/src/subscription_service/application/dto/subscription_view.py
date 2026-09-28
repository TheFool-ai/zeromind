"""来源查询结果，不暴露 ORM、内部行版本或条件请求头。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from subscription_service.domain.aggregates.subscription import Subscription


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    id: UUID
    name: str
    feed_address: str
    categories: tuple[str, ...]
    enabled: bool
    configuration_version: int
    address_version: int
    last_successful_fetch_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, source: Subscription) -> "SubscriptionView":
        """复制标量和不可变集合，后续领域修改不会改变已返回快照。"""
        return cls(
            source.id,
            source.name,
            source.feed_address.value,
            source.categories,
            source.enabled,
            source.configuration_version,
            source.address_version,
            source.fetch_checkpoint.last_successful_fetch_at,
            source.created_at,
            source.updated_at,
        )
