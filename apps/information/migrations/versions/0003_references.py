"""Create content references and RSS metadata revisions.

Revision ID: 0003_references
Revises: 0002_subscriptions
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_references"
down_revision: str | Sequence[str] | None = "0002_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("identity_key", sa.String(length=2048), nullable=False),
        sa.Column("original_url", sa.String(length=4096), nullable=True),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id",
            "identity_key",
            name="uq_content_reference_identity",
        ),
    )
    op.create_index(
        op.f("ix_content_references_subscription_id"),
        "content_references",
        ["subscription_id"],
        unique=False,
    )
    op.create_table(
        "reference_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=4096), nullable=True),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["content_references.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reference_id",
            "fingerprint",
            name="uq_reference_revision_fingerprint",
        ),
        sa.UniqueConstraint(
            "reference_id",
            "number",
            name="uq_reference_revision_number",
        ),
    )
    op.create_index(
        op.f("ix_reference_revisions_reference_id"),
        "reference_revisions",
        ["reference_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_reference_revisions_reference_id"),
        table_name="reference_revisions",
    )
    op.drop_table("reference_revisions")
    op.drop_index(
        op.f("ix_content_references_subscription_id"),
        table_name="content_references",
    )
    op.drop_table("content_references")
