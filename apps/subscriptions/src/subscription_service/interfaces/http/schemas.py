"""HTTP 请求和响应契约，与领域类型隔离；拒绝未知字段和隐式类型转换。"""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateSubscriptionRequest(RequestModel):
    name: str = Field(min_length=1, max_length=300, description="来源展示名称")
    feed_address: str = Field(min_length=1, max_length=2048, description="Feed 或 RSSHub 路由")
    categories: list[str] = Field(default_factory=list, description="来源分类")


class VersionRequest(RequestModel):
    expected_configuration_version: int | None = Field(
        default=None, ge=1, description="可选：调用者读取到的配置版本，过期返回 409"
    )


class UpdateSubscriptionRequest(VersionRequest):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    feed_address: str | None = Field(default=None, min_length=1, max_length=2048)
    categories: list[str] | None = None

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        """遗漏字段保留原值；显式 null 容易产生歧义，因此拒绝，[] 可清空分类。"""
        changes = self.model_fields_set & {"name", "feed_address", "categories"}
        if not changes or any(getattr(self, field) is None for field in changes):
            raise ValueError("至少提供一个非 null 的修改字段")
        return self


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    feed_address: str
    categories: tuple[str, ...]
    enabled: bool
    configuration_version: int
    address_version: int
    last_successful_fetch_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubscriptionListResponse(BaseModel):
    items: list[SubscriptionResponse]
    limit: int
    offset: int
