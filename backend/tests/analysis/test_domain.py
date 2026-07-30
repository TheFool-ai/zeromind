from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from zeromind.analysis.domain import (
    ContentAnalysis,
    KeyQuote,
    ScoreDimension,
    Viewpoint,
)


def make_analysis(
    *,
    generated_status: str = "qualified",
) -> ContentAnalysis:
    return ContentAnalysis(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        reference_id=UUID("11111111-1111-1111-1111-111111111111"),
        reference_revision=1,
        subscription_id=UUID("22222222-2222-2222-2222-222222222222"),
        workflow_definition_id=UUID("33333333-3333-3333-3333-333333333333"),
        workflow_definition_version=1,
        workflow_run_id=UUID("44444444-4444-4444-4444-444444444444"),
        generated_status=generated_status,
        source_name="Example Engineering",
        source_feed_url="https://example.com/feed",
        title="A useful article",
        original_url="https://example.com/article",
        author="Ada",
        published_at=datetime(2026, 7, 30, tzinfo=UTC),
        observed_at=datetime(2026, 7, 30, 1, tzinfo=UTC),
        screening_score=85,
        screening_reason="Relevant and substantial",
        screening_summary="Metadata screening summary",
        primary_category="AI",
        secondary_categories=("Engineering",),
        tags=("agents", "workflows"),
        one_sentence_summary="A practical Agent workflow guide.",
        summary="The article explains a practical workflow architecture.",
        viewpoints=(
            Viewpoint(
                statement="Deterministic gates improve explainability.",
                explanation="Thresholds remain visible and testable.",
            ),
        ),
        key_quotes=(
            KeyQuote(
                text="Keep model judgment separate from deterministic policy.",
                context="The author discusses scoring.",
            ),
        ),
        total_score=86,
        dimensions={
            "depth": ScoreDimension(
                value=90,
                weight=0.6,
                reason="Detailed evidence",
            ),
            "clarity": ScoreDimension(
                value=80,
                weight=0.4,
                reason="Clear structure",
            ),
        },
        recommendation_level="recommended",
        recommendation_reason="High information density",
        provenance={
            "screening": {"agent_version": 1},
            "analysis": {"agent_version": 2},
        },
        created_at=datetime(2026, 7, 30, 2, tzinfo=UTC),
    )


def test_effective_decision_uses_latest_override_sequence() -> None:
    analysis = make_analysis(generated_status="fine_rejected")
    same_time = datetime(2026, 7, 30, 3, tzinfo=UTC)

    first = analysis.add_override(
        decision="qualified",
        reason="Manual review found original evidence.",
        actor_subject="admin",
        now=same_time,
    )
    second = analysis.add_override(
        decision="rejected",
        reason="The evidence is outdated after a second review.",
        actor_subject="admin",
        now=same_time,
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert analysis.effective_decision == "rejected"
    assert analysis.overrides == (first, second)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("qualified", "qualified"),
        ("initial_rejected", "rejected"),
        ("fine_rejected", "rejected"),
    ],
)
def test_generated_status_controls_decision_without_override(
    status: str,
    expected: str,
) -> None:
    assert make_analysis(generated_status=status).effective_decision == expected


@pytest.mark.parametrize(
    "reason",
    ["short", "x" * 2001],
)
def test_override_requires_a_bounded_reason(reason: str) -> None:
    with pytest.raises(ValueError, match="reason"):
        make_analysis().add_override(
            decision="rejected",
            reason=reason,
            actor_subject="admin",
        )


def test_override_normalizes_reason_and_actor() -> None:
    override = make_analysis().add_override(
        decision="rejected",
        reason="  Manual review found unsupported claims.  ",
        actor_subject="  admin  ",
    )

    assert override.reason == "Manual review found unsupported claims."
    assert override.actor_subject == "admin"


def test_override_rejects_unknown_decision() -> None:
    with pytest.raises(ValueError, match="decision"):
        make_analysis().add_override(
            decision="maybe",
            reason="Manual review found unsupported claims.",
            actor_subject="admin",
        )


def test_override_requires_an_actor() -> None:
    with pytest.raises(ValueError, match="actor"):
        make_analysis().add_override(
            decision="rejected",
            reason="Manual review found unsupported claims.",
            actor_subject=" ",
        )


def test_generated_analysis_fields_are_immutable() -> None:
    analysis = make_analysis()

    with pytest.raises(FrozenInstanceError):
        analysis.title = "Changed"  # type: ignore[misc]
