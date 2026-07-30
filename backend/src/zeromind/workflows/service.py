import uuid
from typing import Protocol

from pydantic import ValidationError

from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.executor import WorkflowExecutor
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
    ) -> None:
        self._repository = repository
        self._executor = executor
        self._projectors = projectors

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
        run = await self._executor.execute(
            definition_id,
            trigger=trigger,
            idempotency_key=idempotency_key,
        )
        projection = definition.spec.projection
        if projection is None:
            return run
        if run.status != "completed":
            raise ValueError(run.error or "workflow run did not complete")
        projector = self._projectors.get(projection)
        if projector is None:
            run.fail_projection(f"no projector registered for {projection}")
            await self._repository.save_run(run)
            raise ValueError(run.error)
        try:
            await projector.project(definition, run)
        except Exception as error:
            run.fail_projection(_projection_error_message(error))
            await self._repository.save_run(run)
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
