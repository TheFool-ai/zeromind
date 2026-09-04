from fastapi import Request
from fastapi.testclient import TestClient

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.bootstrap.app import create_app
from zeromind.identity.context import request_identity
from zeromind.identity.tokens import TokenService
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.shared.config import Settings
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService


def make_client() -> TestClient:
    settings = Settings(
        admin_username="operator",
        admin_password="correct-horse",
        token_secret="test-secret-that-is-long-enough",
    )
    return TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=InMemoryReferenceRepository(),
            agent_registry=AgentRegistry(InMemoryAgentRepository()),
            token_service=TokenService(settings),
        )
    )


def test_admin_can_exchange_credentials_for_bearer_token() -> None:
    client = make_client()

    response = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "correct-horse"},
    )
    token = response.json()["access_token"]
    identity = client.get(
        "/api/v1/auth/me",
        headers={"authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert identity.json() == {"username": "operator", "role": "admin"}


def test_invalid_or_tampered_credentials_are_rejected() -> None:
    client = make_client()

    wrong = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "wrong"},
    )
    tampered = client.get(
        "/api/v1/auth/me",
        headers={"authorization": "Bearer not-a-token"},
    )

    assert wrong.status_code == 401
    assert tampered.status_code == 401


def test_production_api_requires_admin_bearer_token() -> None:
    settings = Settings(
        admin_username="operator",
        admin_password="correct-horse",
        token_secret="test-secret-that-is-long-enough",
    )
    app = create_app(
        subscription_service=SubscriptionService(InMemorySubscriptionRepository()),
        reference_repository=InMemoryReferenceRepository(),
        agent_registry=AgentRegistry(InMemoryAgentRepository()),
        token_service=TokenService(settings),
        require_auth=True,
    )
    client = TestClient(app)

    anonymous = client.get("/api/v1/subscriptions")
    token = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "correct-horse"},
    ).json()["access_token"]
    authenticated = client.get(
        "/api/v1/subscriptions",
        headers={"authorization": f"Bearer {token}"},
    )

    assert anonymous.status_code == 401
    assert authenticated.status_code == 200


def test_verified_middleware_identity_is_available_to_request_handlers() -> None:
    settings = Settings(
        admin_username="operator",
        admin_password="correct-horse",
        token_secret="test-secret-that-is-long-enough",
    )
    app = create_app(
        subscription_service=SubscriptionService(InMemorySubscriptionRepository()),
        reference_repository=InMemoryReferenceRepository(),
        agent_registry=AgentRegistry(InMemoryAgentRepository()),
        token_service=TokenService(settings),
        require_auth=True,
    )

    @app.get("/api/v1/identity-probe")
    def identity_probe(request: Request) -> dict[str, str]:
        identity = request_identity(request)
        return {"username": identity.username, "role": identity.role}

    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "correct-horse"},
    ).json()["access_token"]

    response = client.get(
        "/api/v1/identity-probe",
        headers={"authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"username": "operator", "role": "admin"}


def test_request_identity_rejects_request_without_verified_identity() -> None:
    app = create_app(
        subscription_service=SubscriptionService(InMemorySubscriptionRepository()),
        reference_repository=InMemoryReferenceRepository(),
        agent_registry=AgentRegistry(InMemoryAgentRepository()),
    )

    @app.get("/identity-probe")
    def identity_probe(request: Request) -> dict[str, str]:
        identity = request_identity(request)
        return {"username": identity.username, "role": identity.role}

    response = TestClient(app).get("/identity-probe")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
