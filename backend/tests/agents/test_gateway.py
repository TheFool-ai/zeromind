from uuid import UUID

import pytest

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.gateway import AgentGateway, AgentOutputError
from zeromind.agents.pi_rpc import PiRpcResult
from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository

PROFILE_ID = UUID("33333333-3333-3333-3333-333333333333")


class StubPiClient:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output

    async def execute(self, request: object, *, timeout_seconds: float) -> PiRpcResult:
        del request, timeout_seconds
        return PiRpcResult(output=self.output, deltas=(), usage={})


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
    gateway = AgentGateway(value, StubPiClient({"summary": "Done"}))

    result = await gateway.execute(definition.id, {"title": "Article"})

    assert result.output == {"summary": "Done"}
    assert result.agent_version == 1


@pytest.mark.asyncio
async def test_gateway_rejects_output_that_breaks_agent_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value, definition = await registry(monkeypatch)
    gateway = AgentGateway(value, StubPiClient({"unexpected": True}))

    with pytest.raises(AgentOutputError):
        await gateway.execute(definition.id, {"title": "Article"})
