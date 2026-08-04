import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from zeromind.agents.registry import AgentRegistry, SqlAlchemyAgentRepository
from zeromind.agents.session_repository import SqlAlchemyAgentSessionRepository
from zeromind.analysis.projector import AnalysisProjector
from zeromind.analysis.repository import SqlAlchemyAnalysisRepository
from zeromind.bootstrap.celery import celery_app
from zeromind.bootstrap.runtime import build_workflow_executor
from zeromind.content.network_policy import NetworkPolicy
from zeromind.delivery.repository import SqlAlchemyWebhookRepository
from zeromind.delivery.service import WebhookDeliveryService
from zeromind.ingestion.analysis_queue import (
    SqlAlchemyReferenceAnalysisQueue,
    recover_reference_analyses,
)
from zeromind.ingestion.feed_client import FeedClient, FeedDocument, FeedNotModified
from zeromind.ingestion.lifecycle import (
    SqlAlchemyReferenceAnalysisLifecycleRepository,
)
from zeromind.ingestion.repository import SqlAlchemyReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.ingestion.workflow_observer import ReferenceAnalysisLifecycleObserver
from zeromind.rsshub.credentials import CredentialCipher
from zeromind.rsshub.repository import SqlAlchemyRSSHubInstanceRepository
from zeromind.rsshub.resolver import RSSHubResolver
from zeromind.shared.config import get_settings
from zeromind.shared.database import create_database
from zeromind.shared.outbox import (
    EventHandler,
    OutboxDispatcher,
    OutboxRepository,
    SqlAlchemyOutboxRepository,
)
from zeromind.subscriptions.domain import Subscription
from zeromind.subscriptions.repository import (
    SqlAlchemySubscriptionRepository,
    SubscriptionRepository,
)
from zeromind.workflows.constants import MAIN_ANALYSIS_WORKFLOW_NAME
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.repository import (
    SqlAlchemyWorkflowRepository,
    WorkflowRepository,
)
from zeromind.workflows.service import WorkflowRunService

POLL_INTERVAL = timedelta(minutes=30)
OVERLAP = timedelta(minutes=10)


def overlap_window_start(last_checked_at: datetime) -> datetime:
    return last_checked_at - OVERLAP


class DueFeedScheduler:
    def __init__(self, repository: SubscriptionRepository) -> None:
        self._repository = repository

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int = 1000,
    ) -> tuple[Subscription, ...]:
        return tuple(
            await self._repository.claim_due(
                now=now,
                limit=limit,
                lease=POLL_INTERVAL,
            )
        )


async def matching_workflows(
    repository: WorkflowRepository,
    event_type: str,
) -> tuple[WorkflowDefinition, ...]:
    return tuple(
        definition
        for definition in await repository.list_definitions()
        if definition.status == "active"
        and event_type in definition.spec.trigger.events
    )


async def dispatch_workflow_event(
    workflows: WorkflowRepository,
    run_service: WorkflowRunService,
    outbox: OutboxRepository,
    *,
    event_type: str,
    payload: dict[str, object],
) -> int:
    reference_id = str(payload["reference_id"])
    revision = int(str(payload["revision"]))
    definitions: tuple[WorkflowDefinition, ...]
    if event_type == "reference.analysis.requested":
        candidates = tuple(
            item
            for item in await matching_workflows(workflows, event_type)
            if item.name == MAIN_ANALYSIS_WORKFLOW_NAME
        )
        if len(candidates) != 1:
            raise ValueError(
                "expected one active information analysis workflow, "
                f"found {len(candidates)}"
            )
        definitions = candidates
    else:
        definitions = await matching_workflows(workflows, event_type)
    completed = 0
    for definition in definitions:
        raw_request_id = payload.get("request_id")
        request_id = (
            uuid.UUID(str(raw_request_id))
            if raw_request_id is not None
            else uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{event_type}:{reference_id}:{revision}",
            )
        )
        key = (
            f"analysis:{reference_id}:{revision}:{request_id}:"
            f"{definition.version}"
            if definition.name == MAIN_ANALYSIS_WORKFLOW_NAME
            else (
                f"{event_type}:{reference_id}:{revision}:"
                f"{definition.id}:{definition.version}"
            )
        )
        run = await run_service.execute(
            definition.id,
            trigger={"event": event_type, **payload, "request_id": str(request_id)},
            idempotency_key=key,
        )
        await outbox.enqueue(
            event_type="workflow.completed",
            aggregate_type="workflow_run",
            aggregate_id=str(run.id),
            payload={
                "run_id": str(run.id),
                "workflow_id": str(definition.id),
                "result": run.output or {},
            },
            idempotency_key=f"workflow.completed:{run.id}",
        )
        completed += 1
    return completed


