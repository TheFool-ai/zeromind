import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from zeromind.workflows.domain import StepRun, WorkflowRun
from zeromind.workflows.dsl import PATH, NodeSpec
from zeromind.workflows.primitives import evaluate_predicate
from zeromind.workflows.repository import WorkflowRepository

NodeHandler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class TerminalNodeResult:
    step_output: dict[str, object]
    workflow_output: dict[str, object]


def resolve_path(path: str, context: dict[str, object]) -> object:
    current: object = context
    for segment in path[2:].split("."):
        if not isinstance(current, dict) or segment not in current:
            raise ValueError(f"mapping path does not exist: {path}")
        current = current[segment]
    return current


def resolve_mapping(value: object, context: dict[str, object]) -> object:
    if isinstance(value, str):
        return resolve_path(value, context) if PATH.fullmatch(value) else value
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
                for node_id, result in zip(layer, results, strict=True):
                    if isinstance(result, TerminalNodeResult):
                        persisted_output = persistent_view(result.workflow_output)
                        if not isinstance(persisted_output, dict):
                            raise ValueError(
                                "gate reject output must resolve to an object"
                            )
                        run.output = persisted_output
                        run.status = "completed"
                        run.completed_at = datetime.now(UTC)
                        await self._repository.save_run(run)
                        return run
                    outputs[node_id] = result
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
    ) -> dict[str, object] | TerminalNodeResult:
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
        if node.type == "gate":
            return self._execute_gate(step, node, context)
        handler = self._handlers.get(node.type)
        if handler is None:
            raise ValueError(f"no handler registered for node type {node.type}")
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

    @staticmethod
    def _execute_gate(
        step: StepRun,
        node: NodeSpec,
        context: dict[str, object],
    ) -> dict[str, object] | TerminalNodeResult:
        predicate_spec = node.predicate
        reject_spec = node.reject
        if predicate_spec is None or reject_spec is None:
            raise ValueError(f"gate {node.id} is missing predicate or reject output")
        step.attempts = 1
        try:
            predicate = {
                "left": resolve_mapping(predicate_spec.left, context),
                "operator": predicate_spec.operator,
                "right": resolve_mapping(predicate_spec.right, context),
            }
            passed = evaluate_predicate(predicate)
            step_output: dict[str, object] = {
                "passed": passed,
                "operator": predicate_spec.operator,
                "left": predicate["left"],
                "right": predicate["right"],
            }
            if passed:
                persisted_step_output = persistent_view(step_output)
                if not isinstance(persisted_step_output, dict):
                    raise ValueError("gate step output must resolve to an object")
                step.output = persisted_step_output
                step.status = "completed"
                step.completed_at = datetime.now(UTC)
                return step_output
            workflow_output = resolve_mapping(reject_spec.output, context)
            if not isinstance(workflow_output, dict):
                raise ValueError("gate reject output must resolve to an object")
            terminal_status = workflow_output.get("status")
            if isinstance(terminal_status, str):
                step_output["terminal_status"] = terminal_status
            persisted_step_output = persistent_view(step_output)
            if not isinstance(persisted_step_output, dict):
                raise ValueError("gate step output must resolve to an object")
            step.output = persisted_step_output
            step.status = "completed"
            step.completed_at = datetime.now(UTC)
            return TerminalNodeResult(
                step_output=step_output,
                workflow_output=workflow_output,
            )
        except Exception as error:
            step.error = str(error)
            step.status = "failed"
            step.completed_at = datetime.now(UTC)
            raise
