"""不依赖框架的通用领域校验；时间统一成 UTC 后参与比较。"""

from datetime import UTC, datetime


def utc_time(value: datetime) -> datetime:
    """拒绝无时区时间，避免服务器时区影响业务结果。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return value.astimezone(UTC)


def positive(value: int, name: str) -> None:
    """版本必须是正整数，布尔值不能作为版本。"""
    if type(value) is not int or value < 1:
        raise ValueError(f"{name}必须为正整数")


def clean_name(value: str) -> str:
    """名称去首尾空白，长度上限与表结构保持一致。"""
    value = value.strip()
    if not value or len(value) > 300:
        raise ValueError("名称长度必须为 1 到 300")
    return value


def clean_categories(values: tuple[str, ...]) -> tuple[str, ...]:
    """保留输入顺序去重；空分类忽略，单个分类最多 160 字符。"""
    result = tuple(dict.fromkeys(v.strip() for v in values if v.strip()))
    if any(len(v) > 160 for v in result):
        raise ValueError("分类不能超过 160 字符")
    return result
