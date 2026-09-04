from fastapi.testclient import TestClient

from zeromind.bootstrap.app import create_app
from zeromind.rsshub.credentials import CredentialCipher
from zeromind.rsshub.repository import InMemoryRSSHubInstanceRepository
from zeromind.rsshub.service import RSSHubInstanceService
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService


def make_client() -> TestClient:
    rsshub_service = RSSHubInstanceService(
        InMemoryRSSHubInstanceRepository(),
        CredentialCipher("test-credential-secret"),
    )
    return TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            rsshub_service=rsshub_service,
        )
    )


def test_instance_lifecycle_never_returns_access_key() -> None:
    client = make_client()
    created = client.post(
        "/api/v1/rsshub/instances",
        json={
            "name": "Primary",
            "base_url": "HTTPS://RSSHUB.EXAMPLE.COM:443/",
            "access_key": "never-return-this",
            "authentication_mode": "key",
        },
    )

    listed = client.get("/api/v1/rsshub/instances")

    assert created.status_code == 201
    assert created.json()["base_url"] == "https://rsshub.example.com"
    assert created.json()["active"] is True
    assert created.json()["has_access_key"] is True
    assert "access_key" not in created.json()
    assert "never-return-this" not in created.text
    assert listed.json()["items"] == [created.json()]


def test_update_distinguishes_omitted_key_from_explicit_clear() -> None:
    client = make_client()
    created = client.post(
        "/api/v1/rsshub/instances",
        json={
            "name": "Primary",
            "base_url": "https://rsshub.example.com",
            "access_key": "secret",
        },
    ).json()
    identifier = created["id"]

    preserved = client.put(
        f"/api/v1/rsshub/instances/{identifier}",
        json={
            "name": "Primary",
            "base_url": "https://rsshub.example.com",
            "authentication_mode": "code",
            "enabled": True,
        },
    )
    cleared = client.put(
        f"/api/v1/rsshub/instances/{identifier}",
        json={
            "name": "Primary",
            "base_url": "https://rsshub.example.com",
            "authentication_mode": "code",
            "enabled": True,
            "access_key": None,
        },
    )

    assert preserved.json()["has_access_key"] is True
    assert preserved.json()["authentication_mode"] == "code"
    assert cleared.json()["has_access_key"] is False


def test_activate_instance_and_reject_active_delete() -> None:
    client = make_client()
    first = client.post(
        "/api/v1/rsshub/instances",
        json={"name": "Primary", "base_url": "https://rsshub.example.com"},
    ).json()
    second = client.post(
        "/api/v1/rsshub/instances",
        json={"name": "Backup", "base_url": "https://backup.example.com"},
    ).json()

    activated = client.post(f"/api/v1/rsshub/instances/{second['id']}/activate")
    rejected = client.delete(f"/api/v1/rsshub/instances/{second['id']}")
    deleted = client.delete(f"/api/v1/rsshub/instances/{first['id']}")

    assert activated.status_code == 200
    assert activated.json()["active"] is True
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "rsshub_instance_in_use"
    assert deleted.status_code == 204


def test_duplicate_and_invalid_instances_return_stable_errors() -> None:
    client = make_client()
    payload = {"name": "Primary", "base_url": "https://rsshub.example.com"}
    assert client.post("/api/v1/rsshub/instances", json=payload).status_code == 201

    duplicate = client.post("/api/v1/rsshub/instances", json=payload)
    invalid = client.post(
        "/api/v1/rsshub/instances",
        json={"name": "Invalid", "base_url": "rsshub://twitter/user/vista8"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "rsshub_instance_already_exists"
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_rsshub_instance"
