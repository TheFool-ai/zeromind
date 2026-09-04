import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

AgentSessionStatus = Literal[
    "running",
    "completed",
    "provider_failed",
    "timed_out",
    "protocol_failed",
    "json_invalid",
    "schema_invalid",
    "cancelled",
]
AgentSessionFailureStatus = Literal[
    "provider_failed",
    "timed_out",
    "protocol_failed",
    "json_invalid",
    "schema_invalid",
    "cancelled",
]


@dataclass(frozen=True, slots=True)
class AgentExecutionContext:
    workflow_run_id: uuid.UUID
    step_run_id: uuid.UUID
    attempt: int


@dataclass(slots=True)
class AgentSession:
    id: uuid.UUID
    workflow_run_id: uuid.UUID
    step_run_id: uuid.UUID
    agent_id: uuid.UUID
    agent_version_id: uuid.UUID
    attempt: int
    provider: str
    model: str
    thinking_level: str
    sanitized_input: dict[str, object]
    document_sha256: str | None
    document_character_count: int | None
    output: dict[str, object] | None
    response_sha256: str | None
    response_character_count: int | None
    usage: dict[str, int | float] | None
    status: AgentSessionStatus
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None

    @classmethod
    def start(
        cls,
        *,
        context: AgentExecutionContext,
        agent_id: uuid.UUID,
        agent_version_id: uuid.UUID,
        provider: str,
        model: str,
        thinking_level: str,
        sanitized_input: dict[str, object],
        document_sha256: str | None,
        document_character_count: int | None,
        now: datetime | None = None,
    ) -> "AgentSession":
        if context.attempt < 1:
            raise ValueError("agent session attempt must be positive")
        return cls(
            id=uuid.uuid4(),
            workflow_run_id=context.workflow_run_id,
            step_run_id=context.step_run_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            attempt=context.attempt,
            provider=provider,
            model=model,
            thinking_level=thinking_level,
            sanitized_input=dict(sanitized_input),
            document_sha256=document_sha256,
            document_character_count=document_character_count,
            output=None,
            response_sha256=None,
            response_character_count=None,
            usage=None,
            status="running",
            error_code=None,
            error_message=None,
            started_at=now or datetime.now(UTC),
            completed_at=None,
        )

    def _ensure_running(self) -> None:
        if self.status != "running":
            raise ValueError("agent session is already terminal")

    def complete(
        self,
        *,
        output: dict[str, object],
        usage: dict[str, int | float],
        response_sha256: str,
        response_character_count: int,
        now: datetime | None = None,
    ) -> None:
        self._ensure_running()
        self.output = dict(output)
        self.usage = dict(usage)
        self.response_sha256 = response_sha256
        self.response_character_count = response_character_count
        self.status = "completed"
        self.completed_at = now or datetime.now(UTC)

    def fail(
        self,
        *,
        status: AgentSessionFailureStatus,
        error_code: str,
        error_message: str,
        response_sha256: str | None = None,
        response_character_count: int | None = None,
        now: datetime | None = None,
    ) -> None:
        self._ensure_running()
        self.status = status
        self.error_code = error_code
        self.error_message = error_message
        self.response_sha256 = response_sha256
        self.response_character_count = response_character_count
        self.completed_at = now or datetime.now(UTC)

