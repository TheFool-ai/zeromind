import json
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.workflows.dsl import parse_workflow_yaml, validate_workflow

EXAMPLES = Path(__file__).resolve().parents[3] / "docs" / "examples"
FILES = (
    "screening-agent.json",
    "core-analysis-agent.json",
    "taxonomy-agent.json",
    "quality-scoring-agent.json",
    "review-agent.json",
    "finalizer-agent.json",
)
PLACEHOLDERS = tuple(
    UUID(f"00000000-0000-0000-0000-{value:012d}")
    for value in range(101, 107)
)


@pytest.mark.asyncio
async def test_six_presets_have_strict_valid_schemas_and_form_valid_dsl() -> None:
    repository = InMemoryAgentRepository()
    registry = AgentRegistry(repository)
    provider = ProviderProfile.create(
        name="GLM",
        provider="glm",
        model="GLM-5.2",
        api_key_env="GLM_API_KEY",
        identifier=UUID("00000000-0000-0000-0000-000000000100"),
    )
    await registry.register_provider(provider)
    capabilities: set[str] = set()
    for filename, identifier in zip(FILES, PLACEHOLDERS, strict=True):
        payload = json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))
        assert payload["input_schema"]["additionalProperties"] is False
        assert payload["output_schema"]["additionalProperties"] is False
        Draft202012Validator.check_schema(payload["input_schema"])
        Draft202012Validator.check_schema(payload["output_schema"])
        definition = AgentDefinition.create(
            **{
                **payload,
                "capabilities": tuple(payload["capabilities"]),
                "provider_profile_id": provider.id,
                "identifier": identifier,
            }
        )
        capabilities.update(definition.capabilities)
        await registry.register_agent(definition)

    spec = parse_workflow_yaml(
        (EXAMPLES / "article-analysis.yaml").read_text(encoding="utf-8")
    )
    await validate_workflow(spec, registry)

    assert capabilities == {
        "screen-content",
        "extract-content-insights",
        "classify-content",
        "score-content-quality",
        "review-content-analysis",
        "finalize-content-analysis",
    }
    assert spec.topological_order() == (
        "reference",
        "screening",
        "initial_gate",
        "resolve",
        "core_analysis",
        "taxonomy",
        "quality_scoring",
        "review",
        "finalize",
        "deterministic_score",
        "fine_gate",
    )
    assert "update_reasons" not in str(spec.output)
