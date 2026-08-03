class AgentOutputError(ValueError):
    pass


TAXONOMY_CATEGORIES = (
    "人工智能",
    "软件编程",
    "产品设计",
    "商业科技",
    "其他",
)


def validate_agent_semantics(
    capabilities: tuple[str, ...], output: dict[str, object]
) -> None:
    if "classify-content" not in capabilities:
        return
    probabilities = output.get("category_probabilities")
    if not isinstance(probabilities, dict):
        raise AgentOutputError("category_probabilities must be an object")
    if set(probabilities) != set(TAXONOMY_CATEGORIES):
        raise AgentOutputError("category_probabilities has unsupported categories")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in probabilities.values()
    ):
        raise AgentOutputError("category probabilities must be integers")
    integer_probabilities = {
        str(category): int(value) for category, value in probabilities.items()
    }
    if sum(integer_probabilities.values()) != 100:
        raise AgentOutputError("category probabilities must total 100")
    primary = output.get("primary_category")
    if not isinstance(primary, str) or primary not in TAXONOMY_CATEGORIES:
        raise AgentOutputError("primary_category is unsupported")
    maximum = max(integer_probabilities.values())
    if integer_probabilities[primary] != maximum:
        raise AgentOutputError("primary_category must have the highest probability")
    tags = output.get("tags")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise AgentOutputError("tags must be an array of strings")
    if len(tags) != len(set(tags)):
        raise AgentOutputError("tags must be unique")
