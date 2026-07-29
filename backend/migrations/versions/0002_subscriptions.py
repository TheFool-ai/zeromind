"""Create RSS subscriptions.

Revision ID: 0002_subscriptions
Revises: 0001_bootstrap
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_subscriptions"
down_revision: str | Sequence[str] | None = "0001_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("feed_url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("site_url", sa.String(length=2048), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("health", sa.String(length=32), nullable=False),
        sa.Column("etag", sa.String(length=1024), nullable=True),
        sa.Column("last_modified", sa.String(length=255), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_url"),
    )
    op.create_index(
        op.f("ix_subscriptions_next_poll_at"),
        "subscriptions",
        ["next_poll_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_subscriptions_next_poll_at"), table_name="subscriptions")
    op.drop_table("subscriptions")
