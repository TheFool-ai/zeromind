from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


def _normalize_rsshub_locator(raw: str) -> str:
    parsed = urlsplit(raw)
    if not parsed.netloc or not parsed.path or parsed.path == "/":
        raise ValueError("RSSHub locator must include a route")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("RSSHub locator must not contain credentials")
    try:
        if parsed.port is not None:
            raise ValueError("RSSHub locator must not contain a port")
    except ValueError as error:
        raise ValueError("RSSHub locator must not contain a port") from error
    if parsed.fragment:
        raise ValueError("RSSHub locator must not contain a fragment")
    if any(character.isspace() for character in raw):
        raise ValueError("RSSHub locator must not contain whitespace")
    if unquote(parsed.netloc) in {".", ".."} or any(
        unquote(segment) in {".", ".."} for segment in parsed.path.split("/")
    ):
        raise ValueError("RSSHub locator must not contain path traversal")
    return f"rsshub://{raw[9:]}"


def _normalize_http_feed_url(raw: str) -> str:
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("feed URL must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("feed URL must not contain credentials")

    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as error:
        raise ValueError("feed URL contains an invalid host or port") from error

    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def _normalize_feed_url(value: str) -> str:
    raw = value.strip()
    if raw[:9].lower() == "rsshub://":
        return _normalize_rsshub_locator(raw)
    return _normalize_http_feed_url(raw)


@dataclass(frozen=True, slots=True)
class FeedAddress:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalize_feed_url(self.value))

    @classmethod
    def parse(cls, raw: str) -> "FeedAddress":
        return cls(raw)

    @property
    def is_rsshub(self) -> bool:
        return self.value.startswith("rsshub://")
