import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from zeromind.ingestion.models import ContentReferenceModel  # noqa: F401
from zeromind.shared.models import Base
from zeromind.subscriptions.models import SubscriptionModel  # noqa: F401
from zeromind.workflows.models import (  # noqa: F401
    WorkflowDefinitionModel,
    WorkflowRunModel,
)


class ContentAnalysisModel(Base):
    __tablename__ = "content_analyses"
    __table_args__ = (
        UniqueConstraint(
            "reference_id",
            "reference_revision",
            "workflow_definition_id",
            "workflow_definition_version",
            name="uq_content_analysis_identity",
        ),
        UniqueConstraint(
            "workflow_run_id",
            name="uq_content_analysis_workflow_run",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_references.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_definition_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generated_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    effective_decision: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(300), nullable=False)
    source_feed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    original_url: Mapped[str | None] = mapped_column(String(4096))
    author: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    screening: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    primary_category: Mapped[str | None] = mapped_column(String(160), index=True)
    secondary_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    one_sentence_summary: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    viewpoints: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        nullable=False,
    )
    key_quotes: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        nullable=False,
    )
    total_score: Mapped[int | None] = mapped_column(Integer, index=True)
    dimensions: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    recommendation_level: Mapped[str | None] = mapped_column(String(80))
    recommendation_reason: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class ContentAnalysisTagModel(Base):
    __tablename__ = "content_analysis_tags"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id",
            "tag",
            name="uq_content_analysis_tag",
        ),
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_analyses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag: Mapped[str] = mapped_column(
        String(80),
        primary_key=True,
        index=True,
    )


class AnalysisDecisionOverrideModel(Base):
    __tablename__ = "analysis_decision_overrides"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id",
            "sequence",
            name="uq_analysis_decision_override_sequence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
