from typing import Protocol

from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import NodeSpec


class WorkflowLifecycleObserver(Protocol):
    async def run_created(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> None: ...

    async def step_started(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        node: NodeSpec,
    ) -> None: ...

    async def run_projected(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> None: ...

    async def run_failed(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        error: Exception,
    ) -> None: ...


class NullWorkflowLifecycleObserver:
    async def run_created(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> None:
        return None

    async def step_started(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        node: NodeSpec,
    ) -> None:
        return None

    async def run_projected(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> None:
        return None

    async def run_failed(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        error: Exception,
    ) -> None:
        return None

