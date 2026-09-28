"""来源地址规范化；仅检查语法，DNS 和内网访问策略由网络适配器负责。"""

import re
from dataclasses import dataclass
from ipaddress import IPv6Address
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


def _normalize(raw: str) -> str:
    raw = raw.strip()
    if not raw or len(raw) > 2048 or any(c.isspace() or ord(c) < 32 for c in raw):
        raise ValueError("来源地址为空、过长或包含空白")
    if "\\" in raw:
        raise ValueError("来源地址不能包含反斜杠")
    parsed = urlsplit(raw)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("来源地址不能包含用户名或密码")
    scheme = parsed.scheme.lower()
    if scheme == "rsshub":
        if not parsed.netloc or not parsed.path or parsed.path == "/":
            raise ValueError("RSSHub 地址必须包含完整路由")
        if ":" in parsed.netloc or parsed.fragment:
            raise ValueError("RSSHub 路由不能包含端口或片段")
        decoded = unquote(parsed.netloc + parsed.path)
        if any(p in {".", ".."} for p in decoded.split("/")) or "\\" in decoded:
            raise ValueError("RSSHub 路由不能包含路径穿越")
        if any(c.isspace() or ord(c) < 32 for c in decoded):
            raise ValueError("RSSHub 路由不能包含编码的空白")
        if any(k.lower() in {"key", "code"} for k, _ in parse_qsl(parsed.query)):
            raise ValueError("RSSHub 认证参数不能保存在订阅地址中")
        return "rsshub://" + raw[9:]
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Feed 地址必须使用 HTTP 或 HTTPS")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{IPv6Address(host)}]"
    elif not re.fullmatch(r"[a-z0-9.-]+", host):
        raise ValueError("来源主机名不合法")
    port = parsed.port  # urllib 同时校验端口范围。
    if port == 0:
        raise ValueError("端口不能为零")
    default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    authority = host if port is None or default else f"{host}:{port}"
    result = urlunsplit(
        (
            scheme,
            authority,
            parsed.path or "/",
            urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True))),
            "",
        )
    )
    if len(result) > 2048:
        raise ValueError("规范化地址不能超过 2048 字符")
    return result


@dataclass(frozen=True, slots=True)
class FeedAddress:
    """按规范化地址比较；直接构造和 parse 均执行相同校验。"""

    value: str  # 来源抓取地址或逻辑 RSSHub 路由，不保存实例配置。

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalize(self.value))

    @classmethod
    def parse(cls, raw: str) -> "FeedAddress":
        """解析手动录入或 OPML 地址；非法输入抛出 ValueError，不访问网络。"""
        return cls(raw)

    @property
    def is_rsshub(self) -> bool:
        """是否为逻辑 RSSHub 路由，实际服务器由部署配置决定。"""
        return self.value.startswith("rsshub://")
