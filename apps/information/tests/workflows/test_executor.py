from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.bootstrap.runtime import build_workflow_executor
from zeromind.ingestion.domain import FeedEntry
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.shared.config import Settings
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import parse_workflow_yaml
from zeromind.workflows.executor import NodeExecutionContext, WorkflowExecutor
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


async def reference_repository() -> tuple[InMemoryReferenceRepository, UUID]:
    repository = InMemoryReferenceRepository()
    service = IngestionService(repository)
    subscription_id = UUID("11111111-1111-1111-1111-111111111111")
    first = FeedEntry(
        guid="runtime",
        url="https://example.com/runtime",
        title="Version one",
        summary="First summary",
        author="Ada",
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=None,
    )
    second = FeedEntry(
        guid="runtime",
        url="https://example.com/runtime",
        title="Version two",
        summary="Second summary",
        author="Ada",
        published_at=datetime(2026, 7, 29, tzinfo=UTC),
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    await service.ingest(
        subscription_id=subscription_id,
        entries=(first,),
        fetched_at=datetime(2026, 7, 29, 12, tzinfo=UTC),
    )
    await service.ingest(
        subscription_id=subscription_id,
        entries=(second,),
        fetched_at=datetime(2026, 7, 30, 12, tzinfo=UTC),
    )
    reference = (await repository.list_references())[0]
    return repository, reference.id


def runtime_executor(
    workflows: InMemoryWorkflowRepository,
    references: InMemoryReferenceRepository,
) -> WorkflowExecutor:
    return build_workflow_executor(
        workflow_repository=workflows,
        reference_repository=references,
        agent_registry=AgentRegistry(InMemoryAgentRepository()),
        settings=Settings(pi_command="true"),
    )


@pytest.mark.asyncio
async def test_executor_resolves_mappings_dependencies_and_output() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(parse_workflow_yaml(SOURCE))
    await repository.add_definition(definition)
    calls: list[str] = []

    async def resolve(
        input: dict[str, object], _: NodeExecutionContext
    ) -> dict[str, object]:
        calls.append("resolve")
        assert input["reference_id"] == "ref-1"
        return {"title": "Article"}

    async def agent(
        input: dict[str, object], _: NodeExecutionContext
    ) -> dict[str, object]:
        calls.append("agent")
        return (
            {"summary": f"Summary of {input['title']}"}
            if calls.count("agent") == 1
            else {"category": "technology"}
        )

    async def parallel(
        input: dict[str, object], _: NodeExecutionContext
    ) -> dict[str, object]:
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
async def test_executor_persists_step_before_passing_execution_context() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: contextual-agent
trigger: {events: [manual]}
nodes:
  - id: analyze
    type: agent
    agent_id: 44444444-4444-4444-4444-444444444444
    retry: {max_attempts: 2, backoff_seconds: 0}
output: {ok: $.steps.analyze.ok}
"""
        )
    )
    await repository.add_definition(definition)
    contexts: list[NodeExecutionContext] = []

    async def agent(
        _: dict[str, object], context: NodeExecutionContext
    ) -> dict[str, object]:
        persisted = await repository.get_run(context.workflow_run_id)
        assert persisted is not None
        assert [step.id for step in persisted.steps] == [context.step_run_id]
        assert persisted.steps[0].attempts == context.attempt
        contexts.append(context)
        if context.attempt == 1:
            raise RuntimeError("retry")
        return {"ok": True}

    run = await WorkflowExecutor(repository, handlers={"agent": agent}).execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:context",
    )

    assert [context.attempt for context in contexts] == [1, 2]
    assert all(context.workflow_run_id == run.id for context in contexts)
    assert contexts[0].step_run_id == contexts[1].step_run_id
    assert contexts[0].agent_id == UUID(
        "44444444-4444-4444-4444-444444444444"
    )


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

    async def handler(
        _: dict[str, object], __: NodeExecutionContext
    ) -> dict[str, object]:
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


@pytest.mark.asyncio
async def test_executor_never_persists_transient_resolved_article_text() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: transient
trigger: {events: [manual]}
nodes:
  - id: resolve
    type: resolve
  - id: analyze
    type: agent
    agent_id: 44444444-4444-4444-4444-444444444444
    depends_on: [resolve]
    input: {document: $.steps.resolve}
output: {analysis: $.steps.analyze}
"""
        )
    )
    await repository.add_definition(definition)

    async def resolve(
        _: dict[str, object], __: NodeExecutionContext
    ) -> dict[str, object]:
        return {
            "_transient_document": True,
            "title": "Safe metadata",
            "text": "ARTICLE BODY MUST NOT BE STORED",
        }

    async def analyze(
        input: dict[str, object], _: NodeExecutionContext
    ) -> dict[str, object]:
        assert "ARTICLE BODY" in str(input)
        return {"summary": "Structured result"}

    run = await WorkflowExecutor(
        repository,
        handlers={"resolve": resolve, "agent": analyze},
    ).execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:transient",
    )

    persisted = await repository.get_run(run.id)
    assert persisted is not None
    assert "ARTICLE BODY" not in str(persisted)
    assert persisted.output == {"analysis": {"summary": "Structured result"}}


