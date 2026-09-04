import pytest

from zeromind.rsshub.credentials import CredentialCipher
from zeromind.rsshub.domain import RSSHubAuthenticationMode
from zeromind.rsshub.repository import InMemoryRSSHubInstanceRepository
from zeromind.rsshub.resolver import (
    RSSHubInstanceNotConfiguredError,
    RSSHubResolver,
)
from zeromind.rsshub.service import RSSHubInstanceService


async def configured_resolver(
    *,
    base_url: str = "https://rsshub.example.com",
    access_key: str | None = "instance-secret",
    authentication_mode: RSSHubAuthenticationMode = RSSHubAuthenticationMode.KEY,
) -> RSSHubResolver:
    repository = InMemoryRSSHubInstanceRepository()
    cipher = CredentialCipher("test-credential-secret")
    service = RSSHubInstanceService(repository, cipher)
    await service.create(
        name="Primary",
        base_url=base_url,
        access_key=access_key,
        authentication_mode=authentication_mode,
    )
    return RSSHubResolver(repository, cipher)


@pytest.mark.asyncio
async def test_resolver_appends_instance_key_and_preserves_route_query() -> None:
    resolver = await configured_resolver()

    resolved = await resolver.resolve(
        "rsshub://twitter/user/vista8?mode=full&key=locator-key&code=locator-code"
    )

    assert resolved == (
        "https://rsshub.example.com/twitter/user/vista8"
        "?mode=full&key=instance-secret"
    )


@pytest.mark.asyncio
async def test_resolver_supports_instance_prefix_and_code_authentication() -> None:
    resolver = await configured_resolver(
        base_url="https://rsshub.example.com/prefix",
        authentication_mode=RSSHubAuthenticationMode.CODE,
    )

    resolved = await resolver.resolve("rsshub://twitter/user/vista8")

    assert resolved == (
        "https://rsshub.example.com/prefix/twitter/user/vista8"
        "?code=b0a178d749b71df0528a1a2b3894ba40"
    )


@pytest.mark.asyncio
async def test_resolver_passes_direct_feed_without_instance() -> None:
    resolver = RSSHubResolver(
        InMemoryRSSHubInstanceRepository(),
        CredentialCipher("test-credential-secret"),
    )

    assert (
        await resolver.resolve("https://example.com/feed.xml")
        == "https://example.com/feed.xml"
    )


@pytest.mark.asyncio
async def test_resolver_requires_active_instance_for_rsshub_locator() -> None:
    resolver = RSSHubResolver(
        InMemoryRSSHubInstanceRepository(),
        CredentialCipher("test-credential-secret"),
    )

    with pytest.raises(RSSHubInstanceNotConfiguredError):
        await resolver.resolve("rsshub://twitter/user/vista8")
