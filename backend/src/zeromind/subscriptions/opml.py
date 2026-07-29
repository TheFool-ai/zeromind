from dataclasses import dataclass
from xml.etree.ElementTree import Element

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from zeromind.subscriptions.domain import normalize_feed_url

MAX_OPML_BYTES = 5 * 1024 * 1024


class InvalidOpmlError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OpmlEntry:
    title: str
    feed_url: str
    site_url: str | None
    categories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvalidOpmlEntry:
    title: str
    feed_url: str
    reason: str


@dataclass(frozen=True, slots=True)
class OpmlPreview:
    title: str | None
    entries: tuple[OpmlEntry, ...]
    invalid_entries: tuple[InvalidOpmlEntry, ...]
    duplicate_count: int


def _walk_outlines(
    parent: Element,
    categories: tuple[str, ...],
) -> list[tuple[Element, tuple[str, ...]]]:
    found: list[tuple[Element, tuple[str, ...]]] = []
    for outline in parent.findall("outline"):
        feed_url = outline.attrib.get("xmlUrl") or outline.attrib.get("xmlurl")
        if feed_url:
            found.append((outline, categories))
            continue
        label = (outline.attrib.get("title") or outline.attrib.get("text") or "").strip()
        child_categories = (*categories, label) if label else categories
        found.extend(_walk_outlines(outline, child_categories))
    return found


def preview_opml(data: bytes) -> OpmlPreview:
    if not data or len(data) > MAX_OPML_BYTES:
        raise InvalidOpmlError("OPML document is empty or exceeds 5 MiB")
    try:
        root = fromstring(data)
    except (DefusedXmlException, ValueError, SyntaxError) as error:
        raise InvalidOpmlError("OPML document contains invalid or unsafe XML") from error
    if root.tag.lower() != "opml":
        raise InvalidOpmlError("document root must be opml")
    body = root.find("body")
    if body is None:
        raise InvalidOpmlError("OPML document must contain a body")

    head_title = root.findtext("head/title")
    title = head_title.strip() if head_title and head_title.strip() else None
    entries: list[OpmlEntry] = []
    invalid: list[InvalidOpmlEntry] = []
    seen: set[str] = set()
    duplicates = 0

    for outline, categories in _walk_outlines(body, ()):
        raw_url = (outline.attrib.get("xmlUrl") or outline.attrib.get("xmlurl") or "").strip()
        entry_title = (
            outline.attrib.get("title") or outline.attrib.get("text") or raw_url
        ).strip()
        try:
            feed_url = normalize_feed_url(raw_url)
        except ValueError:
            invalid.append(InvalidOpmlEntry(entry_title, raw_url, "invalid_feed_url"))
            continue
        if feed_url in seen:
            duplicates += 1
            continue
        seen.add(feed_url)
        site_url = (outline.attrib.get("htmlUrl") or outline.attrib.get("htmlurl") or "").strip()
        entries.append(
            OpmlEntry(
                title=entry_title,
                feed_url=feed_url,
                site_url=site_url or None,
                categories=categories,
            )
        )

    return OpmlPreview(
        title=title,
        entries=tuple(entries),
        invalid_entries=tuple(invalid),
        duplicate_count=duplicates,
    )