@pytest.mark.asyncio
async def test_gate_rejection_completes_without_starting_later_nodes() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: gated
trigger: {events: [manual]}
nodes:
  - id: prepare
    type: parallel
  - id: gate
    type: gate
    depends_on: [prepare]
    predicate:
      left: $.steps.prepare.score
      operator: gte
      right: 70
    reject:
      output: {status: initial_rejected}
  - id: expensive
    type: parallel
    depends_on: [gate]
output: {status: qualified}
"""
        )
    )
    await repository.add_definition(definition)
    calls: list[str] = []

    async def prepare(
        _: dict[str, object], __: NodeExecutionContext
    ) -> dict[str, object]:
        calls.append("prepare")
        return {"score": 20}

    async def expensive(
        _: dict[str, object], __: NodeExecutionContext
    ) -> dict[str, object]:
        calls.append("expensive")
        return {"completed": True}

    run = await WorkflowExecutor(
        repository,
        handlers={"parallel": prepare, "expensive": expensive},
    ).execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:gate-reject",
    )

    assert run.status == "completed"
    assert run.output == {"status": "initial_rejected"}
    assert calls == ["prepare"]
    assert [step.node_id for step in run.steps] == ["prepare", "gate"]
    assert run.steps[-1].output == {
        "passed": False,
        "operator": "gte",
        "left": 20,
        "right": 70,
        "terminal_status": "initial_rejected",
    }


@pytest.mark.asyncio
async def test_gate_passes_control_to_later_nodes() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: passing-gate
trigger: {events: [manual]}
nodes:
  - {id: prepare, type: parallel}
  - id: gate
    type: gate
    depends_on: [prepare]
    predicate: {left: $.steps.prepare.score, operator: gte, right: 70}
    reject: {output: {status: rejected}}
  - {id: expensive, type: parallel, depends_on: [gate]}
output:
  status: qualified
  result: $.steps.expensive.result
"""
        )
    )
    await repository.add_definition(definition)
    calls: list[str] = []

    async def handler(
        input: dict[str, object], _: NodeExecutionContext
    ) -> dict[str, object]:
        if not calls:
            calls.append("prepare")
            return {"score": 90}
        calls.append("expensive")
        return {"result": "analyzed"}

    run = await WorkflowExecutor(
        repository,
        handlers={"parallel": handler},
    ).execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:gate-pass",
    )

    assert run.status == "completed"
    assert run.output == {"status": "qualified", "result": "analyzed"}
    assert calls == ["prepare", "expensive"]
    assert run.steps[1].output == {
        "passed": True,
        "operator": "gte",
        "left": 90,
        "right": 70,
    }


@pytest.mark.asyncio
async def test_gate_rejection_never_persists_transient_article_text() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: transient-gate
trigger: {events: [manual]}
nodes:
  - {id: prepare, type: parallel}
  - id: gate
    type: gate
    depends_on: [prepare]
    predicate: {left: 0, operator: gte, right: 1}
    reject:
      output:
        status: rejected
        document: $.steps.prepare
