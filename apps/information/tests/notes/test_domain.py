from datetime import UTC, datetime
from uuid import UUID

import pytest

from zeromind.notes.domain import MAX_NOTE_BYTES, Note

REFERENCE_ID = UUID("11111111-1111-1111-1111-111111111111")
ANALYSIS_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NOW = datetime(2026, 7, 31, 6, tzinfo=UTC)
LATER = datetime(2026, 7, 31, 7, tzinfo=UTC)


def test_note_normalizes_body_and_updates_timestamp() -> None:
    note = Note.create(
        reference_id=REFERENCE_ID,
        analysis_id=ANALYSIS_ID,
        owner_subject="admin",
        body="  Important insight  ",
        now=NOW,
    )
    note.update(body="Updated insight", analysis_id=None, now=LATER)

    assert note.body == "Updated insight"
    assert note.analysis_id is None
    assert note.updated_at == LATER
    assert note.created_at == NOW


@pytest.mark.parametrize("body", ["", " ", "\n\t"])
def test_note_rejects_empty_or_whitespace_body(body: str) -> None:
    with pytest.raises(ValueError, match="body"):
        Note.create(
            reference_id=REFERENCE_ID,
            analysis_id=None,
            owner_subject="admin",
            body=body,
        )


def test_note_enforces_utf8_byte_limit() -> None:
    accepted = "界" * (MAX_NOTE_BYTES // 3)
    rejected = accepted + "界"

    note = Note.create(
        reference_id=REFERENCE_ID,
        analysis_id=None,
        owner_subject="admin",
        body=accepted,
    )
    assert len(note.body.encode("utf-8")) <= MAX_NOTE_BYTES

    with pytest.raises(ValueError, match="65536"):
        Note.create(
            reference_id=REFERENCE_ID,
            analysis_id=None,
            owner_subject="admin",
            body=rejected,
        )


def test_note_requires_owner_subject() -> None:
    with pytest.raises(ValueError, match="owner"):
        Note.create(
            reference_id=REFERENCE_ID,
            analysis_id=None,
            owner_subject=" ",
            body="Insight",
        )


def test_note_update_reuses_body_validation() -> None:
    note = Note.create(
        reference_id=REFERENCE_ID,
        analysis_id=None,
        owner_subject="admin",
        body="Insight",
    )

    with pytest.raises(ValueError, match="body"):
        note.update(body=" ", analysis_id=None)
