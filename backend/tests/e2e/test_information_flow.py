import hashlib
import hmac
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.gateway import AgentGateway
from zeromind.agents.pi_rpc import PiRpcResult
from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.content.network_policy import NetworkPolicy
from zeromind.content.resolver import ContentResolver
from zeromind.delivery.domain import WebhookEndpoint
from zeromind.delivery.service import WebhookDeliveryService
from zeromind.ingestion.feed_client import FeedClient, FeedDocument
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.subscriptions.opml import preview_opml
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import parse_workflow_yaml
from zeromind.workflows.executor import WorkflowExecutor
from zeromind.workflows.repository import InMemoryWorkflowRepository


class FakePiClient:
    async def execute(self, request: object, *, timeout_seconds: float) -> PiRpcResult:
        del request, timeout_seconds
        return PiRpcResult(
            output={"summary": "A durable structured summary", "score": 0.93},
            deltas=(),
            usage={"input": 100, "output": 12},
        )


async def public_address(_: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.mark.asyncio
async def test_reference_first_information_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (Path(__file__).parents[3] / "compose.yaml").exists()
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    subscriptions = InMemorySubscriptionRepository()
    subscription_service = SubscriptionService(subscriptions)
    opml = preview_opml(
        b"""<?xml version="1.0"?>
<opml version="2.0"><body>
  <outline text="Example" type="rss" xmlUrl="https://example.com/feed.xml"/>
</body></opml>"""
    )
    imported = await subscription_service.import_entries(opml.entries)
    subscription = (await subscriptions.list())[0]
    assert imported.created == 1

    rss = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example</title>
<item><guid>article-1</guid><title>Useful article</title>
<link>https://example.com/article-1</link>
<description>Short RSS metadata only.</description></item>
</channel></rss>"""

    async def source_server(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed.xml":
            return httpx.Response(
                200,
                content=rss,
                headers={"content-type": "application/rss+xml", "etag": '"v1"'},
            )
        return httpx.Response(
            200,
            content=b"""<html lang="en"><head><title>Useful article</title></head>
<body><article><p>This full article body exists only during the workflow run.</p>
<p>It has enough meaningful prose for the extractor to identify the content.</p>
</article></body></html>""",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    fetched = await FeedClient(
        transport=httpx.MockTransport(source_server)
    ).fetch(subscription.feed_url)
    assert isinstance(fetched, FeedDocument)
    references = InMemoryReferenceRepository()
    ingestion = IngestionService(references)
    first = await ingestion.ingest(
        subscription_id=subscription.id,
        entries=fetched.entries,
        fetched_at=now,
    )
    second = await ingestion.ingest(
        subscription_id=subscription.id,
        entries=fetched.entries,
        fetched_at=now,
    )
    reference = (await references.list_references())[0]
    assert first.discovered == 1
    assert second.unchanged == 1
    assert len(await references.list_revisions(reference.id)) == 1

    monkeypatch.setenv("FAKE_PROVIDER_KEY", "not-persisted")
    agent_repository = InMemoryAgentRepository()
    registry = AgentRegistry(agent_repository)
    profile = ProviderProfile.create(
        name="fake",
        provider="fake",
        model="deterministic",
        api_key_env="FAKE_PROVIDER_KEY",
    )
    await registry.register_provider(profile)
    agent = AgentDefinition.create(
        name="analyzer",
        description="Fixture analyzer",
        capabilities=("summarize",),
        system_prompt="Return structured JSON.",
        provider_profile_id=profile.id,
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "required": ["summary", "score"],
            "properties": {
                "summary": {"type": "string"},
                "score": {"type": "number"},
            },
        },
    )
    await registry.register_agent(agent)
    gateway = AgentGateway(registry, FakePiClient())
    resolver = ContentResolver(
        network_policy=NetworkPolicy(resolver=public_address),
        transport=httpx.MockTransport(source_server),
    )

    async def resolve_node(_: dict[str, object]) -> dict[str, object]:
        return {
            "_transient_document": True,
            **asdict(await resolver.resolve(reference)),
        }

    async def agent_node(value: dict[str, object]) -> dict[str, object]:
        identifier = value.pop("_agent_id")
        result = await gateway.execute(agent.id, {"document": value["document"]})
        assert str(identifier) == str(agent.id)
        return result.output

    workflow_repository = InMemoryWorkflowRepository()
    definition = WorkflowDefinition.create(
        parse_workflow_yaml(
            f"""
name: fixture-analysis
trigger: {{events: [reference.discovered]}}
nodes:
  - id: resolve
    type: resolve
  - id: analyze
    type: agent
    agent_id: {agent.id}
    depends_on: [resolve]
    input: {{document: $.steps.resolve}}
output: {{analysis: $.steps.analyze}}
"""
        )
    )
    definition.activate()
    await workflow_repository.add_definition(definition)
    run = await WorkflowExecutor(
        workflow_repository,
        handlers={"resolve": resolve_node, "agent": agent_node},
    ).execute(
        definition.id,
        trigger={"event": "reference.discovered", "reference_id": str(reference.id)},
        idempotency_key=first.events[0].idempotency_key,
    )
    persisted = await workflow_repository.get_run(run.id)
    assert run.output == {
        "analysis": {"summary": "A durable structured summary", "score": 0.93}
    }
    assert "full article body" not in str(persisted)

    monkeypatch.setenv("FIXTURE_WEBHOOK_SECRET", "webhook-secret")
    requests: list[httpx.Request] = []

    async def webhook_server(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    endpoint = WebhookEndpoint.create(
        name="fixture",
        url="https://hooks.example/result",
        secret_env="FIXTURE_WEBHOOK_SECRET",
        events=("workflow.completed",),
    )
    delivery = await WebhookDeliveryService(
        network_policy=NetworkPolicy(resolver=public_address),
        transport=httpx.MockTransport(webhook_server),
    ).deliver(
        endpoint,
        event_id=str(run.id),
        event_type="workflow.completed",
        payload={"run_id": str(run.id), "result": run.output or {}},
    )
    expected_signature = hmac.new(
        b"webhook-secret",
        requests[0].content,
        hashlib.sha256,
    ).hexdigest()
    assert delivery.status == "delivered"
    assert json.loads(requests[0].content)["data"]["result"] == run.output
    assert requests[0].headers["x-zeromind-signature"] == (
        f"sha256={expected_signature}"
    )
