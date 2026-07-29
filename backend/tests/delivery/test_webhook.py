import hashlib
import hmac
import json
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.bootstrap.app import create_app
from zeromind.content.network_policy import NetworkPolicy
from zeromind.delivery.domain import WebhookEndpoint
from zeromind.delivery.repository import InMemoryWebhookRepository
from zeromind.delivery.service import WebhookDeliveryService
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService


@pytest.mark.asyncio
async def test_webhook_is_canonical_json_signed_and_event_filtered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZEROMIND_TEST_WEBHOOK_SECRET", "delivery-secret")
    requests: list[httpx.Request] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    endpoint = WebhookEndpoint.create(
        name="sink",
        url="https://hooks.example/events",
        secret_env="ZEROMIND_TEST_WEBHOOK_SECRET",
        events=("workflow.completed",),
        identifier=UUID("77777777-7777-7777-7777-777777777777"),
    )
    service = WebhookDeliveryService(
        network_policy=NetworkPolicy(
            resolver=lambda _: _public_address()
        ),
        transport=httpx.MockTransport(responder),
    )

    skipped = await service.deliver(
        endpoint,
        event_id="event-0",
        event_type="workflow.failed",
        payload={"run_id": "run-0"},
    )
    delivered = await service.deliver(
        endpoint,
        event_id="event-1",
        event_type="workflow.completed",
        payload={"run_id": "run-1", "result": {"score": 1}},
    )

    body = json.dumps(
        {
            "id": "event-1",
            "type": "workflow.completed",
            "data": {"run_id": "run-1", "result": {"score": 1}},
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    expected = hmac.new(b"delivery-secret", body, hashlib.sha256).hexdigest()
    assert skipped.status == "skipped"
    assert delivered.status == "delivered"
    assert len(requests) == 1
    assert requests[0].headers["x-zeromind-signature"] == f"sha256={expected}"
    assert requests[0].content == body


async def _public_address() -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.mark.asyncio
async def test_webhook_retries_then_records_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZEROMIND_TEST_WEBHOOK_SECRET", "delivery-secret")
    attempts = 0

    async def responder(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    endpoint = WebhookEndpoint.create(
        name="sink",
        url="https://hooks.example/events",
        secret_env="ZEROMIND_TEST_WEBHOOK_SECRET",
        events=("workflow.completed",),
        max_attempts=3,
    )
    service = WebhookDeliveryService(
        network_policy=NetworkPolicy(resolver=lambda _: _public_address()),
        transport=httpx.MockTransport(responder),
        sleep=lambda _: _no_sleep(),
    )

    result = await service.deliver(
        endpoint,
        event_id="event-1",
        event_type="workflow.completed",
        payload={},
    )

    assert attempts == 3
    assert result.status == "exhausted"
    assert result.attempts == 3


async def _no_sleep() -> None:
    return None


def test_webhook_crud_exposes_secret_reference_not_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZEROMIND_TEST_WEBHOOK_SECRET", "never-return-this")
    repository = InMemoryWebhookRepository()
    app = create_app(
        subscription_service=SubscriptionService(InMemorySubscriptionRepository()),
        reference_repository=InMemoryReferenceRepository(),
        agent_registry=AgentRegistry(InMemoryAgentRepository()),
        webhook_repository=repository,
        webhook_network_policy=NetworkPolicy(
            resolver=lambda _: _public_address()
        ),
    )
    client = TestClient(app)

    created = client.post(
        "/api/v1/webhooks",
        json={
            "name": "analytics",
            "url": "https://hooks.example/events",
            "secret_env": "ZEROMIND_TEST_WEBHOOK_SECRET",
            "events": ["workflow.completed"],
            "max_attempts": 3,
        },
    )
    listed = client.get("/api/v1/webhooks")

    assert created.status_code == 201
    assert listed.json()["items"][0]["secret_env"] == "ZEROMIND_TEST_WEBHOOK_SECRET"
    assert "never-return-this" not in listed.text


def test_webhook_crud_rejects_private_destination() -> None:
    repository = InMemoryWebhookRepository()
    app = create_app(
        subscription_service=SubscriptionService(InMemorySubscriptionRepository()),
        reference_repository=InMemoryReferenceRepository(),
        agent_registry=AgentRegistry(InMemoryAgentRepository()),
        webhook_repository=repository,
        webhook_network_policy=NetworkPolicy(
            resolver=lambda _: _private_address()
        ),
    )
    response = TestClient(app).post(
        "/api/v1/webhooks",
        json={
            "name": "internal",
            "url": "http://internal.example/hook",
            "secret_env": "SECRET",
            "events": ["workflow.completed"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "blocked_webhook_target"


async def _private_address() -> tuple[str, ...]:
    return ("127.0.0.1",)
