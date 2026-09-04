import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import httpx
import pytest
from jsonschema import Draft202012Validator

from zeromind.agents.api import CreateAgentRequest
from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.gateway import AgentGateway
from zeromind.agents.pi_rpc import PiRpcRequest, PiRpcResult
from zeromind.agents.registry import AgentRegistry, InMemoryAgentRepository
from zeromind.analysis.projector import AnalysisProjector
from zeromind.analysis.repository import AnalysisQuery, InMemoryAnalysisRepository
from zeromind.analysis.service import AnalysisService
from zeromind.content.network_policy import NetworkPolicy
from zeromind.content.resolver import ContentResolver
from zeromind.ingestion.feed_client import FeedClient, FeedDocument
from zeromind.ingestion.repository import InMemoryReferenceRepository
from zeromind.ingestion.service import IngestionService
from zeromind.notes.repository import InMemoryNoteRepository
from zeromind.notes.service import NoteService
from zeromind.subscriptions.opml import preview_opml
from zeromind.subscriptions.repository import InMemorySubscriptionRepository
from zeromind.subscriptions.service import SubscriptionService
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import parse_workflow_yaml, validate_workflow
from zeromind.workflows.executor import NodeExecutionContext, WorkflowExecutor
from zeromind.workflows.primitives import calculate_weighted_score
from zeromind.workflows.repository import InMemoryWorkflowRepository
from zeromind.workflows.service import WorkflowRunService

ARTICLE_MARKER = "ARTICLE BODY MUST NOT BE STORED"
DIMENSIONS = (
    "relevance",
    "information_value",
    "depth",
    "practicality",
    "novelty",
    "clarity",
)
SCREENING_RESULTS = {
    "Noise": {
        "score": 10,
        "reason": "Announcement without substantive content",
        "summary": "Low-value announcement",
    },
    "Average": {
        "score": 75,
        "reason": "Potentially useful",
        "summary": "Potentially useful article",
    },
    "Excellent": {
        "score": 95,
        "reason": "High-value technical content",
        "summary": "High-value article",
    },
}


class FakePiClient:
    def __init__(self) -> None:
        self.full_content_calls = 0
        self.screening_inputs: list[dict[str, object]] = []

    async def execute(
        self,
        request: PiRpcRequest,
        *,
        timeout_seconds: float,
    ) -> PiRpcResult:
        del timeout_seconds
        metadata = request.input.get("metadata")
        assert isinstance(metadata, dict)
        title = str(metadata["title"])
        if "document" not in request.input:
            self.screening_inputs.append(request.input)
            output = SCREENING_RESULTS[title]
        else:
            self.full_content_calls += 1
            assert ARTICLE_MARKER in str(request.input["document"])
            value = 60 if title == "Average" else 90
            output = {
                "primary_category": "Software Engineering",
                "secondary_categories": ["AI"],
                "tags": ["agents", "workflows"],
                "one_sentence_summary": f"{title} structured summary",
                "summary": f"A structured analysis of {title}.",
                "viewpoints": [
                    {
                        "statement": "Deterministic gates improve auditability.",
                        "explanation": "Threshold decisions remain reproducible.",
                    }
                ],
                "key_quotes": [
                    {
                        "text": "Separate model judgment from policy.",
                        "context": "Workflow design",
                    }
                ],
                "scores": {
                    name: {
                        "value": value,
                        "reason": f"{name} evidence",
                    }
                    for name in DIMENSIONS
                },
                "recommendation_level": (
                    "recommended" if value >= 70 else "not_recommended"
                ),
                "recommendation_reason": f"Deterministic total is {value}.",
            }
        return PiRpcResult(
            output=cast(dict[str, object], output),
            deltas=(),
            usage={"input": 100, "output": 20},
        )


async def public_address(_: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


def screening_output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["score", "reason", "summary"],
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "reason": {"type": "string"},
            "summary": {"type": "string"},
        },
    }


def analysis_output_schema() -> dict[str, object]:
    score = {
        "type": "object",
        "additionalProperties": False,
        "required": ["value", "reason"],
        "properties": {
            "value": {"type": "integer", "minimum": 0, "maximum": 100},
            "reason": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "primary_category",
            "secondary_categories",
            "tags",
            "one_sentence_summary",
            "summary",
            "viewpoints",
            "key_quotes",
            "scores",
            "recommendation_level",
            "recommendation_reason",
        ],
        "properties": {
            "primary_category": {"type": "string"},
            "secondary_categories": {
                "type": "array",
                "items": {"type": "string"},
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "one_sentence_summary": {"type": "string"},
            "summary": {"type": "string"},
            "viewpoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["statement", "explanation"],
                    "properties": {
                        "statement": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                },
            },
            "key_quotes": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "context"],
                    "properties": {
                        "text": {"type": "string", "maxLength": 300},
                        "context": {"type": "string", "maxLength": 200},
                    },
                },
            },
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": list(DIMENSIONS),
                "properties": {name: score for name in DIMENSIONS},
            },
            "recommendation_level": {"type": "string"},
            "recommendation_reason": {"type": "string"},
        },
    }


