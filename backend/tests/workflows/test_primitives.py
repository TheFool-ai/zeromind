import pytest

from zeromind.workflows.primitives import calculate_weighted_score, evaluate_predicate


def test_calculates_weighted_score_with_reasons() -> None:
    result = calculate_weighted_score(
        {
            "depth": {"value": 90, "weight": 0.6, "reason": "Deep evidence"},
            "clarity": {"value": 70, "weight": 0.4, "reason": "Readable"},
        }
    )

    assert result == {
        "total": 82,
        "dimensions": {
            "depth": {
                "value": 90,
                "weight": 0.6,
                "reason": "Deep evidence",
            },
            "clarity": {
                "value": 70,
                "weight": 0.4,
                "reason": "Readable",
            },
        },
    }


def test_weighted_score_uses_half_up_rounding() -> None:
    result = calculate_weighted_score(
        {
            "depth": {"value": 83, "weight": 0.5, "reason": "Deep"},
            "clarity": {"value": 82, "weight": 0.5, "reason": "Clear"},
        }
    )

    assert result["total"] == 83


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        ({"left": 70, "operator": "gte", "right": 70}, True),
        ({"left": "ai", "operator": "eq", "right": "product"}, False),
        ({"left": "ai", "operator": "in", "right": ["ai", "code"]}, True),
        ({"left": "ai", "operator": "not_in", "right": ["product"]}, True),
    ],
)
def test_evaluates_supported_predicates(
    predicate: dict[str, object],
    expected: bool,
) -> None:
    assert evaluate_predicate(predicate) is expected


@pytest.mark.parametrize(
    "dimensions",
    [
        {},
        {"depth": {"value": -1, "weight": 1.0, "reason": "Bad"}},
        {"depth": {"value": 101, "weight": 1.0, "reason": "Bad"}},
        {"depth": {"value": True, "weight": 1.0, "reason": "Bad"}},
        {"depth": {"value": 80.5, "weight": 1.0, "reason": "Bad"}},
        {"depth": {"value": 80, "weight": 0, "reason": "Bad"}},
        {"depth": {"value": 80, "weight": True, "reason": "Bad"}},
        {"depth": {"value": 80, "weight": 1.0, "reason": " "}},
        {"depth": {"value": 80, "weight": 1.0, "reason": "x" * 2001}},
        {
            "depth": {"value": 80, "weight": 0.6, "reason": "Deep"},
            "clarity": {"value": 70, "weight": 0.3, "reason": "Clear"},
        },
    ],
)
def test_rejects_invalid_score_dimensions(
    dimensions: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        calculate_weighted_score(dimensions)


def test_numeric_predicate_rejects_non_numeric_operands() -> None:
    with pytest.raises(ValueError, match="must be numbers"):
        evaluate_predicate({"left": "70", "operator": "gte", "right": 70})


def test_membership_predicate_requires_a_collection() -> None:
    with pytest.raises(ValueError, match="must be a collection"):
        evaluate_predicate({"left": "ai", "operator": "in", "right": "ai"})
