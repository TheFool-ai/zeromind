import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

AddressResolver = Callable[[str], Awaitable[tuple[str, ...]]]


class BlockedNetworkTarget(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    url: str
    host: str
    addresses: tuple[str, ...]


async def _resolve_host(host: str) -> tuple[str, ...]:
    def resolve() -> tuple[str, ...]:
        results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return tuple(sorted({str(item[4][0]) for item in results}))

    return await asyncio.to_thread(resolve)


class NetworkPolicy:
    def __init__(self, *, resolver: AddressResolver | None = None) -> None:
        self._resolver = resolver or _resolve_host

    async def validate_url(self, url: str) -> ValidatedTarget:
        parsed = urlsplit(url.strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            raise BlockedNetworkTarget("only public http and https URLs are allowed")
        if not parsed.hostname:
            raise BlockedNetworkTarget("URL must include a host")
        if parsed.username is not None or parsed.password is not None:
            raise BlockedNetworkTarget("URL credentials are not allowed")

        host = parsed.hostname.lower()
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            try:
                addresses = await self._resolver(host)
            except OSError as error:
                raise BlockedNetworkTarget("host could not be resolved") from error
        else:
            addresses = (str(literal),)

        if not addresses:
            raise BlockedNetworkTarget("host did not resolve to an address")
        for address in addresses:
            try:
                parsed_address = ipaddress.ip_address(address)
            except ValueError as error:
                raise BlockedNetworkTarget("resolver returned an invalid address") from error
            if not parsed_address.is_global:
                raise BlockedNetworkTarget(
                    f"destination address {parsed_address} is not public"
                )
        return ValidatedTarget(url=url.strip(), host=host, addresses=addresses)

