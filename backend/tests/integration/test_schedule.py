from datetime import UTC, datetime, timedelta

import pytest

from zeromind.bootstrap.tasks import DueFeedScheduler, matching_workflows, overlap_window_start
from zeromind.subscriptions.domain import Subscription
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import parse_workflow_yaml
from zeromind.workflows.repository import InMemoryWorkflowRepository


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
