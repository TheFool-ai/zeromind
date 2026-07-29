import re
from collections import deque
from typing import Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from zeromind.agents.registry import AgentRegistry

MAX_WORKFLOW_BYTES = 1024 * 1024
PATH = re.compile(r"^\$\.(?:[A-Za-z_][A-Za-z0-9_]*)(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
ALLOWED_EVENTS = {"reference.discovered", "reference.updated", "manual"}


class WorkflowValidationError(ValueError):
    pass


class RetrySpec(BaseModel):
    max_attempts: int = Field(default=1, ge=1, le=5)
    backoff_seconds: float = Field(default=1, ge=0, le=300)


class TriggerSpec(BaseModel):
    events: tuple[str, ...]

    @model_validator(mode="after")
    def valid_events(self) -> "TriggerSpec":
        if not self.events:
            raise ValueError("trigger events cannot be empty")
        unknown = set(self.events) - ALLOWED_EVENTS
        if unknown:
            raise ValueError(f"unsupported trigger events: {sorted(unknown)}")
        return self


class NodeSpec(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
    type: Literal["resolve", "agent", "condition", "parallel", "webhook"]
    depends_on: tuple[str, ...] = ()
    input: dict[str, object] = Field(default_factory=dict)
    agent_id: UUID | None = None
    timeout_seconds: float = Field(default=120, gt=0, le=600)
    retry: RetrySpec = Field(default_factory=RetrySpec)

    @model_validator(mode="after")
    def type_requirements(self) -> "NodeSpec":
        if self.type == "agent" and self.agent_id is None:
            raise ValueError("agent node requires agent_id")
        if self.type != "agent" and self.agent_id is not None:
            raise ValueError("agent_id is only valid for agent nodes")
        _validate_mappings(self.input)
        return self


class WorkflowSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    trigger: TriggerSpec
    nodes: tuple[NodeSpec, ...]
    output: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_graph(self) -> "WorkflowSpec":
        if not self.nodes:
            raise ValueError("workflow must contain at least one node")
        identifiers = [node.id for node in self.nodes]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("workflow node IDs must be unique")
        known = set(identifiers)
        for node in self.nodes:
            missing = set(node.depends_on) - known
            if missing:
                raise ValueError(
                    f"node {node.id} has missing dependencies: {sorted(missing)}"
                )
            if node.id in node.depends_on:
                raise ValueError(f"node {node.id} cannot depend on itself")
        _validate_mappings(self.output)
        self.topological_order()
        return self

    def topological_layers(self) -> tuple[tuple[str, ...], ...]:
        order = {node.id: index for index, node in enumerate(self.nodes)}
        incoming = {node.id: set(node.depends_on) for node in self.nodes}
        outgoing: dict[str, list[str]] = {node.id: [] for node in self.nodes}
        for node in self.nodes:
            for dependency in node.depends_on:
                outgoing[dependency].append(node.id)
        ready = deque(
            sorted(
                (identifier for identifier, deps in incoming.items() if not deps),
                key=order.get,  # type: ignore[arg-type]
            )
        )
        layers: list[tuple[str, ...]] = []
        visited = 0
        while ready:
            layer = tuple(ready)
            ready.clear()
            layers.append(layer)
            visited += len(layer)
            next_ready: list[str] = []
            for identifier in layer:
                for dependent in outgoing[identifier]:
                    incoming[dependent].discard(identifier)
                    if not incoming[dependent]:
                        next_ready.append(dependent)
            ready.extend(sorted(set(next_ready), key=order.get))  # type: ignore[arg-type]
        if visited != len(self.nodes):
            raise WorkflowValidationError("workflow graph contains a cycle")
        return tuple(layers)

    def topological_order(self) -> tuple[str, ...]:
        return tuple(
            identifier
            for layer in self.topological_layers()
            for identifier in layer
        )


def _validate_mappings(value: object) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _validate_mappings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _validate_mappings(item)
    elif isinstance(value, str) and not PATH.fullmatch(value):
        raise ValueError(f"mapping must be a restricted $.path expression: {value}")


def parse_workflow_yaml(source: str) -> WorkflowSpec:
    if not source.strip() or len(source.encode()) > MAX_WORKFLOW_BYTES:
        raise WorkflowValidationError("workflow YAML is empty or exceeds 1 MiB")
    try:
        decoded = yaml.safe_load(source)
        return WorkflowSpec.model_validate(decoded)
    except WorkflowValidationError:
        raise
    except (yaml.YAMLError, ValidationError, ValueError) as error:
        raise WorkflowValidationError(str(error)) from error


async def validate_workflow(
    spec: WorkflowSpec,
    agent_registry: AgentRegistry,
) -> None:
    for node in spec.nodes:
        if node.agent_id is None:
            continue
        try:
            definition = await agent_registry.get_agent(node.agent_id)
        except KeyError as error:
            raise WorkflowValidationError(
                f"agent {node.agent_id} is not registered"
            ) from error
        if not definition.enabled:
            raise WorkflowValidationError(f"agent {node.agent_id} is disabled")

