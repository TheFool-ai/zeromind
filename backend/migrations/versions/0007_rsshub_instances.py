"""Create RSSHub instance registry.

Revision ID: 0007_rsshub_instances
Revises: 0006_jobs_webhooks
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_rsshub_instances"
down_revision: str | Sequence[str] | None = "0006_jobs_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rsshub_instances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("encrypted_access_key", sa.Text(), nullable=True),
        sa.Column("authentication_mode", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("base_url"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "uq_rsshub_instances_active",
        "rsshub_instances",
        ["active"],
        unique=True,
        postgresql_where=sa.text("active"),
        sqlite_where=sa.text("active = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_rsshub_instances_active", table_name="rsshub_instances")
    op.drop_table("rsshub_instances")