output: {status: qualified}
"""
        )
    )
    await repository.add_definition(definition)

    async def prepare(
        _: dict[str, object], __: NodeExecutionContext
    ) -> dict[str, object]:
        return {
            "_transient_document": True,
            "title": "Safe metadata",
            "text": "ARTICLE BODY MUST NOT BE STORED",
        }

    run = await WorkflowExecutor(
        repository,
        handlers={"parallel": prepare},
    ).execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:transient-gate",
    )

    persisted = await repository.get_run(run.id)
    assert persisted is not None
    assert "ARTICLE BODY" not in str(persisted)
    assert persisted.output == {
        "status": "rejected",
        "document": {"title": "Safe metadata"},
    }


@pytest.mark.asyncio
async def test_passing_gate_never_persists_transient_predicate_operands() -> None:
    repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: transient-passing-gate
trigger: {events: [manual]}
nodes:
  - {id: prepare, type: parallel}
  - id: gate
    type: gate
    depends_on: [prepare]
    predicate: {left: $.steps.prepare, operator: ne, right: null}
    reject: {output: {status: rejected}}
output: {status: qualified}
"""
        )
    )
    await repository.add_definition(definition)

    async def prepare(
        _: dict[str, object], __: NodeExecutionContext
    ) -> dict[str, object]:
        return {
            "_transient_document": True,
            "title": "Safe metadata",
            "text": "ARTICLE BODY MUST NOT BE STORED",
        }

    run = await WorkflowExecutor(
        repository,
        handlers={"parallel": prepare},
    ).execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:transient-passing-gate",
    )

    persisted = await repository.get_run(run.id)
    assert persisted is not None
    assert "ARTICLE BODY" not in str(persisted)


@pytest.mark.asyncio
async def test_reference_node_reads_the_requested_revision() -> None:
    references, reference_id = await reference_repository()
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: reference-revision
trigger: {events: [manual]}
nodes:
  - id: metadata
    type: reference
    input:
      reference_id: $.trigger.reference_id
      revision: 1
output: {metadata: $.steps.metadata}
"""
        )
    )
    await workflows.add_definition(definition)

    run = await runtime_executor(workflows, references).execute(
        definition.id,
        trigger={"event": "manual", "reference_id": str(reference_id)},
        idempotency_key="manual:reference-revision",
    )

    assert run.output is not None
    assert run.output["metadata"] == {
        "reference_id": str(reference_id),
        "revision": 1,
        "subscription_id": "11111111-1111-1111-1111-111111111111",
        "url": "https://example.com/runtime",
        "title": "Version one",
        "summary": "First summary",
        "author": "Ada",
        "published_at": "2026-07-29T00:00:00+00:00",
        "updated_at": None,
        "observed_at": "2026-07-29T12:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_score_node_uses_deterministic_weighted_scoring() -> None:
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: deterministic-score
trigger: {events: [manual]}
nodes:
  - id: score
    type: score
    input:
      dimensions:
        depth: {value: 90, weight: 0.6, reason: Detailed}
        clarity: {value: 80, weight: 0.4, reason: Clear}
output: {score: $.steps.score}
"""
        )
    )
    await workflows.add_definition(definition)

    run = await runtime_executor(
        workflows,
        InMemoryReferenceRepository(),
    ).execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="manual:deterministic-score",
    )

    assert run.output is not None
    assert run.output["score"] == {
        "total": 86,
        "dimensions": {
            "depth": {"value": 90, "weight": 0.6, "reason": "Detailed"},
            "clarity": {"value": 80, "weight": 0.4, "reason": "Clear"},
        },
    }


@pytest.mark.asyncio
async def test_reference_node_reports_a_stable_missing_reference_error() -> None:
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: missing-reference
trigger: {events: [manual]}
nodes:
  - id: metadata
    type: reference
    input: {reference_id: $.trigger.reference_id}
"""
        )
    )
    await workflows.add_definition(definition)
    missing_id = UUID("99999999-9999-9999-9999-999999999999")

    with pytest.raises(ValueError, match="reference_not_found"):
        await runtime_executor(
            workflows,
            InMemoryReferenceRepository(),
        ).execute(
            definition.id,
            trigger={"event": "manual", "reference_id": str(missing_id)},
            idempotency_key="manual:missing-reference",
        )

    run = (await workflows.list_runs())[0]
    assert run.error == f"reference_not_found:{missing_id}"


@pytest.mark.asyncio
async def test_reference_node_reports_a_stable_missing_revision_error() -> None:
    references, reference_id = await reference_repository()
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: missing-revision
trigger: {events: [manual]}
nodes:
  - id: metadata
    type: reference
    input:
      reference_id: $.trigger.reference_id
      revision: 99
"""
        )
    )
    await workflows.add_definition(definition)

    with pytest.raises(ValueError, match="reference_revision_not_found"):
        await runtime_executor(workflows, references).execute(
            definition.id,
            trigger={"event": "manual", "reference_id": str(reference_id)},
            idempotency_key="manual:missing-revision",
        )

    run = (await workflows.list_runs())[0]
    assert run.error == f"reference_revision_not_found:{reference_id}:99"