def workflow_source(screening_id: UUID, analysis_id: UUID) -> str:
    dimensions = "\n".join(
        f"""        {name}:
          value: $.steps.analyze.scores.{name}.value
          reason: $.steps.analyze.scores.{name}.reason
          weight: {weight}"""
        for name, weight in (
            ("relevance", "0.20"),
            ("information_value", "0.25"),
            ("depth", "0.20"),
            ("practicality", "0.15"),
            ("novelty", "0.10"),
            ("clarity", "0.10"),
        )
    )
    return f"""
name: e2e-valuable-article-analysis
trigger:
  events: [reference.discovered]
projection: content_analysis_v1
nodes:
  - id: reference
    type: reference
    input:
      reference_id: $.trigger.reference_id
      revision: $.trigger.revision
  - id: screen
    type: agent
    agent_id: {screening_id}
    depends_on: [reference]
    input:
      metadata: $.steps.reference
      audience: software-builders
  - id: initial_gate
    type: gate
    depends_on: [screen]
    predicate:
      left: $.steps.screen.score
      operator: gte
      right: 30
    reject:
      output:
        schema_version: 1
        status: initial_rejected
        reference: $.steps.reference
        screening: $.steps.screen
  - id: resolve
    type: resolve
    depends_on: [initial_gate]
    input:
      reference_id: $.trigger.reference_id
  - id: analyze
    type: agent
    agent_id: {analysis_id}
    depends_on: [resolve]
    input:
      metadata: $.steps.reference
      document: $.steps.resolve
      audience: software-builders
      maximum_quotes: 5
  - id: quality_score
    type: score
    depends_on: [analyze]
    input:
      dimensions:
{dimensions}
  - id: fine_gate
    type: gate
    depends_on: [quality_score]
    predicate:
      left: $.steps.quality_score.total
      operator: gte
      right: 70
    reject:
      output:
        schema_version: 1
        status: fine_rejected
        reference: $.steps.reference
        screening: $.steps.screen
        content: $.steps.analyze
        score: $.steps.quality_score
output:
  schema_version: 1
  status: qualified
  reference: $.steps.reference
  screening: $.steps.screen
  content: $.steps.analyze
  score: $.steps.quality_score
"""


def test_documented_analysis_examples_are_parseable_and_strict() -> None:
    examples = Path(__file__).parents[3] / "docs" / "examples"
    agents = [
        CreateAgentRequest.model_validate(
            json.loads((examples / filename).read_text())
        )
        for filename in (
            "screening-agent.json",
            "core-analysis-agent.json",
            "taxonomy-agent.json",
            "quality-scoring-agent.json",
            "review-agent.json",
            "finalizer-agent.json",
        )
    ]
    for agent in agents:
        Draft202012Validator.check_schema(agent.input_schema)
        Draft202012Validator.check_schema(agent.output_schema)
        assert agent.input_schema["additionalProperties"] is False
        assert agent.output_schema["additionalProperties"] is False
    assert agents[0].capabilities == ("screen-content",)
    assert [agent.capabilities[0] for agent in agents] == [
        "screen-content",
        "extract-content-insights",
        "classify-content",
        "score-content-quality",
        "review-content-analysis",
        "finalize-content-analysis",
    ]

    spec = parse_workflow_yaml(
        (examples / "article-analysis.yaml").read_text()
    )
    assert spec.projection == "content_analysis_v1"
    assert spec.topological_order() == (
        "reference",
        "screening",
        "initial_gate",
        "resolve",
        "core_analysis",
        "taxonomy",
        "quality_scoring",
        "review",
        "finalize",
        "deterministic_score",
        "fine_gate",
    )
    assert [
        node.id for node in spec.nodes if node.type == "gate"
    ] == ["initial_gate", "fine_gate"]


