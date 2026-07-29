from collections.abc import Awaitable, Callable

import pytest

from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import parse_workflow_yaml
from zeromind.workflows.executor import WorkflowExecutor
from zeromind.workflows.repository import InMemoryWorkflowRepository

Handler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]

SOURCE = """
name: parallel-analysis
trigger: {events: [manual]}
nodes:
  - id: resolve
    type: resolve
    input:
      reference_id: $.trigger.reference_id
  - id: summarize
    type: agent
    agent_id: 44444444-4444-4444-4444-444444444444
    depends_on: [resolve]
    input:
      title: $.steps.resolve.title
  - id: classify
    type: agent
    agent_id: 55555555-5555-5555-5555-555555555555
    depends_on: [resolve]
    input:
      title: $.steps.resolve.title
  - id: combine
    type: parallel
    depends_on: [summarize, classify]
    input:
      summary: $.steps.summarize.summary
      category: $.steps.classify.category
output:
  summary: $.steps.combine.summary
  category: $.steps.combine.category
"""


@pytest.mark.asyncio
async def test_executor_resolves_mappings_dependencies_and_output() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(parse_workflow_yaml(SOURCE))
    await repository.add_definition(definition)
    calls: list[str] = []

    async def resolve(input: dict[str, object]) -> dict[str, object]:
        calls.append("resolve")
        assert input["reference_id"] == "ref-1"
        return {"title": "Article"}

    async def agent(input: dict[str, object]) -> dict[str, object]:
        calls.append("agent")
        return (
            {"summary": f"Summary of {input['title']}"}
            if calls.count("agent") == 1
            else {"category": "technology"}
        )

    async def parallel(input: dict[str, object]) -> dict[str, object]:
        calls.append("parallel")
        return input

    executor = WorkflowExecutor(
        repository,
        handlers={"resolve": resolve, "agent": agent, "parallel": parallel},
    )

    run = await executor.execute(
        definition.id,
        trigger={"event": "manual", "reference_id": "ref-1"},
        idempotency_key="manual:request-1",
    )

    assert calls[0] == "resolve"
    assert calls[-1] == "parallel"
    assert run.output == {
        "summary": "Summary of Article",
        "category": "technology",
    }
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_executor_returns_existing_run_for_same_idempotency_key() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: one
trigger: {events: [manual]}
nodes:
  - {id: node, type: parallel}
output: {value: $.steps.node.value}
"""
        )
    )
    await repository.add_definition(definition)
    executions = 0

    async def handler(_: dict[str, object]) -> dict[str, object]:
        nonlocal executions
        executions += 1
        return {"value": executions}

    executor = WorkflowExecutor(repository, handlers={"parallel": handler})

    first = await executor.execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:same",
    )
    second = await executor.execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:same",
    )

    assert first.id == second.id
    assert executions == 1
