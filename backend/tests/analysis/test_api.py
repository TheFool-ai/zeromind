import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.analysis.domain import ContentAnalysis, KeyQuote, ScoreDimension, Viewpoint
from zeromind.analysis.repository import InMemoryAnalysisRepository
from zeromind.bootstrap.app import create_app
from zeromind.identity.tokens import TokenService
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.shared.config import Settings
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService

ANALYSIS_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NOW = datetime(2026, 7, 31, 5, tzinfo=UTC)


def stored_analysis() -> ContentAnalysis:
    return ContentAnalysis(
        id=ANALYSIS_ID,
        reference_id=UUID("11111111-1111-1111-1111-111111111111"),
        reference_revision=1,
        subscription_id=UUID("22222222-2222-2222-2222-222222222222"),
        workflow_definition_id=UUID(
            "33333333-3333-3333-3333-333333333333"
        ),
        workflow_definition_version=1,
        workflow_run_id=UUID("44444444-4444-4444-4444-444444444444"),
        generated_status="qualified",
        source_name="Example Engineering",
        source_feed_url="https://example.com/feed",
        title="A useful article",
        original_url="https://example.com/article",
        author="Ada",
        published_at=datetime(2026, 7, 30, tzinfo=UTC),
        observed_at=NOW,
        screening_score=85,
        screening_reason="Relevant and substantial",
        screening_summary="Metadata screening summary",
        primary_category="AI",
        secondary_categories=("Engineering",),
        tags=("agents", "workflows"),
        one_sentence_summary="A practical Agent workflow guide.",
        summary="The article explains a practical workflow architecture.",
        viewpoints=(
            Viewpoint(
                statement="Deterministic gates improve explainability.",
                explanation="Thresholds remain visible and testable.",
            ),
        ),
        key_quotes=(
            KeyQuote(
                text="Keep model judgment separate from deterministic policy.",
                context="The author discusses scoring.",
            ),
        ),
        total_score=86,
        dimensions={
            "depth": ScoreDimension(
                value=90,
                weight=0.6,
                reason="Detailed evidence",
            ),
            "clarity": ScoreDimension(
                value=80,
                weight=0.4,
                reason="Clear structure",
            ),
        },
        recommendation_level="recommended",
        recommendation_reason="High information density",
        provenance={
            "screening": {
                "agent_id": "55555555-5555-5555-5555-555555555555",
                "agent_version": 1,
                "provider": "openai",
                "model": "gpt-5-mini",
                "usage": {},
            },
            "analysis": {
                "agent_id": "66666666-6666-6666-6666-666666666666",
                "agent_version": 2,
                "provider": "openai",
                "model": "gpt-5",
                "usage": {},
            },
        },
        created_at=NOW,
    )


def make_client() -> tuple[TestClient, str]:
    analyses = InMemoryAnalysisRepository()
    asyncio.run(analyses.add(stored_analysis()))
    settings = Settings(
        admin_username="admin",
        admin_password="correct-horse",
        token_secret="test-secret-that-is-long-enough",
    )
    client = TestClient(
        create_app(
            subscription_service=SubscriptionService(
                InMemorySubscriptionRepository()
            ),
            reference_repository=InMemoryReferenceRepository(),
            agent_registry=AgentRegistry(InMemoryAgentRepository()),
            analysis_repository=analyses,
            token_service=TokenService(settings),
        )
    )
    token = client.post(
        "/api/v1/auth/token",
        json={"username": "admin", "password": "correct-horse"},
    ).json()["access_token"]
    return client, token


def test_analysis_list_detail_and_override_contract() -> None:
    client, token = make_client()

    listed = client.get("/api/v1/analyses?minimum_score=80")
    detail = client.get(f"/api/v1/analyses/{ANALYSIS_ID}")
    overridden = client.post(
        f"/api/v1/analyses/{ANALYSIS_ID}/overrides",
        headers={"authorization": f"Bearer {token}"},
        json={
            "decision": "rejected",
            "reason": "Manual review found unsupported claims.",
        },
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["title"] == "A useful article"
    assert listed.json()["items"][0]["source_name"] == "Example Engineering"
    assert listed.json()["items"][0]["total_score"] == 86
    assert listed.json()["next_cursor"] is None
    assert detail.status_code == 200
    assert detail.json()["dimensions"][0]["name"] == "depth"
    assert detail.json()["viewpoints"][0]["statement"].startswith(
        "Deterministic"
    )
    assert overridden.status_code == 200
    assert overridden.json()["effective_decision"] == "rejected"
    assert overridden.json()["overrides"][-1]["actor_subject"] == "admin"
    assert "ARTICLE BODY" not in listed.text + detail.text + overridden.text


def test_analysis_list_supports_explicit_rejected_view() -> None:
    client, token = make_client()
    client.post(
        f"/api/v1/analyses/{ANALYSIS_ID}/overrides",
        headers={"authorization": f"Bearer {token}"},
        json={
            "decision": "rejected",
            "reason": "Manual review found unsupported claims.",
        },
    )

    default = client.get("/api/v1/analyses")
    rejected = client.get(
        "/api/v1/analyses?effective_decision=rejected"
    )

    assert default.json()["items"] == []
    assert [item["id"] for item in rejected.json()["items"]] == [
        str(ANALYSIS_ID)
    ]


def test_analysis_api_maps_not_found_and_invalid_cursor() -> None:
    client, _ = make_client()
    missing = client.get(
        "/api/v1/analyses/99999999-9999-9999-9999-999999999999"
    )
    cursor = client.get("/api/v1/analyses?cursor=not-base64!")

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "analysis_not_found"
    assert cursor.status_code == 422
    assert cursor.json()["detail"]["code"] == "invalid_cursor"


def test_override_requires_identity_and_valid_payload() -> None:
    client, token = make_client()

    anonymous = client.post(
        f"/api/v1/analyses/{ANALYSIS_ID}/overrides",
        json={
            "decision": "rejected",
            "reason": "Manual review found unsupported claims.",
        },
    )
    short = client.post(
        f"/api/v1/analyses/{ANALYSIS_ID}/overrides",
        headers={"authorization": f"Bearer {token}"},
        json={"decision": "rejected", "reason": "short"},
    )
    invalid_decision = client.post(
        f"/api/v1/analyses/{ANALYSIS_ID}/overrides",
        headers={"authorization": f"Bearer {token}"},
        json={
            "decision": "maybe",
            "reason": "Manual review found unsupported claims.",
        },
    )

    assert anonymous.status_code == 401
    assert short.status_code == 422
    assert invalid_decision.status_code == 422
