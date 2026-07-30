"""Create canonical structured content analyses.

Revision ID: 0008_content_analyses
Revises: 0007_rsshub_instances
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_content_analyses"
down_revision: str | Sequence[str] | None = "0007_rsshub_instances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("reference_revision", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_definition_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_definition_version", sa.Integer(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("generated_status", sa.String(length=32), nullable=False),
        sa.Column("effective_decision", sa.String(length=16), nullable=False),
        sa.Column("source_name", sa.String(length=300), nullable=False),
        sa.Column("source_feed_url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("original_url", sa.String(length=4096), nullable=True),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("screening", sa.JSON(), nullable=False),
        sa.Column("primary_category", sa.String(length=160), nullable=True),
        sa.Column("secondary_categories", sa.JSON(), nullable=False),
        sa.Column("one_sentence_summary", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("viewpoints", sa.JSON(), nullable=False),
        sa.Column("key_quotes", sa.JSON(), nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=True),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("recommendation_level", sa.String(length=80), nullable=True),
        sa.Column("recommendation_reason", sa.Text(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["content_references.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_definition_id"],
            ["workflow_definitions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reference_id",
            "reference_revision",
            "workflow_definition_id",
            "workflow_definition_version",
            name="uq_content_analysis_identity",
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            name="uq_content_analysis_workflow_run",
        ),
    )
    op.create_index(
        "ix_content_analyses_reference_id",
        "content_analyses",
        ["reference_id"],
    )
    op.create_index(
        "ix_content_analyses_subscription_id",
        "content_analyses",
        ["subscription_id"],
    )
    op.create_index(
        "ix_content_analyses_workflow_definition_id",
        "content_analyses",
        ["workflow_definition_id"],
    )
    op.create_index(
        "ix_content_analyses_generated_status",
        "content_analyses",
        ["generated_status"],
    )
    op.create_index(
        "ix_content_analyses_effective_decision",
        "content_analyses",
        ["effective_decision"],
    )
    op.create_index(
        "ix_content_analyses_primary_category",
        "content_analyses",
        ["primary_category"],
    )
    op.create_index(
        "ix_content_analyses_total_score",
        "content_analyses",
        ["total_score"],
    )

    op.create_table(
        "content_analysis_tags",
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["content_analyses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("analysis_id", "tag"),
        sa.UniqueConstraint(
            "analysis_id",
            "tag",
            name="uq_content_analysis_tag",
        ),
    )
    op.create_index(
        "ix_content_analysis_tags_tag",
        "content_analysis_tags",
        ["tag"],
    )

    op.create_table(
        "analysis_decision_overrides",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["content_analyses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id",
            "sequence",
            name="uq_analysis_decision_override_sequence",
        ),
    )
    op.create_index(
        "ix_analysis_decision_overrides_analysis_id",
        "analysis_decision_overrides",
        ["analysis_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_decision_overrides_analysis_id",
        table_name="analysis_decision_overrides",
    )
    op.drop_table("analysis_decision_overrides")
    op.drop_index(
        "ix_content_analysis_tags_tag",
        table_name="content_analysis_tags",
    )
    op.drop_table("content_analysis_tags")
    op.drop_index(
        "ix_content_analyses_total_score",
        table_name="content_analyses",
    )
    op.drop_index(
        "ix_content_analyses_primary_category",
        table_name="content_analyses",
    )
    op.drop_index(
        "ix_content_analyses_effective_decision",
        table_name="content_analyses",
    )
    op.drop_index(
        "ix_content_analyses_generated_status",
        table_name="content_analyses",
    )
    op.drop_index(
        "ix_content_analyses_workflow_definition_id",
        table_name="content_analyses",
    )
    op.drop_index(
        "ix_content_analyses_subscription_id",
        table_name="content_analyses",
    )
    op.drop_index(
        "ix_content_analyses_reference_id",
        table_name="content_analyses",
    )
    op.drop_table("content_analyses")
