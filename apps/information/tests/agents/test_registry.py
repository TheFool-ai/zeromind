from uuid import UUID

import pytest

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository

PROFILE_ID = UUID("33333333-3333-3333-3333-333333333333")


def profile() -> ProviderProfile:
    return ProviderProfile.create(
        name="default-openai",
        provider="openai",
        model="gpt-5-mini",
        api_key_env="OPENAI_API_KEY",
        thinking_level="medium",
        identifier=PROFILE_ID,
    )


def agent(name: str, capabilities: tuple[str, ...]) -> AgentDefinition:
    return AgentDefinition.create(
        name=name,
        description=f"{name} agent",
        capabilities=capabilities,
        system_prompt="Return structured analysis.",
        provider_profile_id=PROFILE_ID,
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
    )


@pytest.mark.asyncio
async def test_discovery_returns_enabled_agents_with_all_requested_capabilities() -> None:
    registry = AgentRegistry(InMemoryAgentRepository())
    await registry.register_provider(profile())
    summarizer = agent("summarizer", ("summarize", "zh"))
    classifier = agent("classifier", ("classify",))
    await registry.register_agent(summarizer)
    await registry.register_agent(classifier)

    discovered = await registry.discover(("summarize", "zh"))

    assert [item.name for item in discovered] == ["summarizer"]


@pytest.mark.asyncio
async def test_disabled_agent_is_not_discoverable() -> None:
    registry = AgentRegistry(InMemoryAgentRepository())
    await registry.register_provider(profile())
    summarizer = agent("summarizer", ("summarize",))
    summarizer.disable()
    await registry.register_agent(summarizer)

    assert await registry.discover(("summarize",)) == ()


def test_execution_changes_increment_agent_version() -> None:
    definition = agent("summarizer", ("summarize",))

    original = definition.current_version()

    updated = definition.update(
        system_prompt="Return a concise structured analysis.",
        capabilities=("summarize", "concise"),
        provider_profile_id=PROFILE_ID,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    assert definition.version == 2
    assert definition.capabilities == ("concise", "summarize")
    assert original.version == 1
    assert original.system_prompt == "Return structured analysis."
    assert updated.version == 2
    assert updated.id != original.id


@pytest.mark.asyncio
async def test_registry_preserves_version_history() -> None:
    registry = AgentRegistry(InMemoryAgentRepository())
    await registry.register_provider(profile())
    definition = agent("summarizer", ("summarize",))
    await registry.register_agent(definition)

    await registry.update_agent(
        definition.id,
        system_prompt="Return concise JSON.",
        capabilities=("summarize", "concise"),
        provider_profile_id=PROFILE_ID,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    versions = await registry.list_agent_versions(definition.id)
    assert [item.version for item in versions] == [1, 2]
    assert versions[0].system_prompt == "Return structured analysis."
    assert versions[1].system_prompt == "Return concise JSON."


def test_provider_profile_stores_environment_reference_not_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    value = profile()

    assert value.resolve_api_key() == "secret-value"
    assert "secret-value" not in repr(value)
