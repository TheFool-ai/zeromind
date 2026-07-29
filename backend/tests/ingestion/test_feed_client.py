import httpx
import pytest

from zeromind.content.network_policy import BlockedNetworkTarget, NetworkPolicy
from zeromind.ingestion.feed_client import FeedClient, FeedNotModified


@pytest.mark.asyncio
async def test_feed_client_sends_conditional_headers_and_handles_304() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["if-none-match"] == '"v1"'
        assert request.headers["if-modified-since"] == "Tue, 28 Jul 2026 12:00:00 GMT"
        return httpx.Response(304)

    client = FeedClient(transport=httpx.MockTransport(handler))

    result = await client.fetch(
        "https://example.com/feed.xml",
        etag='"v1"',
        last_modified="Tue, 28 Jul 2026 12:00:00 GMT",
    )

    assert isinstance(result, FeedNotModified)


@pytest.mark.asyncio
async def test_feed_client_parses_rss_entries() -> None:
    rss = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Example</title>
      <item>
        <guid>post-42</guid>
        <title>Post 42</title>
        <link>https://example.com/42</link>
        <pubDate>Wed, 29 Jul 2026 08:00:00 GMT</pubDate>
        <description>Summary</description>
      </item>
    </channel></rss>"""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=rss,
            headers={"etag": '"v2"', "content-type": "application/rss+xml"},
        )

    client = FeedClient(transport=httpx.MockTransport(handler))

    result = await client.fetch("https://example.com/feed.xml")

    assert result.etag == '"v2"'
    assert result.entries[0].guid == "post-42"
    assert result.entries[0].title == "Post 42"
    assert result.entries[0].url == "https://example.com/42"


@pytest.mark.asyncio
async def test_feed_client_revalidates_redirects_against_ssrf_policy() -> None:
    async def addresses(host: str) -> tuple[str, ...]:
        return ("127.0.0.1",) if host == "internal.example" else ("93.184.216.34",)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "http://internal.example/feed"},
        )

    client = FeedClient(
        transport=httpx.MockTransport(handler),
        network_policy=NetworkPolicy(resolver=addresses),
    )

    with pytest.raises(BlockedNetworkTarget):
        await client.fetch("https://example.com/feed.xml")
