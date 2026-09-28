"""来源获取检查点，不承担调度、重试或执行日志职责。"""

from dataclasses import dataclass
from datetime import datetime

from subscription_service.domain.validation import utc_time


@dataclass(frozen=True, slots=True)
class FetchCheckpoint:
    """完整成功后保存的条件请求状态；初始为空，失败不替换，地址改变时清空。"""

    etag: str | None = None  # If-None-Match 使用的原始 ETag。
    last_modified: str | None = None  # If-Modified-Since 使用的 HTTP 日期原值。
    last_successful_fetch_at: datetime | None = None  # 最近完整成功时间，UTC。

    def __post_init__(self) -> None:
        if self.last_successful_fetch_at is not None:
            object.__setattr__(
                self, "last_successful_fetch_at", utc_time(self.last_successful_fetch_at)
            )
