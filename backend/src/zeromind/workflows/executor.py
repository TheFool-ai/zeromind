import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from zeromind.workflows.domain import StepRun, WorkflowRun
from zeromind.workflows.dsl import NodeSpec
from zeromind.workflows.repository import WorkflowRepository

NodeHandler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


def resolve_path(path: str, context: dict[str, object]) -> object:
    current: object = context
    for segment in path[2:].split("."):
        if not isinstance(current, dict) or segment not in current:
            raise ValueError(f"mapping path does not exist: {path}")
        current = current[segment]
    return current


def resolve_mapping(value: object, context: dict[str, object]) -> object:
    if isinstance(value, str):
        return resolve_path(value, context)
    if isinstance(value, dict):
        return {
            str(key): resolve_mapping(item, context)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_mapping(item, context) for item in value]
    return value


def persistent_view(value: object) -> object:
    """Remove transient article bodies before any workflow state is persisted."""
    if isinstance(value, dict):
        transient = value.get("_transient_document") is True
        return {
            str(key): persistent_view(item)
            for key, item in value.items()
            if key != "_transient_document" and not (transient and key == "text")
        }
    if isinstance(value, list):
        return [persistent_view(item) for item in value]
    return value


class WorkflowExecutor:
    def __init__(
        self,
        repository: WorkflowRepository,
        *,
        handlers: dict[str, NodeHandler],
    ) -> None:
        self._repository = repository
        self._handlers = handlers

    async def execute(
        self,
        definition_id: uuid.UUID,
        *,
        trigger: dict[str, object],
        idempotency_key: str,
    ) -> WorkflowRun:
        existing = await self._repository.find_run(
            definition_id,
            idempotency_key,
        )
        if existing:
            return existing
        definition = await self._repository.get_definition(definition_id)
        if definition is None:
            raise KeyError(definition_id)
        now = datetime.now(UTC)
        run = WorkflowRun(
            id=uuid.uuid4(),
            definition_id=definition.id,
            definition_version=definition.version,
            idempotency_key=idempotency_key,
            trigger=trigger,
            status="running",
            output=None,
            error=None,
            started_at=now,
            completed_at=None,
        )
        await self._repository.add_run(run)
        nodes = {node.id: node for node in definition.spec.nodes}
        outputs: dict[str, object] = {}
        try:
            for layer in definition.spec.topological_layers():
                results = await asyncio.gather(
                    *(
                        self._execute_node(
                            run,
                            nodes[node_id],
                            {"trigger": trigger, "steps": outputs},
                        )
                        for node_id in layer
                    )
                )
                outputs.update(dict(zip(layer, results, strict=True)))
            context: dict[str, object] = {"trigger": trigger, "steps": outputs}
            resolved_output = resolve_mapping(definition.spec.output, context)
            if not isinstance(resolved_output, dict):
                raise ValueError("workflow output must resolve to an object")
            persisted_output = persistent_view(resolved_output)
            if not isinstance(persisted_output, dict):
                raise ValueError("workflow output must resolve to an object")
            run.output = persisted_output
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            await self._repository.save_run(run)
            return run
        except Exception as error:
            run.status = "failed"
            run.error = str(error)
            run.completed_at = datetime.now(UTC)
            await self._repository.save_run(run)
            raise

    async def _execute_node(
        self,
        run: WorkflowRun,
        node: NodeSpec,
        context: dict[str, object],
    ) -> dict[str, object]:
        handler = self._handlers.get(node.type)
        if handler is None:
            raise ValueError(f"no handler registered for node type {node.type}")
        resolved = resolve_mapping(node.input, context)
        if not isinstance(resolved, dict):
            raise ValueError(f"node {node.id} input must resolve to an object")
        if node.agent_id:
            resolved["_agent_id"] = str(node.agent_id)
        persisted_input = persistent_view(resolved)
        if not isinstance(persisted_input, dict):
            raise ValueError(f"node {node.id} input must resolve to an object")
        step = StepRun(
            id=uuid.uuid4(),
            run_id=run.id,
            node_id=node.id,
            status="running",
            attempts=0,
            input=persisted_input,
            output=None,
            error=None,
            started_at=datetime.now(UTC),
            completed_at=None,
        )
        run.steps.append(step)
        for attempt in range(1, node.retry.max_attempts + 1):
            step.attempts = attempt
            try:
                async with asyncio.timeout(node.timeout_seconds):
                    result = await handler(resolved)
                persisted_result = persistent_view(result)
                if not isinstance(persisted_result, dict):
                    raise ValueError(f"node {node.id} output must be an object")
                step.output = persisted_result
                step.status = "completed"
                step.completed_at = datetime.now(UTC)
                return result
            except Exception as error:
                step.error = str(error)
                if attempt == node.retry.max_attempts:
                    step.status = "failed"
                    step.completed_at = datetime.now(UTC)
                    raise
                await asyncio.sleep(node.retry.backoff_seconds * attempt)
        raise RuntimeError("unreachable")
