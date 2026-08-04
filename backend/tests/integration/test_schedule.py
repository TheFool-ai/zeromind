from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest

from zeromind.bootstrap.celery import celery_app
from zeromind.bootstrap.tasks import (
    DueFeedScheduler,
    dispatch_workflow_event,
    fetch_subscription_document,
    matching_workflows,
    overlap_window_start,
)
from zeromind.ingestion.feed_client import FeedClient, FeedDocument
from zeromind.rsshub.credentials import CredentialCipher
from zeromind.rsshub.repository import InMemoryRSSHubInstanceRepository
from zeromind.rsshub.resolver import RSSHubResolver
from zeromind.rsshub.service import RSSHubInstanceService
from zeromind.shared.outbox import InMemoryOutboxRepository
from zeromind.subscriptions.domain import Subscription
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.workflows.constants import MAIN_ANALYSIS_WORKFLOW_NAME
from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import parse_workflow_yaml
from zeromind.workflows.repository import InMemoryWorkflowRepository


def test_reference_analysis_recovery_runs_on_events_queue_every_five_minutes() -> None:
    assert celery_app.conf.task_routes[
        "zeromind.recover_stale_reference_analyses"
    ] == {"queue": "events"}
    entry = celery_app.conf.beat_schedule[
        "recover-stale-reference-analyses-every-five-minutes"
    ]
    assert entry["task"] == "zeromind.recover_stale_reference_analyses"
    assert entry["schedule"] == 300.0


@pytest.mark.asyncio
async def test_scheduler_claims_only_enabled_due_feeds_once() -> None:
    repository = InMemorySubscriptionRepository()
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    due = Subscription.create(feed_url="https://due.example/rss", title="Due", now=now)
    future = Subscription.create(
        feed_url="https://future.example/rss",
        title="Future",
        now=now + timedelta(hours=1),
    )
    disabled = Subscription.create(
        feed_url="https://disabled.example/rss",
        title="Disabled",
        now=now,
    )
    disabled.disable(now=now)
    for item in (due, future, disabled):
        await repository.add(item)

    scheduler = DueFeedScheduler(repository)
    first = await scheduler.claim_due(now=now, limit=10)
    second = await scheduler.claim_due(now=now, limit=10)

    assert [item.id for item in first] == [due.id]
    assert second == ()
    assert due.next_poll_at == now + timedelta(minutes=30)


def test_poll_window_has_ten_minute_overlap() -> None:
    checked = datetime(2026, 7, 29, 12, tzinfo=UTC)

    assert overlap_window_start(checked) == checked - timedelta(minutes=10)


@pytest.mark.asyncio
async def test_poll_fetches_rsshub_subscription_through_active_instance() -> None:
    requested_url: str | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_url
        requested_url = str(request.url)
        return httpx.Response(
            200,
            content=b"<rss version='2.0'><channel><title>Feed</title></channel></rss>",
            headers={"content-type": "application/rss+xml"},
        )

    repository = InMemoryRSSHubInstanceRepository()
    cipher = CredentialCipher("test-credential-secret")
    await RSSHubInstanceService(repository, cipher).create(
        name="Primary",
        base_url="https://rsshub.example.com",
        access_key="instance-secret",
    )
    subscription = Subscription.create(
        feed_url="rsshub://twitter/user/vista8?mode=full",
        title="Vista8",
    )

    document = await fetch_subscription_document(
        subscription,
        resolver=RSSHubResolver(repository, cipher),
        feed_client=FeedClient(transport=httpx.MockTransport(handler)),
    )

    assert isinstance(document, FeedDocument)
    assert requested_url == (
        "https://rsshub.example.com/twitter/user/vista8"
        "?mode=full&key=instance-secret"
    )


@pytest.mark.asyncio
async def test_reference_updates_only_match_opted_in_workflows() -> None:
    repository = InMemoryWorkflowRepository()
    discovered = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: discoveries
