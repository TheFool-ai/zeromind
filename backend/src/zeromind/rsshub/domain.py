import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import unquote, urlsplit, urlunsplit


class DuplicateRSSHubInstanceError(ValueError):
    pass


class RSSHubInstanceInUseError(ValueError):
    pass


class RSSHubAuthenticationMode(StrEnum):
    KEY = "key"
    CODE = "code"


def normalize_instance_base_url(value: str) -> str:
    raw = value.strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("RSSHub base URL must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("RSSHub base URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("RSSHub base URL must not contain a query or fragment")
    if any(character.isspace() for character in raw):
        raise ValueError("RSSHub base URL must not contain whitespace")
    if any(unquote(segment) in {".", ".."} for segment in parsed.path.split("/")):
        raise ValueError("RSSHub base URL must not contain path traversal")

    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as error:
        raise ValueError("RSSHub base URL contains an invalid host or port") from error

    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


@dataclass(slots=True)
class RSSHubInstance:
    id: uuid.UUID
    name: str
    base_url: str
    encrypted_access_key: str | None
    authentication_mode: RSSHubAuthenticationMode
    enabled: bool
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        name: str,
        base_url: str,
        encrypted_access_key: str | None = None,
        authentication_mode: RSSHubAuthenticationMode = RSSHubAuthenticationMode.KEY,
        enabled: bool = True,
        active: bool = False,
        now: datetime | None = None,
    ) -> "RSSHubInstance":
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("RSSHub instance name is required")
        current = now or datetime.now(UTC)
        return cls(
            id=uuid.uuid4(),
            name=clean_name,
            base_url=normalize_instance_base_url(base_url),
            encrypted_access_key=encrypted_access_key,
            authentication_mode=authentication_mode,
            enabled=enabled,
            active=active,
            created_at=current,
            updated_at=current,
        )

    def update(
        self,
        *,
        name: str,
        base_url: str,
        encrypted_access_key: str | None,
        authentication_mode: RSSHubAuthenticationMode,
        enabled: bool,
        now: datetime | None = None,
    ) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("RSSHub instance name is required")
        self.name = clean_name
        self.base_url = normalize_instance_base_url(base_url)
        self.encrypted_access_key = encrypted_access_key
        self.authentication_mode = authentication_mode
        self.enabled = enabled
        self.updated_at = now or datetime.now(UTC)