async def fetch_subscription_document(
    subscription: Subscription,
    *,
    resolver: RSSHubResolver,
    feed_client: FeedClient,
) -> FeedDocument | FeedNotModified:
    resolved_url = await resolver.resolve(subscription.feed_url)
    return await feed_client.fetch(
        resolved_url,
        etag=subscription.etag,
        last_modified=subscription.last_modified,
    )


async def _schedule_due_feeds() -> int:
    database = create_database()
    try:
        repository = SqlAlchemySubscriptionRepository(database.sessions)
        due = await DueFeedScheduler(repository).claim_due(
            now=datetime.now(UTC),
            limit=1000,
        )
        for subscription in due:
            celery_app.send_task("zeromind.poll_feed", args=[str(subscription.id)])
        return len(due)
    finally:
        await database.dispose()


@celery_app.task(name="zeromind.schedule_due_feeds")  # type: ignore[untyped-decorator]
def schedule_due_feeds() -> int:
    return asyncio.run(_schedule_due_feeds())


async def _poll_feed(subscription_id: str) -> dict[str, int]:
    database = create_database()
    settings = get_settings()
    subscriptions = SqlAlchemySubscriptionRepository(database.sessions)
    references = SqlAlchemyReferenceRepository(database.sessions)
    outbox = SqlAlchemyOutboxRepository(database.sessions)
    identifier = uuid.UUID(subscription_id)
    subscription = await subscriptions.get(identifier)
    if subscription is None:
        await database.dispose()
        raise KeyError(identifier)
    checked_at = datetime.now(UTC)
    try:
        document = await fetch_subscription_document(
            subscription,
            resolver=RSSHubResolver(
                SqlAlchemyRSSHubInstanceRepository(database.sessions),
                CredentialCipher(settings.credential_secret),
            ),
            feed_client=FeedClient(
                network_policy=NetworkPolicy(
                    private_host_allowlist=settings.rsshub_private_hostnames,
                )
            ),
        )
        if isinstance(document, FeedDocument):
            result = await IngestionService(references).ingest(
                subscription_id=subscription.id,
                entries=document.entries,
                fetched_at=checked_at,
                window_start=(
                    overlap_window_start(subscription.last_checked_at)
                    if subscription.last_checked_at
                    else None
                ),
            )
            for event in result.events:
                await outbox.enqueue(
                    event_type=event.event_type,
                    aggregate_type="reference",
                    aggregate_id=str(event.reference_id),
                    payload={
                        "reference_id": str(event.reference_id),
                        "revision": event.revision,
                    },
                    idempotency_key=event.idempotency_key,
                    now=checked_at,
                )
            subscription.mark_success(
                now=checked_at,
                etag=document.etag,
                last_modified=document.last_modified,
            )
            counts = {
                "discovered": result.discovered,
                "updated": result.updated,
                "unchanged": result.unchanged,
            }
        else:
            subscription.mark_success(
                now=checked_at,
                etag=subscription.etag,
                last_modified=subscription.last_modified,
            )
            counts = {"discovered": 0, "updated": 0, "unchanged": 0}
        await subscriptions.save(subscription)
        return counts
    except Exception:
        subscription.mark_failure(now=checked_at)
        await subscriptions.save(subscription)
        raise
    finally:
        await database.dispose()


@celery_app.task(name="zeromind.poll_feed")  # type: ignore[untyped-decorator]
def poll_feed(subscription_id: str) -> dict[str, int]:
    return asyncio.run(_poll_feed(subscription_id))


