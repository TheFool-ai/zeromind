import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from zeromind.shared.models import Base


class SubscriptionModel(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    feed_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    site_url: Mapped[str | None] = mapped_column(String(2048))
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    health: Mapped[str] = mapped_column(String(32), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(1024))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_poll_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