@pytest.mark.asyncio
async def test_reference_first_information_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (Path(__file__).parents[3] / "compose.yaml").exists()
    now = datetime(2026, 7, 31, 12, tzinfo=UTC)
    subscriptions = InMemorySubscriptionRepository()
    imported = await SubscriptionService(subscriptions).import_entries(
        preview_opml(
            b"""<?xml version="1.0"?>
<opml version="2.0"><body>
  <outline text="Example Engineering" type="rss"
    xmlUrl="https://example.com/feed.xml"/>
</body></opml>"""
        ).entries
    )
    subscription = (await subscriptions.list())[0]
    assert imported.created == 1

    rss = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example Engineering</title>
<item><guid>noise</guid><title>Noise</title>
<link>https://example.com/noise</link>
<description>Minor announcement.</description></item>
<item><guid>average</guid><title>Average</title>
<link>https://example.com/average</link>
<description>Potentially useful guide.</description></item>
<item><guid>excellent</guid><title>Excellent</title>
<link>https://example.com/excellent</link>
<description>Deep technical article.</description></item>
</channel></rss>"""

    async def source_server(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed.xml":
            return httpx.Response(
                200,
                content=rss,
                headers={"content-type": "application/rss+xml"},
            )
        title = request.url.path.removeprefix("/").title()
        return httpx.Response(
            200,
            content=f"""<html lang="en"><head><title>{title}</title></head>
