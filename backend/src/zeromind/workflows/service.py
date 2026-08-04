import uuid
from typing import Protocol

from pydantic import ValidationError

from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.executor import WorkflowExecutor
from zeromind.workflows.observer import (
    NullWorkflowLifecycleObserver,
    WorkflowLifecycleObserver,
)
from zeromind.workflows.repository import WorkflowRepository


class WorkflowResultProjector(Protocol):
    async def project(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> object | None: ...


class WorkflowRunService:
    def __init__(
        self,
        repository: WorkflowRepository,
        executor: WorkflowExecutor,
        projectors: dict[str, WorkflowResultProjector],
        observer: WorkflowLifecycleObserver | None = None,
    ) -> None:
        self._repository = repository
        self._executor = executor
        self._projectors = projectors
        self._observer = observer or NullWorkflowLifecycleObserver()

    async def execute(
        self,
        definition_id: uuid.UUID,
        *,
        trigger: dict[str, object],
        idempotency_key: str,
    ) -> WorkflowRun:
        definition = await self._repository.get_definition(definition_id)
        if definition is None:
            raise KeyError(definition_id)
        try:
            run = await self._executor.execute(
                definition_id,
                trigger=trigger,
                idempotency_key=idempotency_key,
            )
        except Exception as error:
            failed = await self._repository.find_run(definition_id, idempotency_key)
            if failed is not None:
                await self._observer.run_failed(definition, failed, error)
            raise
        projection = definition.spec.projection
        if projection is None:
            return run
        if run.status != "completed":
            raise ValueError(run.error or "workflow run did not complete")
        projector = self._projectors.get(projection)
        if projector is None:
            run.fail_projection(f"no projector registered for {projection}")
            await self._repository.save_run(run)
            missing_projector_error = ValueError(run.error)
            await self._observer.run_failed(
                definition,
                run,
                missing_projector_error,
            )
            raise missing_projector_error
        try:
            await projector.project(definition, run)
            await self._observer.run_projected(definition, run)
        except Exception as error:
            run.fail_projection(_projection_error_message(error))
            await self._repository.save_run(run)
            await self._observer.run_failed(definition, run, error)
            raise ValueError(run.error) from error
        return run


def _projection_error_message(error: Exception) -> str:
    if isinstance(error, ValidationError):
        messages = tuple(
            str(item["msg"])
            for item in error.errors(include_input=False, include_url=False)
        )
        return "; ".join(messages)[:1000]
    return str(error).splitlines()[0][:1000]
