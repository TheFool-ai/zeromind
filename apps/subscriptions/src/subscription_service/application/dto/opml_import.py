"""OPML 边界数据：解析结果与导入报告，不暴露上传原文或 ORM 对象。"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

# HTTP 层和解析器共同执行此上限；直调应用层也不能绕过。
MAX_OPML_BYTES = 1024 * 1024
MAX_OPML_OUTLINES = 1000  # 包括文件夹，避免仅限制 Feed 时漏掉大量分组节点。
MAX_XML_DEPTH = 32  # 根 opml 为第 1 层。
MAX_XML_ELEMENTS = 10000  # 同时约束 head 内非 outline 节点。


@dataclass(frozen=True, slots=True)
class OpmlEntry:
    """一个候选来源；index 是文档中候选来源的 1 起始顺序，不包含文件夹。"""

    index: int
    name: str
    feed_address: str
    categories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImportItemResult:
    """不回传标题/地址，避免错误输入中夹带的凭据被报告带出。"""

    index: int
    status: Literal["created", "skipped", "failed"]
    code: str
    subscription_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class OpmlImportResult:
    """total 包括尚未处理的候选项；remaining 用于失败中断后的可恢复进度。"""

    total: int
    items: tuple[ImportItemResult, ...]

    @property
    def created(self) -> int:
        return sum(item.status == "created" for item in self.items)

    @property
    def skipped(self) -> int:
        return sum(item.status == "skipped" for item in self.items)

    @property
    def failed(self) -> int:
        return sum(item.status == "failed" for item in self.items)

    @property
    def remaining(self) -> int:
        return self.total - len(self.items)
