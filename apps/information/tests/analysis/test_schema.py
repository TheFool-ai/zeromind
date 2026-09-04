from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from zeromind.analysis.schema import ContentAnalysisDraftV1


def qualified_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "qualified",
        "reference": {
            "reference_id": "11111111-1111-1111-1111-111111111111",
            "revision": 1,
            "subscription_id": "22222222-2222-2222-2222-222222222222",
            "url": "https://example.com/article",
            "title": "A useful article",
            "summary": "RSS summary",
            "author": "Ada",
            "published_at": "2026-07-30T00:00:00+00:00",
            "updated_at": None,
            "observed_at": "2026-07-30T01:00:00+00:00",
        },
        "screening": {
            "score": 85,
            "reason": "Relevant and substantial",
            "summary": "Metadata screening summary",
            "_execution": {
                "agent_id": "33333333-3333-3333-3333-333333333333",
                "agent_version": 1,
                "provider": "openai",
                "model": "gpt-5-mini",
                "usage": {"input": 50, "output": 10},
            },
        },
        "content": {
            "primary_category": "AI",
            "secondary_categories": ["Engineering"],
            "tags": ["agents", "workflows"],
            "one_sentence_summary": "A practical Agent workflow guide.",
            "summary": "The article explains a practical workflow architecture.",
            "viewpoints": [
                {
                    "statement": "Deterministic gates improve explainability.",
                    "explanation": "Thresholds remain visible and testable.",
                }
            ],
            "key_quotes": [
                {
                    "text": "Keep model judgment separate from deterministic policy.",
                    "context": "The author discusses scoring.",
                }
            ],
            "recommendation_level": "recommended",
            "recommendation_reason": "High information density",
            "scores": {
                "depth": {"value": 90, "reason": "Detailed evidence"},
                "clarity": {"value": 80, "reason": "Clear structure"},
            },
            "_execution": {
                "agent_id": "44444444-4444-4444-4444-444444444444",
                "agent_version": 2,
                "provider": "openai",
                "model": "gpt-5",
                "usage": {"input": 500, "output": 100},
            },
        },
        "score": {
            "total": 86,
            "dimensions": {
                "depth": {
                    "value": 90,
                    "weight": 0.6,
                    "reason": "Detailed evidence",
                },
                "clarity": {
                    "value": 80,
                    "weight": 0.4,
                    "reason": "Clear structure",
                },
            },
        },
    }


def test_accepts_qualified_analysis_projection() -> None:
    draft = ContentAnalysisDraftV1.model_validate(qualified_payload())

    assert draft.status == "qualified"
    assert draft.score is not None
    assert draft.score.total == 86
    assert draft.content is not None
    assert draft.content.execution.model == "gpt-5"
    assert draft.reference.observed_at == datetime(
        2026,
        7,
        30,
        1,
        tzinfo=UTC,
    )


def test_accepts_initial_rejection_without_full_content() -> None:
    payload = qualified_payload()
    payload["status"] = "initial_rejected"
    payload.pop("content")
    payload.pop("score")

    draft = ContentAnalysisDraftV1.model_validate(payload)

    assert draft.status == "initial_rejected"
    assert draft.content is None
    assert draft.score is None


def test_rejects_unsupported_schema_version() -> None:
    payload = qualified_payload()
    payload["schema_version"] = 2

    with pytest.raises(ValidationError, match="schema_version"):
        ContentAnalysisDraftV1.model_validate(payload)


@pytest.mark.parametrize("value", [-1, 101, 80.5, True])
def test_rejects_invalid_integer_scores(value: object) -> None:
    payload = qualified_payload()
    payload["screening"]["score"] = value  # type: ignore[index]

    with pytest.raises(ValidationError, match="score"):
        ContentAnalysisDraftV1.model_validate(payload)


def test_rejects_dimension_weights_that_do_not_sum_to_one() -> None:
    payload = qualified_payload()
    payload["score"]["dimensions"]["depth"]["weight"] = 0.5  # type: ignore[index]

    with pytest.raises(ValidationError, match="weights"):
        ContentAnalysisDraftV1.model_validate(payload)


def test_rejects_total_that_does_not_match_deterministic_score() -> None:
    payload = qualified_payload()
    payload["score"]["total"] = 99  # type: ignore[index]

    with pytest.raises(ValidationError, match="deterministic"):
        ContentAnalysisDraftV1.model_validate(payload)


def test_rejects_score_dimensions_that_disagree_with_agent_content() -> None:
    payload = qualified_payload()
    payload["score"]["dimensions"]["depth"]["reason"] = "Different reason"  # type: ignore[index]

    with pytest.raises(ValidationError, match="content scores"):
        ContentAnalysisDraftV1.model_validate(payload)


@pytest.mark.parametrize("status", ["fine_rejected", "qualified"])
def test_full_analysis_states_require_content_and_score(status: str) -> None:
    payload = qualified_payload()
    payload["status"] = status
    payload.pop("content")

    with pytest.raises(ValidationError, match="content and score"):
        ContentAnalysisDraftV1.model_validate(payload)


def test_initial_rejection_cannot_carry_full_content() -> None:
    payload = qualified_payload()
    payload["status"] = "initial_rejected"

    with pytest.raises(ValidationError, match="cannot contain"):
        ContentAnalysisDraftV1.model_validate(payload)


def test_rejects_more_than_ten_viewpoints() -> None:
    payload = qualified_payload()
    viewpoint = {
        "statement": "A bounded statement",
        "explanation": "A bounded explanation",
    }
    payload["content"]["viewpoints"] = [viewpoint] * 11  # type: ignore[index]

    with pytest.raises(ValidationError, match="viewpoints"):
        ContentAnalysisDraftV1.model_validate(payload)


def test_rejects_more_than_five_key_quotes() -> None:
    payload = qualified_payload()
    quote = {"text": "A bounded quote", "context": "Context"}
    payload["content"]["key_quotes"] = [quote] * 6  # type: ignore[index]

    with pytest.raises(ValidationError, match="key_quotes"):
        ContentAnalysisDraftV1.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("content", "key_quotes", 0, "text"), "q" * 301),
        (("content", "key_quotes", 0, "context"), "c" * 201),
        (("content", "viewpoints", 0, "statement"), "s" * 501),
        (("content", "viewpoints", 0, "explanation"), "e" * 2001),
        (("content", "summary"), "s" * 5001),
        (("content", "recommendation_reason"), "r" * 2001),
        (("screening", "reason"), "r" * 2001),
        (("score", "dimensions", "depth", "reason"), "r" * 2001),
    ],
)
def test_rejects_oversized_derived_text(
    path: tuple[str | int, ...],
    value: str,
) -> None:
    payload = deepcopy(qualified_payload())
    target: object = payload
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ValidationError):
        ContentAnalysisDraftV1.model_validate(payload)


def test_rejects_nested_transient_document_marker() -> None:
    payload = qualified_payload()
    payload["screening"]["_execution"]["usage"] = {  # type: ignore[index]
        "_transient_document": 1
    }

    with pytest.raises(ValidationError, match="_transient_document"):
        ContentAnalysisDraftV1.model_validate(payload)


def test_rejects_known_article_body_marker() -> None:
    payload = qualified_payload()
    payload["content"]["summary"] = "ARTICLE BODY MUST NOT BE STORED"  # type: ignore[index]

    with pytest.raises(ValidationError, match="article body"):
        ContentAnalysisDraftV1.model_validate(payload)
