from fastapi.testclient import TestClient

from zeromind.bootstrap.app import create_app


def test_live_health_does_not_require_dependencies() -> None:
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_health_reports_dependency_state() -> None:
    client = TestClient(
        create_app(
            readiness_probe=lambda: {
                "database": "up",
                "redis": "up",
                "pi": "up",
            }
        )
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {
            "database": "up",
            "redis": "up",
            "pi": "up",
        },
    }


def test_ready_health_is_unavailable_when_dependency_is_down() -> None:
    client = TestClient(
        create_app(
            readiness_probe=lambda: {
                "database": "up",
                "redis": "down",
                "pi": "up",
            }
        )
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
