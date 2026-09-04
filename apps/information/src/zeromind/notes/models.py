import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from zeromind.analysis.models import ContentAnalysisModel  # noqa: F401
from zeromind.ingestion.models import ContentReferenceModel  # noqa: F401
from zeromind.shared.models import Base


class NoteModel(Base):
    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_owner_reference", "owner_subject", "reference_id"),
        Index("ix_notes_owner_analysis", "owner_subject", "analysis_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_references.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_analyses.id", ondelete="SET NULL"),
    )
    owner_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
