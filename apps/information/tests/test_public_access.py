import pytest
from fastapi.testclient import TestClient

from zeromind.bootstrap.app import create_app
from zeromind.subscriptions.infrastructure.persistence.in_memory_subscription_repository import (
    InMemorySubscriptionRepository,
)
from zeromind.subscriptions.public import SubscriptionService


@pytest.mark.parametrize("headers", [{}, {"authorization": "Bearer expired-token"}])
def test_management_api_works_without_valid_credentials(headers: dict[str, str]) -> None:
    client = TestClient(create_app(
        subscription_service=SubscriptionService(InMemorySubscriptionRepository()),
    ))
    assert client.get("/api/v1/subscriptions", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/token", json={}).status_code == 404
    assert client.get("/api/v1/auth/me").status_code == 404
