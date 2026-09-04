from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.workflows.domain import StepRun, WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import parse_workflow_yaml
from zeromind.workflows.models import (
    StepRunModel,
    WorkflowDefinitionModel,
    WorkflowRunModel,
)
from zeromind.workflows.repository import SqlAlchemyWorkflowRepository


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(WorkflowDefinitionModel.__table__.create)
        await connection.run_sync(WorkflowRunModel.__table__.create)
        await connection.run_sync(StepRunModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_repository_round_trips_definition_run_and_steps(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyWorkflowRepository(sessions)
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: stored
trigger: {events: [manual]}
nodes:
  - {id: copy, type: parallel}
output: {}
"""
        )
    )
    definition.activate()
    await repository.add_definition(definition)
    now = datetime.now(UTC)
    run = WorkflowRun(
        id=definition.id,
        definition_id=definition.id,
        definition_version=definition.version,
        idempotency_key="manual:stored",
        trigger={"event": "manual"},
        status="completed",
        output={"ok": True},
        error=None,
        started_at=now,
        completed_at=now,
        steps=[
            StepRun(
                id=definition.id,
                run_id=definition.id,
                node_id="copy",
                status="completed",
                attempts=1,
                input={},
                output={"ok": True},
                error=None,
                started_at=now,
                completed_at=now,
            )
        ],
    )
    await repository.add_run(run)
    await repository.add_step(run.steps.pop())
    await repository.save_run(run)

    restored = await repository.find_run(definition.id, "manual:stored")

    assert (await repository.get_definition(definition.id)).status == "active"  # type: ignore[union-attr]
    assert restored is not None
    assert restored.output == {"ok": True}
    assert restored.steps[0].node_id == "copy"
