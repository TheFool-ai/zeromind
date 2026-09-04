from math import isclose
from operator import eq, ge, gt, le, lt, ne

NUMERIC_OPERATORS = {"gt": gt, "gte": ge, "lt": lt, "lte": le}
EQUALITY_OPERATORS = {"eq": eq, "ne": ne}


def calculate_weighted_score(
    dimensions: dict[str, object],
) -> dict[str, object]:
    normalized: dict[str, dict[str, object]] = {}
    weighted = 0.0
    total_weight = 0.0
    if not dimensions:
        raise ValueError("score dimensions cannot be empty")
    for name, raw in dimensions.items():
        if not isinstance(raw, dict):
            raise ValueError(f"score dimension {name} must be an object")
        value = raw.get("value")
        weight = raw.get("weight")
        reason = raw.get("reason")
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 100
        ):
            raise ValueError(
                f"score dimension {name} value must be an integer from 0 to 100"
            )
        if (
            isinstance(weight, bool)
            or not isinstance(weight, int | float)
            or weight <= 0
        ):
            raise ValueError(f"score dimension {name} weight must be positive")
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or len(reason) > 2000
        ):
            raise ValueError(f"score dimension {name} reason is invalid")
        normalized[name] = {
            "value": value,
            "weight": float(weight),
            "reason": reason.strip(),
        }
        weighted += value * float(weight)
        total_weight += float(weight)
    if not isclose(total_weight, 1.0, abs_tol=1e-9):
        raise ValueError("score dimension weights must sum to 1.0")
    return {"total": int(weighted + 0.5), "dimensions": normalized}


def evaluate_predicate(predicate: dict[str, object]) -> bool:
    left = predicate["left"]
    right = predicate["right"]
    operator = str(predicate["operator"])
    if operator in NUMERIC_OPERATORS:
        if (
            isinstance(left, bool)
            or isinstance(right, bool)
            or not isinstance(left, int | float)
            or not isinstance(right, int | float)
        ):
            raise ValueError("numeric gate operands must be numbers")
        return bool(NUMERIC_OPERATORS[operator](left, right))
    if operator in EQUALITY_OPERATORS:
        return bool(EQUALITY_OPERATORS[operator](left, right))
    if operator in {"in", "not_in"}:
        if not isinstance(right, list | tuple | set):
            raise ValueError("membership gate right operand must be a collection")
        present = left in right
        return present if operator == "in" else not present
    raise ValueError(f"unsupported gate operator: {operator}")
