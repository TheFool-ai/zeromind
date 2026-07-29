from uuid import UUID

import pytest

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.workflows.dsl import WorkflowValidationError, parse_workflow_yaml, validate_workflow

AGENT_ID = UUID("44444444-4444-4444-4444-444444444444")
PROFILE_ID = UUID("33333333-3333-3333-3333-333333333333")

VALID = f"""
name: article-analysis
trigger:
  events: [reference.discovered]
nodes:
  - id: resolve
    type: resolve
    input:
      reference_id: $.trigger.reference_id
  - id: summarize
    type: agent
    agent_id: {AGENT_ID}
    depends_on: [resolve]
    input:
      document: $.steps.resolve
    retry:
      max_attempts: 2
      backoff_seconds: 1
output:
  analysis: $.steps.summarize
"""


async def registry() -> AgentRegistry:
    value = AgentRegistry(InMemoryAgentRepository())
    await value.register_provider(
        ProviderProfile.create(
            name="default",
            provider="openai",
            model="gpt-5-mini",
            api_key_env="OPENAI_API_KEY",
            identifier=PROFILE_ID,
        )
    )
    await value.register_agent(
        AgentDefinition.create(
            name="summarizer",
            description="Summarizes",
            capabilities=("summarize",),
            system_prompt="Return JSON.",
            provider_profile_id=PROFILE_ID,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            identifier=AGENT_ID,
        )
    )
    return value


@pytest.mark.asyncio
async def test_valid_workflow_parses_and_resolves_registered_agent() -> None:
    spec = parse_workflow_yaml(VALID)

    await validate_workflow(spec, await registry())

    assert spec.name == "article-analysis"
    assert spec.nodes[1].agent_id == AGENT_ID
    assert spec.topological_order() == ("resolve", "summarize")


def test_workflow_rejects_cycles() -> None:
    cyclic = """
name: cyclic
trigger: {events: [manual]}
nodes:
  - {id: one, type: parallel, depends_on: [two]}
  - {id: two, type: parallel, depends_on: [one]}
output: {}
"""

    with pytest.raises(WorkflowValidationError, match="cycle"):
        parse_workflow_yaml(cyclic)


@pytest.mark.parametrize(
    "mapping",
    [
        "${__import__('os').system('whoami')}",
        "$.steps[item]",
        "lambda x: x",
    ],
)
def test_workflow_rejects_executable_or_dynamic_mappings(mapping: str) -> None:
    source = f"""
name: unsafe
trigger: {{events: [manual]}}
nodes:
  - id: node
    type: parallel
    input: {{value: "{mapping}"}}
output: {{}}
"""

    with pytest.raises(WorkflowValidationError, match="mapping"):
        parse_workflow_yaml(source)


def test_workflow_rejects_unbounded_retry() -> None:
    source = """
name: retry
trigger: {events: [manual]}
nodes:
  - id: node
    type: parallel
    retry: {max_attempts: 99, backoff_seconds: 1}
output: {}
"""

    with pytest.raises(WorkflowValidationError, match="max_attempts"):
        parse_workflow_yaml(source)

