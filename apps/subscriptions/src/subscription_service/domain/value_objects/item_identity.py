"""来源内的去重身份，与内部条目 UUID 分开。"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ItemIdentity:
    """同一来源内按 kind/value 去重；不执行跨来源文章合并。"""

    kind: Literal["guid", "url", "hash"]  # GUID、规范化链接或兜底哈希。
    value: str  # 非空身份原值，数据库使用其哈希索引以避免超长索引。

    def __post_init__(self) -> None:
        if self.kind not in {"guid", "url", "hash"} or not self.value.strip():
            raise ValueError("条目身份类型或值不合法")
        object.__setattr__(self, "value", self.value.strip())
