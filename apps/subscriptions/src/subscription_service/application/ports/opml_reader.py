"""应用层只依赖解析端口，不引用 XML 库或基础设施实现。"""

from typing import Protocol

from subscription_service.application.dto.opml_import import OpmlEntry


class OpmlReader(Protocol):
    def parse(self, content: bytes) -> tuple[OpmlEntry, ...]:
        """完整安全解析后才返回候选项；非法文件抛 InvalidOpmlError，无网络访问。"""
        ...
