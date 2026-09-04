import hashlib

from zeromind.agents.sanitization import bounded_error, sanitize_agent_input


def test_sanitizes_nested_transient_document_without_mutating_input() -> None:
    body = "ARTICLE BODY MUST NOT BE STORED"
    value: dict[str, object] = {
        "metadata": {"title": "Safe"},
        "items": [
            {
                "document": {
                    "_transient_document": True,
                    "content_type": "text/markdown",
                    "title": "Safe title",
                    "text": body,
                }
            }
        ],
    }

    result = sanitize_agent_input(value)

    assert result.document_sha256 == hashlib.sha256(body.encode()).hexdigest()
    assert result.document_character_count == len(body)
    assert result.value["metadata"] == {"title": "Safe"}
    assert "ARTICLE BODY" not in str(result.value)
    assert "_transient_document" not in str(result.value)
    assert result.value["items"] == [
        {
            "document": {
                "content_type": "text/markdown",
                "title": "Safe title",
                "sha256": result.document_sha256,
                "character_count": len(body),
            }
        }
    ]
    assert "text" in str(value)


def test_bounded_error_redacts_secrets_headers_and_newlines() -> None:
    message = "Authorization: Bearer token-value\napi_key=secret-value\n" + "x" * 2000

    result = bounded_error(message, secrets=("token-value", "secret-value"))

    assert "token-value" not in result
    assert "secret-value" not in result
    assert "\n" not in result
    assert len(result) == 1000

