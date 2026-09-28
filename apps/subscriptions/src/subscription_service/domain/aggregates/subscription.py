"""订阅源聚合，不包含调度、重试、运行记录或 AI 分析。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from subscription_service.domain.validation import (
    clean_categories,
    clean_name,
    positive,
    utc_time,
)
from subscription_service.domain.value_objects.feed_address import FeedAddress
from subscription_service.domain.value_objects.fetch_checkpoint import FetchCheckpoint


@dataclass(slots=True, eq=False)
class Subscription:
    """来源配置和获取检查点；地址唯一性由仓储和数据库保证。

    业务状态由方法修改。数据库按字段重建，不能调用 create 重新生成身份。
    configuration_version 是业务配置版本，与仓储内部乐观锁行版本不同。
    """

    id: UUID  # 来源稳定身份。
    name: str  # 展示名称，1～300 字符。
    feed_address: FeedAddress  # 规范化地址。
    categories: tuple[str, ...]  # 来源分类，保序去重。
    enabled: bool  # 是否继续获取；关闭保留历史条目。
    configuration_version: int  # 配置变化递增，普通获取不递增。
    fetch_checkpoint: FetchCheckpoint  # 条件请求信息及最近完整成功时间。
    created_at: datetime  # UTC 创建时间。
    updated_at: datetime  # UTC 配置修改时间，普通获取不更新。
    address_version: int = 1  # 仅地址变化递增，识别地址改走又改回的在途响应。

    def __post_init__(self) -> None:
        self.name = clean_name(self.name)
        self.categories = clean_categories(self.categories)
        positive(self.configuration_version, "配置版本")
        positive(self.address_version, "地址版本")
        self.created_at = utc_time(self.created_at)
        self.updated_at = utc_time(self.updated_at)
        if self.updated_at < self.created_at:
            raise ValueError("修改时间不能早于创建时间")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Subscription):
            return NotImplemented
        return self.id == other.id

    @classmethod
    def create(
        cls,
        *,
        name: str,
        feed_address: FeedAddress,
        now: datetime,
        categories: tuple[str, ...] = (),
    ) -> "Subscription":
        """创建默认启用、版本为 1、空检查点的来源；不执行 I/O。"""
        now = utc_time(now)
        return cls(uuid4(), name, feed_address, categories, True, 1, FetchCheckpoint(), now, now)

    def _changed_at(self, now: datetime) -> datetime:
        """先校验时间再修改状态，非法输入不能留下部分修改。"""
        now = utc_time(now)
        if now < self.updated_at:
            raise ValueError("配置修改时间不能倒退")
        return now

    def update_details(self, *, name: str, categories: tuple[str, ...], now: datetime) -> None:
        """整体替换名称和分类；规范化后无变化时不推进版本。"""
        name, categories = clean_name(name), clean_categories(categories)
        if (name, categories) == (self.name, self.categories):
            return
        now = self._changed_at(now)
        self.name, self.categories = name, categories
        self.configuration_version += 1
        self.updated_at = now

    def change_address(self, *, feed_address: FeedAddress, now: datetime) -> None:
        """同一来源迁移地址，清空检查点；相同地址为幂等操作。

        调用方负责确认来源身份及唯一性。原地址对应的条目历史保留。
        """
        if feed_address == self.feed_address:
            return
        now = self._changed_at(now)
        self.feed_address = feed_address
        self.fetch_checkpoint = FetchCheckpoint()
        self.address_version += 1
        self.configuration_version += 1
        self.updated_at = now

    def enable(self, *, now: datetime) -> None:
        """幂等启用，不伪造成功记录或直接派发任务。"""
        self._set_enabled(True, now)

    def disable(self, *, now: datetime) -> None:
        """幂等关闭，保留历史；已开始任务可以完成但不能重新启用来源。"""
        self._set_enabled(False, now)

    def _set_enabled(self, enabled: bool, now: datetime) -> None:
        if self.enabled == enabled:
            return
        now = self._changed_at(now)
        self.enabled = enabled
        self.configuration_version += 1
        self.updated_at = now

    def record_fetch_success(
        self,
        *,
        etag: str | None,
        last_modified: str | None,
        completed_at: datetime,
        expected_address_version: int | None = None,
    ) -> None:
        """完整成功后更新检查点，不影响启停和配置修改时间。

        网络调用方应传入请求开始时的 expected_address_version；旧地址结果被拒绝。
        参数可省略以支持同步初始化，但省略时调用方须自行保证地址有效。
        None 表示移除对应校验信息；304 应传入已有值。成功时间不得倒退。
        """
        if (
            expected_address_version is not None
            and expected_address_version != self.address_version
        ):
            raise ValueError("来源地址已改变，不能保存旧请求检查点")
        completed_at = utc_time(completed_at)
        previous = self.fetch_checkpoint.last_successful_fetch_at or self.created_at
        if completed_at < previous:
            raise ValueError("成功获取时间不能倒退")
        self.fetch_checkpoint = FetchCheckpoint(etag, last_modified, completed_at)
