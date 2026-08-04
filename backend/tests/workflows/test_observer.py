from dataclasses import dataclass, field

import pytest

from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import NodeSpec, WorkflowSpec
from zeromind.workflows.executor import NodeExecutionContext, WorkflowExecutor
from zeromind.workflows.repository import InMemoryWorkflowRepository
from zeromind.workflows.service import WorkflowRunService


@dataclass(slots=True)
class RecordingObserver:
    events: list[str] = field(default_factory=list)

    async def run_created(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> None:
        self.events.append(f"created:{run.id}")

    async def step_started(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        node: NodeSpec,
    ) -> None:
        assert run.steps[-1].node_id == node.id
        self.events.append(f"step:{node.id}")

    async def run_projected(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> None:
        self.events.append(f"projected:{run.id}")

    async def run_failed(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        error: Exception,
    ) -> None:
        self.events.append(f"failed:{run.id}")


@pytest.mark.asyncio
async def test_executor_observes_persisted_step_before_handler() -> None:
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        WorkflowSpec.model_validate(
            {
                "name": "observed",
                "trigger": {"events": ["manual"]},
                "nodes": [{"id": "work", "type": "parallel"}],
                "output": {"ok": "$.steps.work.ok"},
            }
        )
    )
    await workflows.add_definition(definition)
    observer = RecordingObserver()

    async def handler(
        _: dict[str, object],
        context: NodeExecutionContext,
    ) -> dict[str, object]:
        stored = await workflows.get_run(context.workflow_run_id)
        assert stored is not None
        assert stored.steps[-1].id == context.step_run_id
        assert observer.events[-1] == "step:work"
        observer.events.append("handler")
        return {"ok": True}

    run = await WorkflowExecutor(
        workflows,
        handlers={"parallel": handler},
        observer=observer,
    ).execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="observed:1",
    )

    assert run.status == "completed"
    assert observer.events[0].startswith("created:")
    assert observer.events[1:] == ["step:work", "handler"]


@pytest.mark.asyncio
async def test_service_observes_projection_only_after_projector_success() -> None:
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        WorkflowSpec.model_validate(
            {
                "name": "projected",
                "trigger": {"events": ["manual"]},
                "projection": "content_analysis_v1",
                "nodes": [{"id": "work", "type": "parallel"}],
                "output": {"ok": "$.steps.work.ok"},
            }
        )
    )
    await workflows.add_definition(definition)
    observer = RecordingObserver()

    async def handler(
        _: dict[str, object],
        __: NodeExecutionContext,
    ) -> dict[str, object]:
        return {"ok": True}

    class Projector:
        async def project(
            self,
            definition: WorkflowDefinition,
            run: WorkflowRun,
        ) -> None:
            assert not any(event.startswith("projected:") for event in observer.events)
            observer.events.append("projector")

    executor = WorkflowExecutor(
        workflows,
        handlers={"parallel": handler},
        observer=observer,
    )
    service = WorkflowRunService(
        workflows,
        executor,
        projectors={"content_analysis_v1": Projector()},
        observer=observer,
    )

    await service.execute(
        definition.id,
        trigger={"event": "manual"},
        idempotency_key="projected:1",
    )

    assert observer.events[-2] == "projector"
    assert observer.events[-1].startswith("projected:")


@pytest.mark.asyncio
async def test_observer_error_fails_step_and_run() -> None:
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        WorkflowSpec.model_validate(
            {
                "name": "observer-failure",
                "trigger": {"events": ["manual"]},
                "nodes": [{"id": "work", "type": "parallel"}],
            }
        )
    )
    await workflows.add_definition(definition)

    class FailingObserver(RecordingObserver):
        async def step_started(
            self,
            definition: WorkflowDefinition,
            run: WorkflowRun,
            node: NodeSpec,
        ) -> None:
            raise RuntimeError("observer unavailable")

    observer = FailingObserver()
    executor = WorkflowExecutor(
        workflows,
        handlers={},
        observer=observer,
    )
    service = WorkflowRunService(
        workflows,
        executor,
        projectors={},
        observer=observer,
    )

    with pytest.raises(RuntimeError, match="observer unavailable"):
        await service.execute(
            definition.id,
            trigger={"event": "manual"},
            idempotency_key="observer-failure:1",
        )

    run = (await workflows.list_runs())[0]
    assert run.status == "failed"
    assert run.steps[0].status == "failed"
    assert observer.events[-1].startswith("failed:")
