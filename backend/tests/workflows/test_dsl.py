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


def test_workflow_accepts_literals_and_analysis_projection() -> None:
    spec = parse_workflow_yaml(
        """
name: screened
trigger: {events: [manual]}
projection: content_analysis_v1
nodes:
  - id: score
    type: score
    input:
      dimensions:
        value:
          value: 80
          weight: 1.0
          reason: useful
  - id: gate
    type: gate
    depends_on: [score]
    predicate:
      left: $.steps.score.total
      operator: gte
      right: 70
    reject:
      output: {schema_version: 1, status: fine_rejected}
output: {schema_version: 1, status: qualified}
"""
    )

    assert spec.projection == "content_analysis_v1"
    assert spec.nodes[0].input["dimensions"] == {
        "value": {"value": 80, "weight": 1.0, "reason": "useful"}
    }


def test_workflow_accepts_safe_text_literals() -> None:
    spec = parse_workflow_yaml(
        """
name: literals
trigger: {events: [manual]}
nodes:
  - id: node
    type: parallel
    input:
      audience: software-builders
      instruction: Return JSON only.
output: {status: complete}
"""
    )

    assert spec.nodes[0].input == {
        "audience": "software-builders",
        "instruction": "Return JSON only.",
    }


def test_workflow_rejects_unknown_projection() -> None:
    with pytest.raises(WorkflowValidationError, match="projection"):
        parse_workflow_yaml(
            """
name: unknown-projection
trigger: {events: [manual]}
projection: arbitrary_json
nodes: [{id: node, type: parallel}]
"""
        )


@pytest.mark.parametrize(
    "node",
    [
        "{id: gate, type: gate, predicate: {left: 1, operator: eq, right: 1}}",
        "{id: gate, type: gate, reject: {output: {status: rejected}}}",
    ],
)
def test_gate_requires_predicate_and_reject_output(node: str) -> None:
    with pytest.raises(WorkflowValidationError, match="gate"):
        parse_workflow_yaml(
            f"""
name: incomplete-gate
trigger: {{events: [manual]}}
nodes: [{node}]
"""
        )


def test_non_gate_rejects_predicate_configuration() -> None:
    with pytest.raises(WorkflowValidationError, match="only valid for gate"):
        parse_workflow_yaml(
            """
name: misplaced-predicate
trigger: {events: [manual]}
nodes:
  - id: node
    type: parallel
    predicate: {left: 1, operator: eq, right: 1}
"""
        )


def test_gate_must_be_the_only_node_in_its_topological_layer() -> None:
    with pytest.raises(WorkflowValidationError, match="topological layer"):
        parse_workflow_yaml(
            """
name: parallel-gate
trigger: {events: [manual]}
nodes:
  - {id: prepare, type: parallel}
  - id: gate
    type: gate
    depends_on: [prepare]
    predicate: {left: 1, operator: eq, right: 1}
    reject: {output: {status: rejected}}
  - {id: bypass, type: parallel, depends_on: [prepare]}
"""
        )


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
        "$(whoami)",
        "`whoami`",
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
