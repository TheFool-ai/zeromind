import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.agents.models import AgentSessionModel
from zeromind.agents.session_domain import AgentSession, AgentSessionStatus


class AgentSessionRepository(Protocol):
    async def add(self, value: AgentSession) -> None: ...

    async def save(self, value: AgentSession) -> None: ...

    async def get(self, session_id: uuid.UUID) -> AgentSession | None: ...

    async def list(
        self,
        *,
        workflow_run_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        status: AgentSessionStatus | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
    ) -> tuple[AgentSession, ...]: ...

    async def fail_stale(self, *, before: datetime, now: datetime) -> int: ...


class InMemoryAgentSessionRepository:
    def __init__(self) -> None:
        self._values: dict[uuid.UUID, AgentSession] = {}

    async def add(self, value: AgentSession) -> None:
        if value.id in self._values or any(
            item.step_run_id == value.step_run_id and item.attempt == value.attempt
            for item in self._values.values()
        ):
            raise ValueError("agent session already exists")
        self._values[value.id] = value

    async def save(self, value: AgentSession) -> None:
        if value.id not in self._values:
            raise KeyError(value.id)
        self._values[value.id] = value

    async def get(self, session_id: uuid.UUID) -> AgentSession | None:
        return self._values.get(session_id)

    async def list(
        self,
        *,
        workflow_run_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        status: AgentSessionStatus | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
    ) -> tuple[AgentSession, ...]:
        return tuple(
            item
            for item in sorted(self._values.values(), key=lambda value: value.started_at)
            if (workflow_run_id is None or item.workflow_run_id == workflow_run_id)
            and (agent_id is None or item.agent_id == agent_id)
            and (status is None or item.status == status)
            and (started_from is None or item.started_at >= started_from)
            and (started_to is None or item.started_at <= started_to)
        )

    async def fail_stale(self, *, before: datetime, now: datetime) -> int:
        changed = 0
        for value in self._values.values():
            if value.status == "running" and value.started_at < before:
                value.fail(
                    status="protocol_failed",
                    error_code="stale_session_recovered",
                    error_message="agent process ended before recording a terminal result",
                    now=now,
                )
                changed += 1
        return changed


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _domain(model: AgentSessionModel) -> AgentSession:
    return AgentSession(
        id=model.id,
        workflow_run_id=model.workflow_run_id,
        step_run_id=model.step_run_id,
        agent_id=model.agent_id,
        agent_version_id=model.agent_version_id,
        attempt=model.attempt,
        provider=model.provider,
        model=model.model,
        thinking_level=model.thinking_level,
        sanitized_input=model.sanitized_input,
        document_sha256=model.document_sha256,
        document_character_count=model.document_character_count,
        output=model.output,
        response_sha256=model.response_sha256,
        response_character_count=model.response_character_count,
        usage=model.usage,
        status=model.status,  # type: ignore[arg-type]
        error_code=model.error_code,
        error_message=model.error_message,
        started_at=_as_utc(model.started_at),
        completed_at=_as_utc(model.completed_at) if model.completed_at else None,
    )


class SqlAlchemyAgentSessionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, value: AgentSession) -> None:
        async with self._sessions() as session, session.begin():
            session.add(self._model(value))

    async def save(self, value: AgentSession) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(AgentSessionModel, value.id)
            if model is None:
                raise KeyError(value.id)
            if model.status != "running":
                raise ValueError("agent session is already terminal")
            model.output = value.output
            model.response_sha256 = value.response_sha256
            model.response_character_count = value.response_character_count
            model.usage = value.usage
            model.status = value.status
            model.error_code = value.error_code
            model.error_message = value.error_message
            model.completed_at = value.completed_at

    async def get(self, session_id: uuid.UUID) -> AgentSession | None:
        async with self._sessions() as session:
            model = await session.get(AgentSessionModel, session_id)
            return _domain(model) if model else None

    async def list(
        self,
        *,
        workflow_run_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        status: AgentSessionStatus | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
    ) -> tuple[AgentSession, ...]:
        statement = select(AgentSessionModel)
        if workflow_run_id is not None:
            statement = statement.where(
                AgentSessionModel.workflow_run_id == workflow_run_id
            )
        if agent_id is not None:
            statement = statement.where(AgentSessionModel.agent_id == agent_id)
        if status is not None:
            statement = statement.where(AgentSessionModel.status == status)
        if started_from is not None:
            statement = statement.where(AgentSessionModel.started_at >= started_from)
        if started_to is not None:
            statement = statement.where(AgentSessionModel.started_at <= started_to)
        async with self._sessions() as session:
            models = await session.scalars(
                statement.order_by(AgentSessionModel.started_at)
            )
            return tuple(_domain(model) for model in models)

    async def fail_stale(self, *, before: datetime, now: datetime) -> int:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(AgentSessionModel)
                .where(
                    AgentSessionModel.status == "running",
                    AgentSessionModel.started_at < before,
                )
                .values(
                    status="protocol_failed",
                    error_code="stale_session_recovered",
                    error_message=(
                        "agent process ended before recording a terminal result"
                    ),
                    completed_at=now,
                )
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    @staticmethod
    def _model(value: AgentSession) -> AgentSessionModel:
        return AgentSessionModel(
            id=value.id,
            workflow_run_id=value.workflow_run_id,
            step_run_id=value.step_run_id,
            agent_id=value.agent_id,
            agent_version_id=value.agent_version_id,
            attempt=value.attempt,
            provider=value.provider,
            model=value.model,
            thinking_level=value.thinking_level,
            sanitized_input=value.sanitized_input,
            document_sha256=value.document_sha256,
            document_character_count=value.document_character_count,
            output=value.output,
            response_sha256=value.response_sha256,
            response_character_count=value.response_character_count,
            usage=value.usage,
            status=value.status,
            error_code=value.error_code,
            error_message=value.error_message,
            started_at=value.started_at,
            completed_at=value.completed_at,
        )
