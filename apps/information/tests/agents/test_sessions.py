from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from zeromind.agents.session_domain import AgentExecutionContext, AgentSession
from zeromind.agents.session_repository import InMemoryAgentSessionRepository

RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
AGENT_ID = UUID("33333333-3333-3333-3333-333333333333")
VERSION_ID = UUID("44444444-4444-4444-4444-444444444444")
NOW = datetime(2026, 8, 4, tzinfo=UTC)


def session(*, started_at: datetime = NOW, attempt: int = 1) -> AgentSession:
    return AgentSession.start(
        context=AgentExecutionContext(RUN_ID, STEP_ID, attempt),
        agent_id=AGENT_ID,
        agent_version_id=VERSION_ID,
        provider="glm",
        model="GLM-5.2",
        thinking_level="off",
        sanitized_input={"metadata": {"title": "Safe"}},
        document_sha256=None,
        document_character_count=None,
        now=started_at,
    )


def test_session_allows_one_running_to_completed_transition() -> None:
    value = session()

    value.complete(
        output={"summary": "Done"},
        usage={"total": 10},
        response_sha256="a" * 64,
        response_character_count=18,
        now=NOW + timedelta(seconds=2),
    )

    assert value.status == "completed"
    assert value.output == {"summary": "Done"}
    with pytest.raises(ValueError, match="already terminal"):
        value.fail(
            status="protocol_failed",
            error_code="late",
            error_message="too late",
            now=NOW + timedelta(seconds=3),
        )


@pytest.mark.asyncio
async def test_repository_filters_sessions_and_recovers_only_stale_running() -> None:
    repository = InMemoryAgentSessionRepository()
    stale = session(started_at=NOW - timedelta(minutes=20))
    recent = session(started_at=NOW - timedelta(minutes=5), attempt=2)
    completed = session(started_at=NOW - timedelta(minutes=30), attempt=3)
    completed.complete(
        output={"summary": "Done"},
        usage={},
        response_sha256="b" * 64,
        response_character_count=18,
        now=NOW - timedelta(minutes=29),
    )
    for value in (stale, recent, completed):
        await repository.add(value)

    changed = await repository.fail_stale(
        before=NOW - timedelta(minutes=15),
        now=NOW,
    )

    assert changed == 1
    assert (await repository.get(stale.id)).status == "protocol_failed"  # type: ignore[union-attr]
    assert (await repository.get(recent.id)).status == "running"  # type: ignore[union-attr]
    assert (await repository.get(completed.id)).status == "completed"  # type: ignore[union-attr]
    assert await repository.list(workflow_run_id=RUN_ID, status="running") == (recent,)