async def _dispatch_outbox() -> int:
    database = create_database()
    settings = get_settings()
    outbox = SqlAlchemyOutboxRepository(database.sessions)
    workflows = SqlAlchemyWorkflowRepository(database.sessions)
    references = SqlAlchemyReferenceRepository(database.sessions)
    agents = AgentRegistry(SqlAlchemyAgentRepository(database.sessions))
    agent_sessions = SqlAlchemyAgentSessionRepository(database.sessions)
    subscriptions = SqlAlchemySubscriptionRepository(database.sessions)
    analyses = SqlAlchemyAnalysisRepository(database.sessions)
    webhooks = SqlAlchemyWebhookRepository(database.sessions)
    workflow_observer = ReferenceAnalysisLifecycleObserver(
        SqlAlchemyReferenceAnalysisLifecycleRepository(database.sessions)
    )
    executor = build_workflow_executor(
        workflow_repository=workflows,
        reference_repository=references,
        agent_registry=agents,
        agent_session_repository=agent_sessions,
        observer=workflow_observer,
        settings=settings,
    )
    run_service = WorkflowRunService(
        workflows,
        executor,
        projectors={
            "content_analysis_v1": AnalysisProjector(
                analyses,
                references,
                subscriptions,
            )
        },
        observer=workflow_observer,
    )

    def workflow_handler(event_type: str) -> EventHandler:
        async def handle(payload: dict[str, object]) -> None:
            await dispatch_workflow_event(
                workflows,
                run_service,
                outbox,
                event_type=event_type,
                payload=payload,
            )

        return handle

    async def deliver_webhooks(payload: dict[str, object]) -> None:
        delivery = WebhookDeliveryService(network_policy=NetworkPolicy())
        event_id = str(payload["run_id"])
        for endpoint in await webhooks.list():
            await delivery.deliver(
                endpoint,
                event_id=event_id,
                event_type="workflow.completed",
                payload=payload,
            )

    try:
        return await OutboxDispatcher(
            outbox,
            handlers={
                "reference.discovered": workflow_handler("reference.discovered"),
                "reference.updated": workflow_handler("reference.updated"),
                "reference.analysis.requested": workflow_handler(
                    "reference.analysis.requested"
                ),
                "workflow.completed": deliver_webhooks,
            },
        ).dispatch()
    finally:
        await database.dispose()


@celery_app.task(name="zeromind.dispatch_outbox")  # type: ignore[untyped-decorator]
def dispatch_outbox() -> int:
    return asyncio.run(_dispatch_outbox())


async def _recover_stale_agent_sessions() -> int:
    database = create_database()
    now = datetime.now(UTC)
    try:
        return await SqlAlchemyAgentSessionRepository(database.sessions).fail_stale(
            before=now - timedelta(minutes=15),
            now=now,
        )
    finally:
        await database.dispose()


@celery_app.task(name="zeromind.recover_stale_agent_sessions")  # type: ignore[untyped-decorator]
def recover_stale_agent_sessions() -> int:
    return asyncio.run(_recover_stale_agent_sessions())


async def _recover_stale_reference_analyses() -> dict[str, int]:
    database = create_database()
    now = datetime.now(UTC)
    try:
        references = SqlAlchemyReferenceRepository(database.sessions)
        result = await recover_reference_analyses(
            references,
            SqlAlchemyReferenceAnalysisLifecycleRepository(database.sessions),
            SqlAlchemyWorkflowRepository(database.sessions),
            SqlAlchemyAnalysisRepository(database.sessions),
            SqlAlchemyReferenceAnalysisQueue(database.sessions),
            before=now - timedelta(minutes=30),
            now=now,
        )
        return {
            "repaired": result.repaired,
            "requeued": result.requeued,
            "skipped": result.skipped,
        }
    finally:
        await database.dispose()


@celery_app.task(name="zeromind.recover_stale_reference_analyses")  # type: ignore[untyped-decorator]
def recover_stale_reference_analyses() -> dict[str, int]:
    return asyncio.run(_recover_stale_reference_analyses())