trigger: {events: [reference.discovered]}
nodes: [{id: noop, type: parallel}]
"""
        )
    )
    updates = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: updates
trigger: {events: [reference.updated]}
nodes: [{id: noop, type: parallel}]
"""
        )
    )
    discovered.activate()
    updates.activate()
    await repository.add_definition(discovered)
    await repository.add_definition(updates)

    matched = await matching_workflows(repository, "reference.updated")

    assert [item.name for item in matched] == ["updates"]


class SuccessfulRunService:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def execute(
        self,
        definition_id: UUID,
        *,
        trigger: dict[str, object],
        idempotency_key: str,
    ) -> WorkflowRun:
        self.keys.append(idempotency_key)
        now = datetime(2026, 7, 31, 3, tzinfo=UTC)
        return WorkflowRun(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            definition_id=definition_id,
            definition_version=1,
            idempotency_key=idempotency_key,
            trigger=trigger,
            status="completed",
            output={"status": "qualified"},
            error=None,
            started_at=now,
            completed_at=now,
        )


class FailedProjectionRunService:
    async def execute(
        self,
        definition_id: UUID,
        *,
        trigger: dict[str, object],
        idempotency_key: str,
    ) -> WorkflowRun:
        raise ValueError("analysis_projection_invalid: invalid output")


@pytest.mark.asyncio
async def test_worker_enqueues_completion_only_after_run_service_succeeds() -> None:
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: projected
trigger: {events: [reference.discovered]}
nodes: [{id: noop, type: parallel}]
"""
        )
    )
    definition.activate()
    await workflows.add_definition(definition)
    outbox = InMemoryOutboxRepository()

    await dispatch_workflow_event(
        workflows,
        SuccessfulRunService(),  # type: ignore[arg-type]
        outbox,
        event_type="reference.discovered",
        payload={
            "reference_id": "11111111-1111-1111-1111-111111111111",
            "revision": 1,
        },
    )

    events = await outbox.claim(
        now=datetime.now(UTC),
        limit=10,
        lease=timedelta(minutes=1),
    )
    assert len(events) == 1
    assert events[0].event_type == "workflow.completed"
    assert events[0].payload["result"] == {"status": "qualified"}


@pytest.mark.asyncio
async def test_worker_does_not_enqueue_completion_after_projection_failure() -> None:
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            """
name: projected-failure
trigger: {events: [reference.discovered]}
nodes: [{id: noop, type: parallel}]
"""
        )
    )
    definition.activate()
    await workflows.add_definition(definition)
    outbox = InMemoryOutboxRepository()

    with pytest.raises(ValueError, match="analysis_projection_invalid"):
        await dispatch_workflow_event(
            workflows,
            FailedProjectionRunService(),  # type: ignore[arg-type]
            outbox,
            event_type="reference.discovered",
            payload={
                "reference_id": "11111111-1111-1111-1111-111111111111",
                "revision": 1,
            },
        )

    assert (
        await outbox.claim(
            now=datetime(2026, 7, 31, 4, tzinfo=UTC),
            limit=10,
            lease=timedelta(minutes=1),
        )
        == ()
    )


@pytest.mark.asyncio
async def test_distinct_analysis_requests_create_distinct_main_workflow_keys() -> None:
    workflows = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            f"""
name: {MAIN_ANALYSIS_WORKFLOW_NAME}
trigger: {{events: [reference.analysis.requested]}}
nodes: [{{id: noop, type: parallel}}]
"""
        )
    )
    definition.activate()
    await workflows.add_definition(definition)
    run_service = SuccessfulRunService()
    outbox = InMemoryOutboxRepository()
    base = {
        "reference_id": "11111111-1111-1111-1111-111111111111",
        "revision": 1,
        "reason": "manual",
    }

    for request_id in (
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    ):
        await dispatch_workflow_event(
            workflows,
            run_service,  # type: ignore[arg-type]
            outbox,
            event_type="reference.analysis.requested",
            payload={**base, "request_id": request_id},
        )

    assert len(set(run_service.keys)) == 2
    assert all(key.startswith("analysis:") for key in run_service.keys)
