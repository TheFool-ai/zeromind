import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
from time import struct_time
from typing import Any

import feedparser
import httpx

from zeromind.ingestion.domain import FeedEntry

MAX_FEED_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class FeedNotModified:
    status_code: int = 304


@dataclass(frozen=True, slots=True)
class FeedDocument:
    entries: tuple[FeedEntry, ...]
    etag: str | None
    last_modified: str | None


def _parsed_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def _string(entry: dict[str, Any], key: str) -> str | None:
    value = entry.get(key)
    return str(value).strip() if value is not None and str(value).strip() else None


def _optional(entry: dict[str, Any], key: str) -> Any:
    try:
        return entry[key]
    except KeyError:
        return None


class FeedClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        self._transport = transport
        self._timeout = timeout_seconds

    async def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FeedDocument | FeedNotModified:
        headers = {
            "accept": (
                "application/atom+xml, application/rss+xml, application/xml, text/xml"
            ),
            "user-agent": "ZeroMind/0.1 (+https://github.com/zeromind)",
        }
        if etag:
            headers["if-none-match"] = etag
        if last_modified:
            headers["if-modified-since"] = last_modified

        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 304:
            return FeedNotModified()
        response.raise_for_status()
        if len(response.content) > MAX_FEED_BYTES:
            raise ValueError("feed exceeds 10 MiB")

        parsed = feedparser.parse(response.content)
        entries = tuple(
            FeedEntry(
                guid=_string(entry, "id") or _string(entry, "guid"),
                url=_string(entry, "link"),
                title=_string(entry, "title") or "(untitled)",
                summary=_string(entry, "summary") or _string(entry, "description"),
                author=_string(entry, "author"),
                published_at=_parsed_datetime(entry.get("published_parsed")),
                updated_at=_parsed_datetime(_optional(entry, "updated_parsed")),
            )
            for entry in parsed.entries
        )
        return FeedDocument(
            entries=entries,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )
