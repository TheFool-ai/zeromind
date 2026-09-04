import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from zeromind.shared.models import Base


class RSSHubInstanceModel(Base):
    __tablename__ = "rsshub_instances"
    __table_args__ = (
        Index(
            "uq_rsshub_instances_active",
            "active",
            unique=True,
            postgresql_where=text("active"),
            sqlite_where=text("active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    encrypted_access_key: Mapped[str | None] = mapped_column(Text)
    authentication_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
