import asyncio
from uuid import UUID

from fastapi.testclient import TestClient

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.agents.session_domain import AgentExecutionContext, AgentSession
from zeromind.agents.session_repository import InMemoryAgentSessionRepository
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


def test_update_and_disable_agent_changes_version_and_discovery() -> None:
    client = make_client()
    profile_id = client.post(
        "/api/v1/providers",
        json={
            "name": "default",
            "provider": "openai",
            "model": "gpt-5-mini",
            "api_key_env": "OPENAI_API_KEY",
        },
    ).json()["id"]
    agent_id = client.post(
        "/api/v1/agents",
        json={
            "name": "summarizer",
            "description": "Summarizes",
            "capabilities": ["summarize"],
            "system_prompt": "Return JSON.",
            "provider_profile_id": profile_id,
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        },
    ).json()["id"]

    updated = client.patch(
        f"/api/v1/agents/{agent_id}",
        json={
            "system_prompt": "Return concise JSON.",
            "capabilities": ["summarize", "zh"],
        },
    )
    disabled = client.post(f"/api/v1/agents/{agent_id}/disable")
    discovered = client.get(
        "/api/v1/agents/discover",
        params={"capability": "summarize"},
    )
    versions = client.get(f"/api/v1/agents/{agent_id}/versions")

    assert updated.json()["version"] == 2
    assert updated.json()["capabilities"] == ["summarize", "zh"]
    assert disabled.json()["enabled"] is False
    assert discovered.json()["items"] == []
    assert [item["version"] for item in versions.json()["items"]] == [1, 2]
    assert versions.json()["items"][0]["system_prompt"] == "Return JSON."


def test_list_and_get_sanitized_agent_sessions() -> None:
    sessions = InMemoryAgentSessionRepository()
    value = AgentSession.start(
        context=AgentExecutionContext(
            workflow_run_id=UUID("11111111-1111-1111-1111-111111111111"),
            step_run_id=UUID("22222222-2222-2222-2222-222222222222"),
            attempt=1,
        ),
        agent_id=UUID("33333333-3333-3333-3333-333333333333"),
        agent_version_id=UUID("44444444-4444-4444-4444-444444444444"),
        provider="openai",
        model="gpt-5-mini",
        thinking_level="medium",
        sanitized_input={"document": {"sha256": "safe", "character_count": 42}},
        document_sha256="safe",
        document_character_count=42,
    )
    value.complete(
        output={"summary": "Safe result"},
        usage={"input": 10, "output": 5},
        response_sha256="response",
        response_character_count=25,
    )
    asyncio.run(sessions.add(value))
    client = TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=InMemoryReferenceRepository(),
            agent_registry=AgentRegistry(InMemoryAgentRepository()),
            agent_session_repository=sessions,
        )
    )

    listed = client.get(
        "/api/v1/agent-sessions",
        params={"workflow_run_id": str(value.workflow_run_id), "status": "completed"},
    )
    fetched = client.get(f"/api/v1/agent-sessions/{value.id}")

    assert [item["id"] for item in listed.json()["items"]] == [str(value.id)]
    assert fetched.json()["sanitized_input"] == value.sanitized_input
    assert "ARTICLE BODY" not in fetched.text
