import pytest

from zeromind.agents.gateway import AgentOutputError
from zeromind.agents.validators import validate_agent_semantics


def taxonomy(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "primary_category": "人工智能",
        "category_probabilities": {
            "人工智能": 60,
            "软件编程": 20,
            "产品设计": 10,
            "商业科技": 5,
            "其他": 5,
        },
        "tags": ["大语言模型", "Agent"],
    }
    value.update(overrides)
    return value


def test_taxonomy_semantics_accept_exact_probability_distribution() -> None:
    validate_agent_semantics(("classify-content",), taxonomy())


@pytest.mark.parametrize(
    "output",
    [
        taxonomy(
            category_probabilities={
                "人工智能": 59,
                "软件编程": 20,
                "产品设计": 10,
                "商业科技": 5,
                "其他": 5,
            }
        ),
        taxonomy(primary_category="软件编程"),
        taxonomy(tags=["Agent", "Agent"]),
    ],
)
def test_taxonomy_semantics_reject_inconsistent_output(
    output: dict[str, object],
) -> None:
    with pytest.raises(AgentOutputError):
        validate_agent_semantics(("classify-content",), output)
