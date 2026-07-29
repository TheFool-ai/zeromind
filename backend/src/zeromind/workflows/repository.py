import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import WorkflowSpec
from zeromind.workflows.models import (
    StepRunModel,
    WorkflowDefinitionModel,
    WorkflowRunModel,
)


class WorkflowRepository(Protocol):
    async def add_definition(self, definition: WorkflowDefinition) -> None: ...

    async def save_definition(self, definition: WorkflowDefinition) -> None: ...

    async def get_definition(
        self,
        definition_id: uuid.UUID,
    ) -> WorkflowDefinition | None: ...

    async def list_definitions(self) -> tuple[WorkflowDefinition, ...]: ...

    async def find_run(
        self,
        definition_id: uuid.UUID,
        idempotency_key: str,
    ) -> WorkflowRun | None: ...

    async def add_run(self, run: WorkflowRun) -> None: ...

    async def save_run(self, run: WorkflowRun) -> None: ...

    async def get_run(self, run_id: uuid.UUID) -> WorkflowRun | None: ...

    async def list_runs(self) -> tuple[WorkflowRun, ...]: ...


class InMemoryWorkflowRepository:
    def __init__(self) -> None:
        self._definitions: dict[uuid.UUID, WorkflowDefinition] = {}
        self._runs: dict[uuid.UUID, WorkflowRun] = {}
        self._run_keys: dict[tuple[uuid.UUID, str], uuid.UUID] = {}

    async def add_definition(self, definition: WorkflowDefinition) -> None:
        if any(item.name == definition.name for item in self._definitions.values()):
            raise ValueError("duplicate workflow name")
        self._definitions[definition.id] = definition

    async def save_definition(self, definition: WorkflowDefinition) -> None:
        if definition.id not in self._definitions:
            raise KeyError(definition.id)
        self._definitions[definition.id] = definition

    async def get_definition(
        self,
        definition_id: uuid.UUID,
    ) -> WorkflowDefinition | None:
        return self._definitions.get(definition_id)

    async def list_definitions(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._definitions.values())

    async def find_run(
        self,
        definition_id: uuid.UUID,
        idempotency_key: str,
    ) -> WorkflowRun | None:
        run_id = self._run_keys.get((definition_id, idempotency_key))
        return self._runs.get(run_id) if run_id else None

    async def add_run(self, run: WorkflowRun) -> None:
        key = (run.definition_id, run.idempotency_key)
        if key in self._run_keys:
            raise ValueError("duplicate workflow run")
        self._runs[run.id] = run
        self._run_keys[key] = run.id

    async def save_run(self, run: WorkflowRun) -> None:
        if run.id not in self._runs:
            raise KeyError(run.id)
        self._runs[run.id] = run

    async def get_run(self, run_id: uuid.UUID) -> WorkflowRun | None:
        return self._runs.get(run_id)

    async def list_runs(self) -> tuple[WorkflowRun, ...]:
        return tuple(self._runs.values())


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _definition_domain(model: WorkflowDefinitionModel) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=model.id,
        name=model.name,
        spec=WorkflowSpec.model_validate(model.spec),
        version=model.version,
        status=model.status,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class SqlAlchemyWorkflowRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add_definition(self, definition: WorkflowDefinition) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                WorkflowDefinitionModel(
                    id=definition.id,
                    name=definition.name,
                    spec=definition.spec.model_dump(mode="json"),
                    version=definition.version,
                    status=definition.status,
                    created_at=definition.created_at,
                    updated_at=definition.updated_at,
                )
            )
            try:
                await session.flush()
            except IntegrityError as error:
                raise ValueError("duplicate workflow name") from error

    async def save_definition(self, definition: WorkflowDefinition) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(WorkflowDefinitionModel, definition.id)
            if model is None:
                raise KeyError(definition.id)
            model.name = definition.name
            model.spec = definition.spec.model_dump(mode="json")
            model.version = definition.version
            model.status = definition.status
            model.updated_at = definition.updated_at

    async def get_definition(
        self,
        definition_id: uuid.UUID,
    ) -> WorkflowDefinition | None:
        async with self._sessions() as session:
            model = await session.get(WorkflowDefinitionModel, definition_id)
            return _definition_domain(model) if model else None

    async def list_definitions(self) -> tuple[WorkflowDefinition, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(WorkflowDefinitionModel).order_by(
                    WorkflowDefinitionModel.name
                )
            )
            return tuple(_definition_domain(model) for model in models)

    async def find_run(
        self,
        definition_id: uuid.UUID,
        idempotency_key: str,
    ) -> WorkflowRun | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(WorkflowRunModel).where(
                    WorkflowRunModel.definition_id == definition_id,
                    WorkflowRunModel.idempotency_key == idempotency_key,
                )
            )
            return await self._run_domain(session, model) if model else None

    async def add_run(self, run: WorkflowRun) -> None:
        async with self._sessions() as session, session.begin():
            session.add(self._run_model(run))
            try:
                await session.flush()
            except IntegrityError as error:
                raise ValueError("duplicate workflow run") from error

    async def save_run(self, run: WorkflowRun) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(WorkflowRunModel, run.id)
            if model is None:
                raise KeyError(run.id)
            model.status = run.status
            model.output = run.output
            model.error = run.error
            model.completed_at = run.completed_at
            await session.execute(
                delete(StepRunModel).where(StepRunModel.run_id == run.id)
            )
            await session.flush()
            session.add_all(
                [
                    StepRunModel(
                        id=step.id,
                        run_id=step.run_id,
                        node_id=step.node_id,
                        status=step.status,
                        attempts=step.attempts,
                        input=step.input,
                        output=step.output,
                        error=step.error,
                        started_at=step.started_at,
                        completed_at=step.completed_at,
                    )
                    for step in run.steps
                ]
            )

    async def get_run(self, run_id: uuid.UUID) -> WorkflowRun | None:
        async with self._sessions() as session:
            model = await session.get(WorkflowRunModel, run_id)
            return await self._run_domain(session, model) if model else None

    async def list_runs(self) -> tuple[WorkflowRun, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(WorkflowRunModel).order_by(
                    WorkflowRunModel.started_at.desc()
                )
            )
            return tuple(
                [await self._run_domain(session, model) for model in models]
            )

    @staticmethod
    def _run_model(run: WorkflowRun) -> WorkflowRunModel:
        return WorkflowRunModel(
            id=run.id,
            definition_id=run.definition_id,
            definition_version=run.definition_version,
            idempotency_key=run.idempotency_key,
            trigger=run.trigger,
            status=run.status,
            output=run.output,
            error=run.error,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )

    @staticmethod
    async def _run_domain(
        session: AsyncSession,
        model: WorkflowRunModel,
    ) -> WorkflowRun:
        step_models = await session.scalars(
            select(StepRunModel)
            .where(StepRunModel.run_id == model.id)
            .order_by(StepRunModel.started_at)
        )
        from zeromind.workflows.domain import StepRun

        return WorkflowRun(
            id=model.id,
            definition_id=model.definition_id,
            definition_version=model.definition_version,
            idempotency_key=model.idempotency_key,
            trigger=model.trigger,
            status=model.status,
            output=model.output,
            error=model.error,
            started_at=_as_utc(model.started_at),
            completed_at=_as_utc(model.completed_at) if model.completed_at else None,
            steps=[
                StepRun(
                    id=step.id,
                    run_id=step.run_id,
                    node_id=step.node_id,
                    status=step.status,
                    attempts=step.attempts,
                    input=step.input,
                    output=step.output,
                    error=step.error,
                    started_at=_as_utc(step.started_at),
                    completed_at=(
                        _as_utc(step.completed_at) if step.completed_at else None
                    ),
                )
                for step in step_models
            ],
        )
