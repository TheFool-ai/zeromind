import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from zeromind.shared.models import Base
from zeromind.subscriptions.models import SubscriptionModel  # noqa: F401


class ContentReferenceModel(Base):
    __tablename__ = "content_references"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "identity_key",
            name="uq_content_reference_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    identity_key: Mapped[str] = mapped_column(String(2048), nullable=False)
    original_url: Mapped[str | None] = mapped_column(String(4096))
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReferenceRevisionModel(Base):
    __tablename__ = "reference_revisions"
    __table_args__ = (
        UniqueConstraint(
            "reference_id",
            "number",
            name="uq_reference_revision_number",
        ),
        UniqueConstraint(
            "reference_id",
            "fingerprint",
            name="uq_reference_revision_fingerprint",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_references.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str | None] = mapped_column(String(4096))
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

