import shlex
import uuid
from dataclasses import asdict

from zeromind.agents.gateway import AgentGateway
from zeromind.agents.pi_rpc import PiRpcClient
from zeromind.agents.registry import AgentRegistry
from zeromind.content.network_policy import NetworkPolicy
from zeromind.content.resolver import ContentResolver
from zeromind.ingestion.repository import ReferenceRepository
from zeromind.shared.config import Settings
from zeromind.workflows.executor import NodeHandler, WorkflowExecutor
from zeromind.workflows.primitives import calculate_weighted_score
from zeromind.workflows.repository import WorkflowRepository


def build_workflow_executor(
    *,
    workflow_repository: WorkflowRepository,
    reference_repository: ReferenceRepository,
    agent_registry: AgentRegistry,
    settings: Settings,
) -> WorkflowExecutor:
    resolver = ContentResolver(network_policy=NetworkPolicy())
    gateway = AgentGateway(
        agent_registry,
        PiRpcClient(command=tuple(shlex.split(settings.pi_command))),
    )

    async def resolve_node(input: dict[str, object]) -> dict[str, object]:
        reference_id = uuid.UUID(str(input["reference_id"]))
        reference = await reference_repository.get_reference(reference_id)
        if reference is None:
            raise KeyError(reference_id)
        document = asdict(await resolver.resolve(reference))
        return {"_transient_document": True, **document}

    async def reference_node(input: dict[str, object]) -> dict[str, object]:
        reference_id = uuid.UUID(str(input["reference_id"]))
        reference = await reference_repository.get_reference(reference_id)
        if reference is None:
            raise ValueError(f"reference_not_found:{reference_id}")
        raw_revision = input.get("revision")
        try:
            revision = (
                await reference_repository.get_current_revision(reference_id)
                if raw_revision is None
                else await reference_repository.get_revision(
                    reference_id,
                    int(str(raw_revision)),
                )
            )
        except KeyError as error:
            raise ValueError(
                f"reference_revision_not_found:{reference_id}:{raw_revision}"
            ) from error
        return {
            "reference_id": str(reference.id),
            "revision": revision.number,
            "subscription_id": str(reference.subscription_id),
            "url": revision.url or reference.original_url,
            "title": revision.title,
            "summary": revision.summary,
            "author": revision.author,
            "published_at": (
                revision.published_at.isoformat()
                if revision.published_at
                else None
            ),
            "updated_at": (
                revision.updated_at.isoformat() if revision.updated_at else None
            ),
            "observed_at": revision.observed_at.isoformat(),
        }

    async def score_node(input: dict[str, object]) -> dict[str, object]:
        raw = input.get("dimensions")
        if not isinstance(raw, dict):
            raise ValueError("score dimensions must be an object")
        return calculate_weighted_score(raw)

    async def agent_node(input: dict[str, object]) -> dict[str, object]:
        raw_agent_id = input.pop("_agent_id", None)
        if raw_agent_id is None:
            raise ValueError("agent node has no agent identifier")
        result = await gateway.execute(uuid.UUID(str(raw_agent_id)), input)
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

    async def pass_through(input: dict[str, object]) -> dict[str, object]:
        return input

    handlers: dict[str, NodeHandler] = {
        "resolve": resolve_node,
        "reference": reference_node,
        "agent": agent_node,
        "score": score_node,
        "parallel": pass_through,
        "condition": pass_through,
        "webhook": pass_through,
    }
    return WorkflowExecutor(workflow_repository, handlers=handlers)
