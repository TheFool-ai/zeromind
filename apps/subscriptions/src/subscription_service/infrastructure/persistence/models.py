"""订阅服务独立表结构；ORM 模型不是领域实体。

row_version 仅用于乐观锁，与配置版本、地址版本和条目修订号分开。
长地址和条目身份使用 SHA-256 唯一索引，避免 PostgreSQL B-tree 超长键限制。
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from subscription_service.domain.validation import utc_time


class UTCDateTime(TypeDecorator):
    """PostgreSQL 使用 timestamptz；SQLite 无时区结果显式还原为 UTC。"""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return utc_time(value) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    """仅包含订阅服务的数据表。"""


class SubscriptionModel(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("configuration_version >= 1", name="ck_subscription_config_version"),
        CheckConstraint("address_version >= 1", name="ck_subscription_address_version"),
        CheckConstraint("row_version >= 1", name="ck_subscription_row_version"),
        Index("uq_subscription_address", "address_digest", unique=True),
        Index("ix_subscription_created", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    feed_address: Mapped[str] = mapped_column(String(2048))
    address_digest: Mapped[str] = mapped_column(String(64))
    categories: Mapped[list[str]] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean)
    configuration_version: Mapped[int] = mapped_column(Integer)
    address_version: Mapped[int] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_successful_fetch_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": row_version}


class SubscriptionItemModel(Base):
    __tablename__ = "subscription_items"
    __table_args__ = (
        CheckConstraint("identity_kind IN ('guid', 'url', 'hash')", name="ck_item_identity_kind"),
        CheckConstraint("current_revision >= 1", name="ck_item_revision"),
        CheckConstraint("row_version >= 1", name="ck_item_row_version"),
        Index(
            "uq_item_identity", "subscription_id", "identity_kind", "identity_digest", unique=True
        ),
        Index("ix_item_source_seen", "subscription_id", "first_seen_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("subscriptions.id", ondelete="RESTRICT")
    )
    identity_kind: Mapped[str] = mapped_column(String(10))
    identity_value: Mapped[str] = mapped_column(Text)
    identity_digest: Mapped[str] = mapped_column(String(64))
    current_revision: Mapped[int] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": row_version}


class ItemRevisionModel(Base):
    __tablename__ = "item_revisions"
    __table_args__ = (CheckConstraint("revision_number >= 1", name="ck_revision_number"),)

    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("subscription_items.id", ondelete="RESTRICT"), primary_key=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    original_url: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    metadata_fingerprint: Mapped[str] = mapped_column(String(64))
