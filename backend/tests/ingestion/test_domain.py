from datetime import UTC, datetime
from uuid import UUID

from zeromind.ingestion.domain import ContentReference

NOW = datetime(2026, 8, 4, 9, tzinfo=UTC)
LATER = datetime(2026, 8, 4, 10, tzinfo=UTC)


def test_new_reference_starts_pending_for_current_revision() -> None:
    reference = ContentReference.create(
        subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
        identity_key="guid:one",
        original_url="https://example.com/one",
        now=NOW,
    )

    assert reference.current_revision == 1
    assert reference.analysis_status == "pending"
    assert reference.analysis_status_revision == 1
    assert reference.analysis_workflow_run_id is None
    assert reference.analysis_status_updated_at == NOW


def test_new_revision_resets_analysis_projection() -> None:
    reference = ContentReference.create(
        subscription_id=UUID("11111111-1111-1111-1111-111111111111"),
        identity_key="guid:one",
        original_url="https://example.com/one",
        now=NOW,
    )
    reference.analysis_status = "completed"
    reference.analysis_workflow_run_id = UUID(
        "22222222-2222-2222-2222-222222222222"
    )
    reference.analysis_error_code = "old_error"
    reference.analysis_error_message = "old error"
    reference.analysis_started_at = NOW
    reference.analysis_completed_at = NOW
    reference.current_revision = 2

    reference.reset_analysis(revision=2, now=LATER)

    assert reference.analysis_status == "pending"
    assert reference.analysis_status_revision == 2
    assert reference.analysis_workflow_run_id is None
    assert reference.analysis_error_code is None
    assert reference.analysis_error_message is None
    assert reference.analysis_status_updated_at == LATER
    assert reference.analysis_started_at is None
    assert reference.analysis_completed_at is None
