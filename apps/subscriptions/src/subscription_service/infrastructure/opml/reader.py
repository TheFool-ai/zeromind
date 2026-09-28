"""受限 OPML 解析：先完整验证文件，再产生来源候选项，不进行网络请求。"""

from io import BytesIO
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from subscription_service.application.dto.opml_import import (
    MAX_OPML_BYTES,
    MAX_OPML_OUTLINES,
    MAX_XML_DEPTH,
    MAX_XML_ELEMENTS,
    OpmlEntry,
)
from subscription_service.application.opml_errors import InvalidOpmlError, OpmlTooLargeError


class SafeOpmlReader:
    """接受无命名空间的标准 OPML；拒绝 DTD、实体和外部引用，包括 UTF-16 输入。"""

    def parse(self, content: bytes) -> tuple[OpmlEntry, ...]:
        if len(content) > MAX_OPML_BYTES:
            raise OpmlTooLargeError("OPML 文件不能超过 1 MiB")
        try:
            events = ElementTree.iterparse(
                BytesIO(content),
                events=("start", "end"),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
            depth = outlines = elements = 0
            for event, node in events:
                if event == "start":
                    depth += 1
                    elements += 1
                    outlines += node.tag == "outline"
                    if (
                        depth > MAX_XML_DEPTH
                        or outlines > MAX_OPML_OUTLINES
                        or elements > MAX_XML_ELEMENTS
                    ):
                        raise InvalidOpmlError("OPML 层级或节点数量超过限制")
                else:
                    depth -= 1
            root = events.root
        except (ParseError, DefusedXmlException, LookupError, ValueError) as exc:
            # 解析器的底层消息可能含输入片段，不向接口透传。
            raise InvalidOpmlError("OPML 格式非法或包含不安全的 XML 结构") from exc

        if (
            root.tag != "opml"
            or len(root.findall("body")) != 1
            or len(root.findall("head")) > 1
            or any(child.tag not in {"head", "body"} for child in root)
        ):
            raise InvalidOpmlError("OPML 必须包含一个 body 和至多一个 head")
        body = root.find("body")
        assert body is not None
        if any(node.tag != "outline" for child in body for node in child.iter()):
            raise InvalidOpmlError("OPML body 只能包含 outline")

        entries: list[OpmlEntry] = []

        def visit(node: Element, parents: tuple[str, ...]) -> None:
            label = node.get("title", "").strip() or node.get("text", "").strip()
            is_feed = "xmlUrl" in node.attrib or node.get("type", "").lower() in {"rss", "atom"}
            if is_feed:
                categories = parents + tuple(node.get("category", "").split(","))
                entries.append(
                    OpmlEntry(
                        index=len(entries) + 1,
                        name=label,
                        feed_address=node.get("xmlUrl", ""),
                        categories=categories,
                    )
                )
            # 只有文件夹名称继承为子节点分类，Feed 自己的标题不是分类。
            child_parents = parents + (label,) if not is_feed and label else parents
            for child in node:
                visit(child, child_parents)

        for child in body:
            visit(child, ())
        return tuple(entries)
