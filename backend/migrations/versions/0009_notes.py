"""Create user-owned reading notes.

Revision ID: 0009_notes
Revises: 0008_content_analyses
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_notes"
down_revision: str | Sequence[str] | None = "0008_content_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("owner_subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["content_references.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["content_analyses.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notes_owner_reference",
        "notes",
        ["owner_subject", "reference_id"],
    )
    op.create_index(
        "ix_notes_owner_analysis",
        "notes",
        ["owner_subject", "analysis_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notes_owner_analysis", table_name="notes")
    op.drop_index("ix_notes_owner_reference", table_name="notes")
    op.drop_table("notes")
