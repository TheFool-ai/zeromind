from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from zeromind.content.network_policy import BlockedNetworkTarget, NetworkPolicy
from zeromind.content.resolver import ContentResolutionError, ContentResolver
from zeromind.ingestion.domain import ContentReference


def reference(url: str) -> ContentReference:
    return ContentReference(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
        identity_key="guid:42",
        original_url=url,
        current_revision=1,
        first_seen_at=datetime(2026, 7, 29, tzinfo=UTC),
        last_seen_at=datetime(2026, 7, 29, tzinfo=UTC),
    )


async def public_resolver(_: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.mark.asyncio
async def test_resolver_extracts_transient_document() -> None:
    html = b"""<!doctype html><html lang="en"><head>
      <title>Fallback title</title>
      <meta name="author" content="Ada Lovelace">
      <link rel="canonical" href="https://example.com/canonical">
    </head><body><article><h1>Meaningful title</h1>
      <p>This is a sufficiently meaningful article paragraph for extraction.</p>
      <p>It contains another sentence so the extractor can identify the main text.</p>
    </article></body></html>"""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=html,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    resolver = ContentResolver(
        network_policy=NetworkPolicy(resolver=public_resolver),
        transport=httpx.MockTransport(handler),
    )

    document = await resolver.resolve(reference("https://example.com/article"))

    assert "sufficiently meaningful article" in document.text
    assert document.author == "Ada Lovelace"
    assert document.source_url == "https://example.com/article"
    assert document.canonical_url == "https://example.com/canonical"


@pytest.mark.asyncio
async def test_resolver_revalidates_redirect_target() -> None:
    async def resolver(host: str) -> tuple[str, ...]:
        return ("127.0.0.1",) if host == "internal.example" else ("93.184.216.34",)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.example/secret"})

    content = ContentResolver(
        network_policy=NetworkPolicy(resolver=resolver),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(BlockedNetworkTarget):
        await content.resolve(reference("https://example.com/article"))


@pytest.mark.asyncio
async def test_resolver_rejects_non_html_and_oversized_content() -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                content=b'{"value": 1}',
                headers={"content-type": "application/json"},
            ),
            httpx.Response(
                200,
                content=b"x" * 101,
                headers={"content-type": "text/html"},
            ),
        ]
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        return next(responses)

    content = ContentResolver(
        network_policy=NetworkPolicy(resolver=public_resolver),
        transport=httpx.MockTransport(handler),
        max_bytes=100,
    )

    with pytest.raises(ContentResolutionError, match="content type"):
        await content.resolve(reference("https://example.com/data"))
    with pytest.raises(ContentResolutionError, match="size limit"):
        await content.resolve(reference("https://example.com/large"))
