"""Feed 元数据值对象，不包含网页正文、AI 分析或本地观察时间。"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from subscription_service.domain.validation import utc_time
from subscription_service.domain.value_objects.feed_address import FeedAddress


@dataclass(frozen=True, slots=True)
class ItemMetadata:
    """保留输入快照，规范化时返回副本；相同内容的指纹稳定。"""

    title: str  # 来源标题；缺失标题规范化为 (untitled)。
    original_url: str | None  # 文章链接，只接受 HTTP/HTTPS，可为空。
    summary: str | None  # Feed 自带摘要，不是 AI 摘要。
    author: str | None  # 来源作者。
    published_at: datetime | None  # 来源发布时间。
    source_updated_at: datetime | None  # 来源声明的更新时间。

    def normalized(self) -> "ItemMetadata":
        """去首尾空白、统一空值、规范化链接和时区，不请求网页或推测缺失时间。"""

        def optional(value: str | None) -> str | None:
            return (value.strip() or None) if value is not None else None

        url = optional(self.original_url)
        if url:
            address = FeedAddress(url)
            if address.is_rsshub:
                raise ValueError("文章链接必须是 HTTP/HTTPS")
            url = address.value
        return ItemMetadata(
            self.title.strip() or "(untitled)",
            url,
            optional(self.summary),
            optional(self.author),
            utc_time(self.published_at) if self.published_at is not None else None,
            utc_time(self.source_updated_at) if self.source_updated_at is not None else None,
        )

    def fingerprint(self) -> str:
        """稳定 SHA-256；字段顺序固定，时间使用 UTC，不包含本地抓取信息。"""
        value = self.normalized()
        content = [
            value.title,
            value.original_url,
            value.summary,
            value.author,
            value.published_at.isoformat() if value.published_at else None,
            value.source_updated_at.isoformat() if value.source_updated_at else None,
        ]
        return hashlib.sha256(
            json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()

    def has_same_content_as(self, other: "ItemMetadata") -> bool:
        """比较规范化内容；表示形式差异不创建新版本。"""
        return self.normalized() == other.normalized()
