import hashlib
from urllib.parse import quote_plus, unquote_plus

from zeromind.rsshub.credentials import CredentialCipher
from zeromind.rsshub.domain import RSSHubAuthenticationMode
from zeromind.rsshub.repository import RSSHubInstanceRepository
from zeromind.subscriptions.domain import normalize_feed_url


class RSSHubInstanceNotConfiguredError(ValueError):
    pass


def _without_authentication_query(query: str) -> list[str]:
    result: list[str] = []
    for item in query.split("&"):
        if not item:
            continue
        name = unquote_plus(item.partition("=")[0]).lower()
        if name not in {"key", "code"}:
            result.append(item)
    return result


class RSSHubResolver:
    def __init__(
        self,
        repository: RSSHubInstanceRepository,
        cipher: CredentialCipher,
    ) -> None:
        self._repository = repository
        self._cipher = cipher

    async def resolve(self, locator: str) -> str:
        if locator[:9].lower() != "rsshub://":
            return locator

        normalized = normalize_feed_url(locator)
        instance = await self._repository.get_active()
        if instance is None or not instance.enabled:
            raise RSSHubInstanceNotConfiguredError(
                "no active RSSHub instance is configured"
            )

        route_and_query = normalized[9:]
        route, separator, raw_query = route_and_query.partition("?")
        query = _without_authentication_query(raw_query if separator else "")
        if instance.encrypted_access_key:
            access_key = self._cipher.decrypt(instance.encrypted_access_key)
            if instance.authentication_mode is RSSHubAuthenticationMode.KEY:
                query.append(f"key={quote_plus(access_key)}")
            else:
                digest = hashlib.md5(  # noqa: S324 - RSSHub protocol requires MD5
                    f"/{route}{access_key}".encode()
                ).hexdigest()
                query.append(f"code={digest}")

        resolved = f"{instance.base_url}/{route}"
        return f"{resolved}?{'&'.join(query)}" if query else resolved
