import hashlib
import re
from dataclasses import dataclass

SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(authorization\s*:\s*(?:bearer\s+)?|api[_-]?key\s*[=:]\s*)\S+"
)


@dataclass(frozen=True, slots=True)
class SanitizedAgentInput:
    value: dict[str, object]
    document_sha256: str | None
    document_character_count: int | None


def sanitize_agent_input(value: dict[str, object]) -> SanitizedAgentInput:
    document_sha256: str | None = None
    document_character_count: int | None = None

    def clean(item: object) -> object:
        nonlocal document_sha256, document_character_count
        if isinstance(item, dict):
            if item.get("_transient_document") is True:
                text = item.get("text")
                if not isinstance(text, str):
                    raise ValueError("transient document text must be a string")
                digest = hashlib.sha256(text.encode()).hexdigest()
                document_sha256 = document_sha256 or digest
                document_character_count = document_character_count or len(text)
                safe = {
                    str(key): clean(nested)
                    for key, nested in item.items()
                    if key not in {"_transient_document", "text"}
                }
                safe["sha256"] = digest
                safe["character_count"] = len(text)
                return safe
            return {str(key): clean(nested) for key, nested in item.items()}
        if isinstance(item, list | tuple):
            return [clean(nested) for nested in item]
        return item

    cleaned = clean(value)
    if not isinstance(cleaned, dict):
        raise ValueError("agent input must be an object")
    return SanitizedAgentInput(
        value=cleaned,
        document_sha256=document_sha256,
        document_character_count=document_character_count,
    )


def bounded_error(message: str, *, secrets: tuple[str, ...] = ()) -> str:
    result = message
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[redacted]")
    result = SENSITIVE_ASSIGNMENT.sub(r"\1[redacted]", result)
    return " ".join(result.split())[:1000]

