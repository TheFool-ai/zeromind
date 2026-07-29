import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from zeromind.workflows.dsl import WorkflowSpec


@dataclass(slots=True)
class WorkflowDefinition:
    id: uuid.UUID
    name: str
    spec: WorkflowSpec
    version: int
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        spec: WorkflowSpec,
        *,
        now: datetime | None = None,
    ) -> "WorkflowDefinition":
        current = now or datetime.now(UTC)
        return cls(
            id=uuid.uuid4(),
            name=spec.name,
            spec=spec,
            version=1,
            status="draft",
            created_at=current,
            updated_at=current,
        )

    def activate(self, *, now: datetime | None = None) -> None:
        self.status = "active"
        self.updated_at = now or datetime.now(UTC)


@dataclass(slots=True)
class StepRun:
    id: uuid.UUID
    run_id: uuid.UUID
    node_id: str
    status: str
    attempts: int
    input: dict[str, object]
    output: dict[str, object] | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None


@dataclass(slots=True)
class WorkflowRun:
    id: uuid.UUID
    definition_id: uuid.UUID
    definition_version: int
    idempotency_key: str
    trigger: dict[str, object]
    status: str
    output: dict[str, object] | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None
    steps: list[StepRun] = field(default_factory=list)

