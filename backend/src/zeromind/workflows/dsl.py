import re
from collections import deque
from typing import Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from zeromind.agents.registry import AgentRegistry

MAX_WORKFLOW_BYTES = 1024 * 1024
PATH = re.compile(r"^\$\.(?:[A-Za-z_][A-Za-z0-9_]*)(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
ALLOWED_EVENTS = {"reference.discovered", "reference.updated", "manual"}
ProjectionName = Literal["content_analysis_v1"]
PredicateOperator = Literal["gt", "gte", "lt", "lte", "eq", "ne", "in", "not_in"]


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


class PredicateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: object
    operator: PredicateOperator
    right: object


class RejectSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: dict[str, object]


class NodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
    type: Literal[
        "resolve",
        "reference",
        "agent",
        "score",
        "gate",
        "condition",
        "parallel",
        "webhook",
    ]
    depends_on: tuple[str, ...] = ()
    input: dict[str, object] = Field(default_factory=dict)
    agent_id: UUID | None = None
    predicate: PredicateSpec | None = None
    reject: RejectSpec | None = None
    timeout_seconds: float = Field(default=120, gt=0, le=600)
    retry: RetrySpec = Field(default_factory=RetrySpec)

    @model_validator(mode="after")
    def type_requirements(self) -> "NodeSpec":
        if self.type == "agent" and self.agent_id is None:
            raise ValueError("agent node requires agent_id")
        if self.type != "agent" and self.agent_id is not None:
            raise ValueError("agent_id is only valid for agent nodes")
        if self.type == "gate":
            if self.predicate is None or self.reject is None:
                raise ValueError("gate node requires predicate and reject output")
        elif self.predicate is not None or self.reject is not None:
            raise ValueError("predicate and reject are only valid for gate nodes")
        _validate_mappings(self.input)
        if self.predicate is not None:
            _validate_mappings(self.predicate.left)
            _validate_mappings(self.predicate.right)
        if self.reject is not None:
            _validate_mappings(self.reject.output)
        return self


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    trigger: TriggerSpec
    projection: ProjectionName | None = None
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
        layers = self.topological_layers()
        self._validate_terminal_gates(layers)
        return self

    def _validate_terminal_gates(
        self,
        layers: tuple[tuple[str, ...], ...],
    ) -> None:
        outgoing: dict[str, set[str]] = {node.id: set() for node in self.nodes}
        for node in self.nodes:
            for dependency in node.depends_on:
                outgoing[dependency].add(node.id)
        layer_by_id = {
            identifier: layer_index
            for layer_index, layer in enumerate(layers)
            for identifier in layer
        }
        for gate in (node for node in self.nodes if node.type == "gate"):
            gate_layer = layer_by_id[gate.id]
            if len(layers[gate_layer]) != 1:
                raise ValueError(
                    f"gate {gate.id} must be the only node in its topological layer"
                )
            descendants: set[str] = set()
            pending = list(outgoing[gate.id])
            while pending:
                identifier = pending.pop()
                if identifier in descendants:
                    continue
                descendants.add(identifier)
                pending.extend(outgoing[identifier])
            later = {
                identifier
                for identifier, layer_index in layer_by_id.items()
                if layer_index > gate_layer
            }
            bypass = later - descendants
            if bypass:
                raise ValueError(
                    f"nodes after gate {gate.id} must descend from it: {sorted(bypass)}"
                )

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
    elif isinstance(value, str):
        if PATH.fullmatch(value):
            return
        if value.startswith("$"):
            raise ValueError(f"mapping must be a restricted $.path expression: {value}")
        stripped = value.lstrip()
        if (
            "${" in value
            or "$(" in value
            or "`" in value
            or "__import__" in value
            or stripped.startswith("lambda ")
        ):
            raise ValueError(f"mapping contains an unsafe literal: {value}")


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
