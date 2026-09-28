"""建立独立订阅服务的来源、条目和不可变修订表。

此迁移仅针对新服务数据库，不自动复制或修改归档项目的数据。
历史迁移不导入当前 ORM，以免未来模型变更改写已发布的迁移语义。
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_subscription_domain"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("feed_address", sa.String(2048), nullable=False),
        sa.Column("address_digest", sa.String(64), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("address_version", sa.Integer(), nullable=False),
        sa.Column("etag", sa.Text()),
        sa.Column("last_modified", sa.Text()),
        sa.Column("last_successful_fetch_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("configuration_version >= 1", name="ck_subscription_config_version"),
        sa.CheckConstraint("address_version >= 1", name="ck_subscription_address_version"),
        sa.CheckConstraint("row_version >= 1", name="ck_subscription_row_version"),
    )
    op.create_index("uq_subscription_address", "subscriptions", ["address_digest"], unique=True)
    op.create_index("ix_subscription_created", "subscriptions", ["created_at", "id"])
    op.create_table(
        "subscription_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Uuid(),
            sa.ForeignKey("subscriptions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("identity_kind", sa.String(10), nullable=False),
        sa.Column("identity_value", sa.Text(), nullable=False),
        sa.Column("identity_digest", sa.String(64), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "identity_kind IN ('guid', 'url', 'hash')", name="ck_item_identity_kind"
        ),
        sa.CheckConstraint("current_revision >= 1", name="ck_item_revision"),
        sa.CheckConstraint("row_version >= 1", name="ck_item_row_version"),
    )
    op.create_index(
        "uq_item_identity",
        "subscription_items",
        ["subscription_id", "identity_kind", "identity_digest"],
        unique=True,
    )
    op.create_index(
        "ix_item_source_seen", "subscription_items", ["subscription_id", "first_seen_at", "id"]
    )
    op.create_table(
        "item_revisions",
        sa.Column(
            "item_id",
            sa.Uuid(),
            sa.ForeignKey("subscription_items.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("revision_number", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("original_url", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("author", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("revision_number >= 1", name="ck_revision_number"),
    )


def downgrade():
    """仅用于明确需要销毁新服务数据的回退；不能恢复已删除记录。"""
    op.drop_table("item_revisions")
    op.drop_table("subscription_items")
    op.drop_table("subscriptions")
