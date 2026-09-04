"""Add immutable agent versions and execution sessions.

Revision ID: 0010_agent_versions_and_sessions
Revises: 0009_notes
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_agent_versions_and_sessions"
down_revision: str | Sequence[str] | None = "0009_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("provider_profile_id", sa.Uuid(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agent_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["provider_profile_id"], ["provider_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "version", name="uq_agent_version"),
    )
    op.create_index(
        op.f("ix_agent_versions_agent_id"), "agent_versions", ["agent_id"]
    )
    op.create_index(
        op.f("ix_agent_versions_provider_profile_id"),
        "agent_versions",
        ["provider_profile_id"],
    )

    op.add_column(
        "agent_definitions", sa.Column("current_version", sa.Integer(), nullable=True)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO agent_versions (
                id, agent_id, version, capabilities, system_prompt,
                provider_profile_id, input_schema, output_schema, created_at
            )
            SELECT CAST(md5(CAST(id AS text) || ':version:' || CAST(version AS text)) AS uuid),
                   id, version, capabilities, system_prompt, provider_profile_id,
                   input_schema, output_schema, updated_at
            FROM agent_definitions
            """
        )
    )
    op.execute(sa.text("UPDATE agent_definitions SET current_version = version"))
    op.alter_column("agent_definitions", "current_version", nullable=False)
    op.drop_index(
        op.f("ix_agent_definitions_provider_profile_id"),
        table_name="agent_definitions",
    )
    for column in (
        "capabilities",
        "system_prompt",
        "provider_profile_id",
        "input_schema",
        "output_schema",
        "version",
    ):
        op.drop_column("agent_definitions", column)

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("step_run_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("agent_version_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("thinking_level", sa.String(length=20), nullable=False),
        sa.Column("sanitized_input", sa.JSON(), nullable=False),
        sa.Column("document_sha256", sa.String(length=64), nullable=True),
        sa.Column("document_character_count", sa.Integer(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("response_sha256", sa.String(length=64), nullable=True),
        sa.Column("response_character_count", sa.Integer(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["step_run_id"], ["workflow_step_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agent_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_run_id", "attempt", name="uq_agent_session_attempt"),
    )
    for column in (
        "workflow_run_id",
        "agent_id",
        "agent_version_id",
        "status",
        "started_at",
    ):
        op.create_index(
            op.f(f"ix_agent_sessions_{column}"), "agent_sessions", [column]
        )


def downgrade() -> None:
    for column in (
        "started_at",
        "status",
        "agent_version_id",
        "agent_id",
        "workflow_run_id",
    ):
        op.drop_index(op.f(f"ix_agent_sessions_{column}"), table_name="agent_sessions")
    op.drop_table("agent_sessions")

    op.add_column(
        "agent_definitions", sa.Column("version", sa.Integer(), nullable=True)
    )
    op.add_column(
        "agent_definitions", sa.Column("output_schema", sa.JSON(), nullable=True)
    )
    op.add_column(
        "agent_definitions", sa.Column("input_schema", sa.JSON(), nullable=True)
    )
    op.add_column(
        "agent_definitions",
        sa.Column("provider_profile_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "agent_definitions", sa.Column("system_prompt", sa.Text(), nullable=True)
    )
    op.add_column(
        "agent_definitions", sa.Column("capabilities", sa.JSON(), nullable=True)
    )
    op.execute(
        sa.text(
            """
            UPDATE agent_definitions AS definitions
            SET version = versions.version,
                capabilities = versions.capabilities,
                system_prompt = versions.system_prompt,
                provider_profile_id = versions.provider_profile_id,
                input_schema = versions.input_schema,
                output_schema = versions.output_schema
            FROM agent_versions AS versions
            WHERE versions.agent_id = definitions.id
              AND versions.version = definitions.current_version
            """
        )
    )
    for column in (
        "version",
        "output_schema",
        "input_schema",
        "provider_profile_id",
        "system_prompt",
        "capabilities",
    ):
        op.alter_column("agent_definitions", column, nullable=False)
    op.create_index(
        op.f("ix_agent_definitions_provider_profile_id"),
        "agent_definitions",
        ["provider_profile_id"],
    )
    op.drop_column("agent_definitions", "current_version")
    op.drop_index(
        op.f("ix_agent_versions_provider_profile_id"), table_name="agent_versions"
    )
    op.drop_index(op.f("ix_agent_versions_agent_id"), table_name="agent_versions")
    op.drop_table("agent_versions")
