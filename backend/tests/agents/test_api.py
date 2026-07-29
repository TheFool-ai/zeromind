from fastapi.testclient import TestClient

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.bootstrap.app import create_app
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService


def make_client() -> TestClient:
    return TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=InMemoryReferenceRepository(),
            agent_registry=AgentRegistry(InMemoryAgentRepository()),
        )
    )


def test_register_and_discover_agent_without_exposing_secret() -> None:
    client = make_client()
    provider = client.post(
        "/api/v1/providers",
        json={
            "name": "default",
            "provider": "openai",
            "model": "gpt-5-mini",
            "api_key_env": "OPENAI_API_KEY",
            "thinking_level": "medium",
        },
    )
    profile_id = provider.json()["id"]
    created = client.post(
        "/api/v1/agents",
        json={
            "name": "summarizer",
            "description": "Summarizes articles",
            "capabilities": ["summarize", "zh"],
            "system_prompt": "Return structured JSON.",
            "provider_profile_id": profile_id,
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        },
    )
    discovered = client.get(
        "/api/v1/agents/discover",
        params=[("capability", "summarize"), ("capability", "zh")],
    )

    assert provider.status_code == 201
    assert provider.json()["api_key_env"] == "OPENAI_API_KEY"
    assert "api_key_value" not in provider.json()
    assert created.status_code == 201
    assert [item["name"] for item in discovered.json()["items"]] == ["summarizer"]
