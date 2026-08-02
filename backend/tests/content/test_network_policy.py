import pytest

from zeromind.content.network_policy import BlockedNetworkTarget, NetworkPolicy


async def public_resolver(_: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.mark.asyncio
async def test_network_policy_accepts_public_http_destination() -> None:
    policy = NetworkPolicy(resolver=public_resolver)

    target = await policy.validate_url("https://example.com/article")

    assert target.url == "https://example.com/article"
    assert target.addresses == ("93.184.216.34",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "169.254.169.254",
        "::1",
        "fc00::1",
    ],
)
async def test_network_policy_rejects_non_public_dns_results(address: str) -> None:
    async def resolver(_: str) -> tuple[str, ...]:
        return (address,)

    policy = NetworkPolicy(resolver=resolver)

    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("https://example.com/article")


@pytest.mark.asyncio
async def test_network_policy_rejects_credentials_and_non_http_schemes() -> None:
    policy = NetworkPolicy(resolver=public_resolver)

    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("https://user:secret@example.com/article")
    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_network_policy_accepts_private_address_for_exact_trusted_host() -> None:
    async def private_resolver(_: str) -> tuple[str, ...]:
        return ("172.20.0.8",)

    policy = NetworkPolicy(
        resolver=private_resolver,
        private_host_allowlist={"RSSHUB."},
    )

    target = await policy.validate_url("http://rsshub:1200/test/1")

    assert target.host == "rsshub"
    assert target.addresses == ("172.20.0.8",)


@pytest.mark.asyncio
async def test_network_policy_rejects_private_address_for_untrusted_host() -> None:
    async def private_resolver(_: str) -> tuple[str, ...]:
        return ("172.20.0.8",)

    policy = NetworkPolicy(
        resolver=private_resolver,
        private_host_allowlist={"rsshub"},
    )

    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("http://postgres:5432/")


@pytest.mark.asyncio
async def test_network_policy_does_not_allow_private_ip_literals() -> None:
    policy = NetworkPolicy(private_host_allowlist={"172.20.0.8"})

    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("http://172.20.0.8:1200/test/1")


@pytest.mark.asyncio
async def test_network_policy_requires_explicit_private_host_allowlist() -> None:
    async def private_resolver(_: str) -> tuple[str, ...]:
        return ("172.20.0.8",)

    policy = NetworkPolicy(resolver=private_resolver)

    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("http://rsshub:1200/test/1")
