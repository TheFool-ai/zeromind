import re
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, inspect

from zeromind.ingestion.models import ContentReferenceModel

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/0011_reference_analysis_lifecycle.py"
)


def test_migration_revision_fits_alembic_version_column() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    match = re.search(r'^revision: str = "([^"]+)"$', source, re.MULTILINE)
    assert match is not None
    assert len(match.group(1)) <= 32


def test_content_reference_has_analysis_lifecycle_columns() -> None:
    columns = {column.name for column in inspect(ContentReferenceModel).columns}

    assert {
        "analysis_status",
        "analysis_status_revision",
        "analysis_workflow_run_id",
        "analysis_error_code",
        "analysis_error_message",
        "analysis_status_updated_at",
        "analysis_started_at",
        "analysis_completed_at",
    }.issubset(columns)


def test_content_reference_lifecycle_has_constraints_and_indexes() -> None:
    table = ContentReferenceModel.__table__
    checks = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    foreign_keys = {
        (
            tuple(column.name for column in constraint.columns),
            constraint.ondelete,
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    indexes = {tuple(column.name for column in index.columns) for index in table.indexes}

    assert "ck_content_reference_analysis_status" in checks
    assert (("analysis_workflow_run_id",), "SET NULL") in foreign_keys
    assert ("analysis_status",) in indexes
    assert ("analysis_status_updated_at",) in indexes
