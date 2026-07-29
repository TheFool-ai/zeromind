from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
import trafilatura
from lxml import html as lxml_html

from zeromind.content.network_policy import NetworkPolicy
from zeromind.ingestion.domain import ContentReference

REDIRECT_CODES = {301, 302, 303, 307, 308}


class ContentResolutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedDocument:
    reference_id: str
    source_url: str
    final_url: str
    canonical_url: str | None
    title: str | None
    author: str | None
    language: str | None
    text: str


def _first(values: list[str]) -> str | None:
    for value in values:
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _html_metadata(content: str) -> tuple[str | None, str | None, str | None, str | None]:
    try:
        root = lxml_html.fromstring(content)
    except (ValueError, TypeError):
        return None, None, None, None
    title = _first([str(value) for value in root.xpath("//title/text()")])
    author = _first(
        [
            str(value)
            for value in root.xpath(
                "//meta[translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')="
                "'author']/@content"
            )
        ]
    )
    canonical = _first(
        [
            str(value)
            for value in root.xpath(
                "//link[contains(concat(' ', normalize-space(@rel), ' '), "
                "' canonical ')]/@href"
            )
        ]
    )
    language = _first([str(value) for value in root.xpath("/html/@lang")])
    return title, author, canonical, language


class ContentResolver:
    def __init__(
        self,
        *,
        network_policy: NetworkPolicy,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 20,
        max_bytes: int = 5 * 1024 * 1024,
        max_redirects: int = 5,
    ) -> None:
        self._policy = network_policy
        self._transport = transport
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects

    async def resolve(self, reference: ContentReference) -> ResolvedDocument:
        if not reference.original_url:
            raise ContentResolutionError("reference has no original URL")
        source_url = reference.original_url
        current_url = source_url

        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            follow_redirects=False,
            headers={
                "accept": "text/html, application/xhtml+xml",
                "user-agent": "ZeroMind/0.1 (+https://github.com/zeromind)",
            },
        ) as client:
            for redirect_count in range(self._max_redirects + 1):
                await self._policy.validate_url(current_url)
                request = client.build_request("GET", current_url)
                response = await client.send(request, stream=True)
                try:
                    if response.status_code in REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise ContentResolutionError(
                                "redirect response has no location"
                            )
                        if redirect_count == self._max_redirects:
                            raise ContentResolutionError("redirect limit exceeded")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if not (
                        content_type.startswith("text/html")
                        or content_type.startswith("application/xhtml+xml")
                    ):
                        raise ContentResolutionError("unsupported content type")
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self._max_bytes:
                        raise ContentResolutionError("content exceeds size limit")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            raise ContentResolutionError("content exceeds size limit")
                    encoding = response.encoding or "utf-8"
                    html = bytes(body).decode(encoding, errors="replace")
                    return self._extract(
                        reference=reference,
                        source_url=source_url,
                        final_url=current_url,
                        html=html,
                    )
                finally:
                    await response.aclose()
        raise ContentResolutionError("content resolution ended unexpectedly")

    def _extract(
        self,
        *,
        reference: ContentReference,
        source_url: str,
        final_url: str,
        html: str,
    ) -> ResolvedDocument:
        extracted = trafilatura.bare_extraction(
            html,
            url=final_url,
            with_metadata=True,
            include_comments=False,
            include_tables=False,
        )
        if extracted is None:
            raise ContentResolutionError("main article text could not be extracted")
        data = extracted if isinstance(extracted, dict) else extracted.as_dict()
        text = str(data.get("text") or "").strip()
        if not text:
            raise ContentResolutionError("main article text is empty")
        html_title, html_author, html_canonical, html_language = _html_metadata(html)
        canonical = str(data.get("url") or html_canonical or "").strip() or None
        return ResolvedDocument(
            reference_id=str(reference.id),
            source_url=source_url,
            final_url=final_url,
            canonical_url=canonical,
            title=str(data.get("title") or html_title or "").strip() or None,
            author=str(data.get("author") or html_author or "").strip() or None,
            language=str(data.get("language") or html_language or "").strip() or None,
            text=text,
        )
