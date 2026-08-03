from uuid import UUID

import pytest

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.gateway import AgentGateway, AgentOutputError
from zeromind.agents.pi_rpc import PiRpcResult
from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.agents.session_domain import AgentExecutionContext
from zeromind.agents.session_repository import InMemoryAgentSessionRepository

PROFILE_ID = UUID("33333333-3333-3333-3333-333333333333")


class StubPiClient:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output

    async def execute(self, request: object, *, timeout_seconds: float) -> PiRpcResult:
        del request, timeout_seconds
        return PiRpcResult(
            output=self.output,
            deltas=(),
            usage={"total": 5},
            response_sha256="a" * 64,
            response_character_count=20,
        )


def context() -> AgentExecutionContext:
    return AgentExecutionContext(
        workflow_run_id=UUID("11111111-1111-1111-1111-111111111111"),
        step_run_id=UUID("22222222-2222-2222-2222-222222222222"),
        attempt=1,
    )


async def registry(monkeypatch: pytest.MonkeyPatch) -> tuple[AgentRegistry, AgentDefinition]:
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    value = AgentRegistry(InMemoryAgentRepository())
    await value.register_provider(
        ProviderProfile.create(
            name="default",
            provider="openai",
            model="gpt-5-mini",
            api_key_env="OPENAI_API_KEY",
            thinking_level="medium",
            identifier=PROFILE_ID,
        )
    )
    definition = AgentDefinition.create(
        name="summarizer",
        description="Summarizes articles",
        capabilities=("summarize",),
        system_prompt="Return JSON.",
        provider_profile_id=PROFILE_ID,
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
            "additionalProperties": False,
        },
    )
    await value.register_agent(definition)
    return value, definition


@pytest.mark.asyncio
async def test_gateway_validates_agent_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value, definition = await registry(monkeypatch)
    sessions = InMemoryAgentSessionRepository()
    gateway = AgentGateway(value, StubPiClient({"summary": "Done"}), sessions)

    result = await gateway.execute(
        definition.id,
        {"title": "Article"},
        context=context(),
    )

    assert result.output == {"summary": "Done"}
    assert result.agent_version == 1
    recorded = await sessions.list(workflow_run_id=context().workflow_run_id)
    assert len(recorded) == 1
    assert recorded[0].status == "completed"
    assert recorded[0].agent_version_id == definition.version_id


@pytest.mark.asyncio
async def test_gateway_rejects_output_that_breaks_agent_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value, definition = await registry(monkeypatch)
    sessions = InMemoryAgentSessionRepository()
    gateway = AgentGateway(value, StubPiClient({"unexpected": True}), sessions)

    with pytest.raises(AgentOutputError):
        await gateway.execute(definition.id, {"title": "Article"}, context=context())

    recorded = await sessions.list(workflow_run_id=context().workflow_run_id)
    assert recorded[0].status == "schema_invalid"
    assert recorded[0].output is None


@pytest.mark.asyncio
async def test_gateway_sanitizes_transient_document_in_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value, definition = await registry(monkeypatch)
    sessions = InMemoryAgentSessionRepository()
    gateway = AgentGateway(value, StubPiClient({"summary": "Done"}), sessions)

    await gateway.execute(
        definition.id,
        {
            "document": {
                "_transient_document": True,
                "text": "ARTICLE BODY MUST NOT BE STORED",
                "content_type": "text/markdown",
            }
        },
        context=context(),
    )

    recorded = (await sessions.list())[0]
    assert "ARTICLE BODY" not in str(recorded.sanitized_input)
    assert recorded.document_sha256 is not None
