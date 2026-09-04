#!/usr/bin/env python3
"""Idempotently register the six analysis agents and their DSL workflow."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.registry import AgentRegistry, SqlAlchemyAgentRepository
from zeromind.shared.database import create_database
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import parse_workflow_yaml, validate_workflow
from zeromind.workflows.presets import upsert_main_analysis_workflow
from zeromind.workflows.repository import SqlAlchemyWorkflowRepository

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
AGENT_FILES = (
    ("screening-agent.json", "00000000-0000-0000-0000-000000000101"),
    ("core-analysis-agent.json", "00000000-0000-0000-0000-000000000102"),
    ("taxonomy-agent.json", "00000000-0000-0000-0000-000000000103"),
    ("quality-scoring-agent.json", "00000000-0000-0000-0000-000000000104"),
    ("review-agent.json", "00000000-0000-0000-0000-000000000105"),
    ("finalizer-agent.json", "00000000-0000-0000-0000-000000000106"),
)


def _payload(path: Path, provider_id: UUID) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    value["provider_profile_id"] = provider_id
    value["capabilities"] = tuple(value["capabilities"])
    return value


async def _provider(
    registry: AgentRegistry,
    *,
    provider_id: UUID | None,
    provider_name: str,
) -> ProviderProfile:
    if provider_id is not None:
        return await registry.get_provider(provider_id)
    matches = [
        item
        for item in await registry.list_providers()
        if item.name.casefold() == provider_name.casefold()
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one enabled provider named {provider_name!r}, found {len(matches)}"
        )
    if not matches[0].enabled:
        raise ValueError(f"provider {provider_name!r} is disabled")
    return matches[0]


async def register_presets(
    *,
    provider_id: UUID | None,
    provider_name: str,
    examples: Path = EXAMPLES,
) -> tuple[tuple[AgentDefinition, ...], WorkflowDefinition]:
    database = create_database()
    try:
        registry = AgentRegistry(SqlAlchemyAgentRepository(database.sessions))
        workflows = SqlAlchemyWorkflowRepository(database.sessions)
        profile = await _provider(
            registry,
            provider_id=provider_id,
            provider_name=provider_name,
        )
        existing_by_name = {
            item.name: item for item in await registry.list_agents()
        }
        registered: list[AgentDefinition] = []
        replacements: dict[str, str] = {}
        for filename, placeholder in AGENT_FILES:
            payload = _payload(examples / filename, profile.id)
            current = existing_by_name.get(str(payload["name"]))
            if current is None:
                current = AgentDefinition.create(**payload)
                await registry.register_agent(current)
            else:
                desired = (
                    payload["system_prompt"],
                    payload["capabilities"],
                    payload["provider_profile_id"],
                    payload["input_schema"],
                    payload["output_schema"],
                )
                actual = (
                    current.system_prompt,
                    current.capabilities,
                    current.provider_profile_id,
                    current.input_schema,
                    current.output_schema,
                )
                if desired != actual:
                    current = await registry.update_agent(
                        current.id,
                        system_prompt=str(payload["system_prompt"]),
                        capabilities=payload["capabilities"],
                        provider_profile_id=profile.id,
                        input_schema=payload["input_schema"],
                        output_schema=payload["output_schema"],
                    )
                if not current.enabled:
                    current = await registry.set_agent_enabled(
                        current.id, enabled=True
                    )
            registered.append(current)
            replacements[placeholder] = str(current.id)

        source = (examples / "article-analysis.yaml").read_text(encoding="utf-8")
        for placeholder, agent_id in replacements.items():
            source = source.replace(placeholder, agent_id)
        spec = parse_workflow_yaml(source)
        await validate_workflow(spec, registry)
        workflow = await upsert_main_analysis_workflow(workflows, spec)
        return tuple(registered), workflow
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-id", type=UUID)
    parser.add_argument("--provider-name", default="GLM")
    args = parser.parse_args()
    agents, workflow = asyncio.run(
        register_presets(
            provider_id=args.provider_id,
            provider_name=args.provider_name,
        )
    )
    print(
        json.dumps(
            {
                "agents": [
                    {"id": str(agent.id), "name": agent.name, "version": agent.version}
                    for agent in agents
                ],
                "workflow": {
                    "id": str(workflow.id),
                    "name": workflow.name,
                    "version": workflow.version,
                    "status": workflow.status,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