<body><article>
<p>{ARTICLE_MARKER}. This sentence is visible only to the runtime Agent.</p>
<p>The article contains enough substantive prose for deterministic extraction
and structured analysis without retaining the original document.</p>
</article></body></html>""".encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    fetched = await FeedClient(
        transport=httpx.MockTransport(source_server)
    ).fetch(subscription.feed_url)
    assert isinstance(fetched, FeedDocument)
    references = InMemoryReferenceRepository()
    discovered = await IngestionService(references).ingest(
        subscription_id=subscription.id,
        entries=fetched.entries,
        fetched_at=now,
    )
    assert discovered.discovered == 3

    monkeypatch.setenv("FAKE_PROVIDER_KEY", "runtime-only-secret")
    agent_repository = InMemoryAgentRepository()
    registry = AgentRegistry(agent_repository)
    profile = ProviderProfile.create(
        name="E2E provider",
        provider="fake",
        model="deterministic",
        api_key_env="FAKE_PROVIDER_KEY",
    )
    await registry.register_provider(profile)
    input_base = {
        "type": "object",
        "additionalProperties": False,
        "required": ["metadata", "audience"],
        "properties": {
            "metadata": {"type": "object"},
            "audience": {"type": "string"},
        },
    }
    screen_agent = AgentDefinition.create(
        name="Metadata screening",
        description="Screens RSS metadata without resolving the article.",
        capabilities=("screen-content",),
        system_prompt="Judge only the supplied RSS metadata. Never claim full-text access.",
        provider_profile_id=profile.id,
        input_schema=input_base,
        output_schema=screening_output_schema(),
    )
    await registry.register_agent(screen_agent)
    analysis_input = {
        **input_base,
        "required": ["metadata", "document", "audience"],
        "properties": {
            **cast(dict[str, object], input_base["properties"]),
            "document": {"type": "object"},
            "maximum_quotes": {"type": "integer", "maximum": 5},
        },
    }
    analysis_agent = AgentDefinition.create(
        name="Full-content analysis",
        description="Produces bounded, structured article analysis.",
        capabilities=("analyze-content",),
        system_prompt="Use only the supplied document for facts and quotations.",
        provider_profile_id=profile.id,
        input_schema=analysis_input,
        output_schema=analysis_output_schema(),
    )
    await registry.register_agent(analysis_agent)

    fake_pi = FakePiClient()
    gateway = AgentGateway(registry, fake_pi)
    resolver = ContentResolver(
        network_policy=NetworkPolicy(resolver=public_address),
        transport=httpx.MockTransport(source_server),
    )

    async def reference_node(
        input: dict[str, object], _: NodeExecutionContext
    ) -> dict[str, object]:
        identifier = UUID(str(input["reference_id"]))
        reference = await references.get_reference(identifier)
        assert reference is not None
        revision = await references.get_revision(
            identifier,
            int(str(input["revision"])),
        )
        return {
            "reference_id": str(identifier),
            "revision": revision.number,
            "subscription_id": str(reference.subscription_id),
            "url": revision.url,
            "title": revision.title,
            "summary": revision.summary,
            "author": revision.author,
            "published_at": (
                revision.published_at.isoformat()
                if revision.published_at
                else None
            ),
            "updated_at": (
                revision.updated_at.isoformat()
                if revision.updated_at
                else None
            ),
            "observed_at": revision.observed_at.isoformat(),
        }

    async def resolve_node(
        input: dict[str, object], _: NodeExecutionContext
    ) -> dict[str, object]:
        reference = await references.get_reference(
            UUID(str(input["reference_id"]))
        )
        assert reference is not None
        document = asdict(await resolver.resolve(reference))
        assert ARTICLE_MARKER in document["text"]
        return {"_transient_document": True, **document}

    async def agent_node(
        input: dict[str, object], context: NodeExecutionContext
    ) -> dict[str, object]:
        assert context.agent_id is not None
        result = await gateway.execute(context.agent_id, input)
        return {
            **result.output,
            "_execution": {
                "agent_id": str(result.agent_id),
                "agent_version": result.agent_version,
                "provider": result.provider,
                "model": result.model,
                "usage": result.usage,
            },
        }

    async def score_node(
        input: dict[str, object], _: NodeExecutionContext
    ) -> dict[str, object]:
        raw = input["dimensions"]
        assert isinstance(raw, dict)
        return calculate_weighted_score(raw)

    workflows = InMemoryWorkflowRepository()
    spec = parse_workflow_yaml(
        workflow_source(screen_agent.id, analysis_agent.id)
    )
    await validate_workflow(spec, registry)
    definition = WorkflowDefinition.create(spec)
    definition.activate()
    await workflows.add_definition(definition)
    executor = WorkflowExecutor(
        workflows,
        handlers={
            "reference": reference_node,
            "resolve": resolve_node,
            "agent": agent_node,
            "score": score_node,
        },
    )
    analyses = InMemoryAnalysisRepository()
    run_service = WorkflowRunService(
        workflows,
        executor,
        projectors={
            "content_analysis_v1": AnalysisProjector(
                analyses,
                references,
                subscriptions,
            )
        },
    )
    for event in discovered.events:
        await run_service.execute(
            definition.id,
            trigger={
                "event": event.event_type,
                "reference_id": str(event.reference_id),
                "revision": event.revision,
            },
            idempotency_key=event.idempotency_key,
        )

    generated = await analyses.list(
        AnalysisQuery(effective_decision=None, limit=100)
    )
    by_title = {item.title: item for item in generated}
    statuses = [
        by_title[title].generated_status
        for title in ("Noise", "Average", "Excellent")
    ]
    assert statuses == ["initial_rejected", "fine_rejected", "qualified"]
    assert by_title["Noise"].total_score is None
    assert by_title["Average"].total_score == 60
    assert by_title["Excellent"].total_score == 90
    assert fake_pi.full_content_calls == 2
    assert all(
        ARTICLE_MARKER not in str(value)
        for value in fake_pi.screening_inputs
    )
    noise_run = next(
        run
        for run in await workflows.list_runs()
        if run.output and run.output["reference"]["title"] == "Noise"  # type: ignore[index]
    )
    assert [step.node_id for step in noise_run.steps] == [
        "reference",
        "screen",
        "initial_gate",
    ]

    calls_before_retry = fake_pi.full_content_calls
    average_event = next(
        event
        for event in discovered.events
        if event.reference_id == by_title["Average"].reference_id
    )
    await run_service.execute(
        definition.id,
        trigger={
            "event": average_event.event_type,
            "reference_id": str(average_event.reference_id),
            "revision": average_event.revision,
        },
        idempotency_key=average_event.idempotency_key,
    )
    assert fake_pi.full_content_calls == calls_before_retry
    assert len(
        await analyses.list(AnalysisQuery(effective_decision=None, limit=100))
    ) == 3

    overridden = await AnalysisService(analyses).override(
        by_title["Average"].id,
        decision="qualified",
        reason="Manual review confirms durable engineering value.",
        actor_subject="admin",
    )
    assert overridden.effective_decision == "qualified"
    assert overridden.generated_status == "fine_rejected"
    notes = InMemoryNoteRepository()
    created_note = await NoteService(notes, references, analyses).create(
        owner_subject="admin",
        reference_id=by_title["Average"].reference_id,
        analysis_id=by_title["Average"].id,
        body="Reuse this scoring approach in architecture reviews.",
    )
    assert created_note.reference_id == by_title["Average"].reference_id
    default_feed = await analyses.list(AnalysisQuery(limit=100))
    assert {item.title for item in default_feed} == {"Average", "Excellent"}

    persisted_database_dump = repr(
        (
            await workflows.list_runs(),
            await analyses.list(
                AnalysisQuery(effective_decision=None, limit=100)
            ),
            await notes.list_owned("admin"),
        )
    )
    assert ARTICLE_MARKER not in persisted_database_dump
    assert "runtime-only-secret" not in persisted_database_dump
