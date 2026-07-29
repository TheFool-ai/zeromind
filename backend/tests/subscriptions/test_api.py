from fastapi.testclient import TestClient

from zeromind.bootstrap.app import create_app
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService


def make_client() -> TestClient:
    service = SubscriptionService(InMemorySubscriptionRepository())
    return TestClient(create_app(subscription_service=service))


def test_create_and_list_subscription() -> None:
    client = make_client()

    created = client.post(
        "/api/v1/subscriptions",
        json={
            "feed_url": "HTTPS://EXAMPLE.COM:443/feed.xml#latest",
            "title": "Example",
        },
    )
    listed = client.get("/api/v1/subscriptions")

    assert created.status_code == 201
    assert created.json()["feed_url"] == "https://example.com/feed.xml"
    assert listed.status_code == 200
    assert [item["title"] for item in listed.json()["items"]] == ["Example"]


def test_create_rsshub_subscription_preserves_locator() -> None:
    client = make_client()

    response = client.post(
        "/api/v1/subscriptions",
        json={
            "feed_url": "RSSHUB://twitter/user/vista8?mode=full",
            "title": "Vista8",
        },
    )

    assert response.status_code == 201
    assert response.json()["feed_url"] == "rsshub://twitter/user/vista8?mode=full"


def test_disable_and_enable_subscription() -> None:
    client = make_client()
    created = client.post(
        "/api/v1/subscriptions",
        json={"feed_url": "https://example.com/feed", "title": "Example"},
    )
    identifier = created.json()["id"]

    disabled = client.post(f"/api/v1/subscriptions/{identifier}/disable")
    enabled = client.post(f"/api/v1/subscriptions/{identifier}/enable")

    assert disabled.json()["enabled"] is False
    assert disabled.json()["health"] == "disabled"
    assert enabled.json()["enabled"] is True


def test_create_duplicate_returns_conflict() -> None:
    client = make_client()
    payload = {"feed_url": "https://example.com/feed", "title": "Example"}
    assert client.post("/api/v1/subscriptions", json=payload).status_code == 201

    response = client.post("/api/v1/subscriptions", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "subscription_already_exists"


def test_preview_then_import_opml_reports_outcomes() -> None:
    client = make_client()
    opml = b"""<opml version="2.0"><body>
      <outline title="One" xmlUrl="https://example.com/one.xml"/>
      <outline title="Two" xmlUrl="https://example.com/two.xml"/>
    </body></opml>"""

    preview = client.post(
        "/api/v1/subscriptions/opml/preview",
        files={"file": ("feeds.opml", opml, "text/xml")},
    )
    imported = client.post(
        "/api/v1/subscriptions/opml/import",
        files={"file": ("feeds.opml", opml, "text/xml")},
    )
    repeated = client.post(
        "/api/v1/subscriptions/opml/import",
        files={"file": ("feeds.opml", opml, "text/xml")},
    )

    assert preview.status_code == 200
    assert len(preview.json()["entries"]) == 2
    assert imported.json()["created"] == 2
    assert repeated.json()["duplicates"] == 2


def test_preview_rejects_unsafe_xml() -> None:
    client = make_client()
    opml = b"""<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <opml><body><outline text="&xxe;" xmlUrl="https://example.com/feed"/></body></opml>"""

    response = client.post(
        "/api/v1/subscriptions/opml/preview",
        files={"file": ("feeds.opml", opml, "text/xml")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_opml"
