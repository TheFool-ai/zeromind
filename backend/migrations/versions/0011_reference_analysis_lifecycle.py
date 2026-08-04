"""Add the current analysis lifecycle to content references.

Revision ID: 0011_reference_analysis_lifecycle
Revises: 0010_agent_versions_and_sessions
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_reference_analysis_lifecycle"
down_revision: str | Sequence[str] | None = "0010_agent_versions_and_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANALYSIS_STATUSES = (
    "pending",
    "queued",
    "screening",
    "resolving",
    "analyzing",
    "classifying",
    "scoring",
    "reviewing",
    "finalizing",
    "initial_rejected",
    "fine_rejected",
    "completed",
    "failed",
)


def upgrade() -> None:
    op.add_column(
        "content_references",
        sa.Column("analysis_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "content_references",
        sa.Column("analysis_status_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_references",
        sa.Column("analysis_workflow_run_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "content_references",
        sa.Column("analysis_error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "content_references",
        sa.Column("analysis_error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "content_references",
        sa.Column(
            "analysis_status_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "content_references",
        sa.Column("analysis_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_references",
        sa.Column("analysis_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE content_references
            SET analysis_status = 'pending',
                analysis_status_revision = current_revision,
                analysis_status_updated_at = CURRENT_TIMESTAMP
            """
        )
    )
    for column in (
        "analysis_status",
        "analysis_status_revision",
        "analysis_status_updated_at",
    ):
        op.alter_column("content_references", column, nullable=False)
    quoted = ", ".join(f"'{value}'" for value in ANALYSIS_STATUSES)
    op.create_check_constraint(
        "ck_content_reference_analysis_status",
        "content_references",
        f"analysis_status IN ({quoted})",
    )
    op.create_foreign_key(
        "fk_content_references_analysis_workflow_run_id",
        "content_references",
        "workflow_runs",
        ["analysis_workflow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for column in (
        "analysis_status",
        "analysis_status_updated_at",
        "analysis_workflow_run_id",
    ):
        op.create_index(
            op.f(f"ix_content_references_{column}"),
            "content_references",
            [column],
        )


def downgrade() -> None:
    for column in (
        "analysis_workflow_run_id",
        "analysis_status_updated_at",
        "analysis_status",
    ):
        op.drop_index(
            op.f(f"ix_content_references_{column}"),
            table_name="content_references",
        )
    op.drop_constraint(
        "fk_content_references_analysis_workflow_run_id",
        "content_references",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_content_reference_analysis_status",
        "content_references",
        type_="check",
    )
    for column in (
        "analysis_completed_at",
        "analysis_started_at",
        "analysis_status_updated_at",
        "analysis_error_message",
        "analysis_error_code",
        "analysis_workflow_run_id",
        "analysis_status_revision",
        "analysis_status",
    ):
        op.drop_column("content_references", column)
