"""Typed portable execution graph for Graph Coder v1."""

from __future__ import annotations

import fnmatch
import json
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self

from graph_coder.errors import ContractError

SCHEMA_VERSION = "graph-coder/v1"


class NodeKind(StrEnum):
    """Portable node kinds.

    There is deliberately no `review` kind. Review is a manager verdict and a
    durable artifact, not a task in the delegation DAG, so a graph can never
    record the one structure the product forbids. `MANAGE` replaces it: an
    advisory control-plane node that owns a branch and reviews its children.
    """

    MANAGE = "manage"
    EXPLORE = "explore"
    SPIKE = "spike"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    INTEGRATE = "integrate"
    REPAIR = "repair"
    RELEASE = "release"


class NodeRole(StrEnum):
    ATOMIC = "atomic"
    COMPOSITE = "composite"


class NodeAuthority(StrEnum):
    """Whether a node may touch the repository at all."""

    ADVISORY_ONLY = "advisory_only"
    IMPLEMENTATION = "implementation"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


FailureDomain = Literal["node", "branch", "graph", "external"]


@dataclass(slots=True)
class ArtifactRef:
    """A named artifact consumed or produced by a node."""

    name: str
    type: str = "generic"
    producer: str | None = None
    required: bool = True
    external: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | str) -> Self:
        if isinstance(data, str):
            return cls(name=data)
        return cls(**data)


@dataclass(slots=True)
class ReviewPolicy:
    required: bool = False
    reviewers: list[str] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RouteSpec:
    adapter: str = "jcode"
    model: str | None = None
    effort: str | None = None
    spawn_mode: str | None = None
    capabilities: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Limits:
    max_attempts: int = 1
    heartbeat_seconds: int = 300
    max_expansions: int = 0

    def validate(self, *, node_id: str) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise ContractError(f"node {node_id} max_attempts must be in 1..10")
        if not 1 <= self.heartbeat_seconds <= 86_400:
            raise ContractError(f"node {node_id} heartbeat_seconds must be in 1..86400")
        if not 0 <= self.max_expansions <= 100:
            raise ContractError(f"node {node_id} max_expansions must be in 0..100")


@dataclass(slots=True)
class CostEstimate:
    tokens: int | None = None
    dollars: float | None = None
    minutes: int | None = None


@dataclass(slots=True)
class GraphNode:
    id: str
    kind: NodeKind | str
    title: str
    prompt: str = ""
    unit_ids: list[str] = field(default_factory=list)
    parent_owner: str | None = "Director"
    role: NodeRole | str = NodeRole.ATOMIC
    authority: NodeAuthority | str = NodeAuthority.IMPLEMENTATION
    review_owner: str | None = None
    depends_on: list[str] = field(default_factory=list)
    artifact_inputs: list[ArtifactRef] = field(default_factory=list)
    artifact_outputs: list[ArtifactRef] = field(default_factory=list)
    read_scopes: list[str] = field(default_factory=list)
    write_scopes: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    review: ReviewPolicy = field(default_factory=ReviewPolicy)
    route: RouteSpec = field(default_factory=RouteSpec)
    risk: Risk | str = Risk.MEDIUM
    priority: Priority | str = Priority.NORMAL
    cost: CostEstimate = field(default_factory=CostEstimate)
    limits: Limits = field(default_factory=Limits)
    failure_domain: FailureDomain = "node"
    merge_strategy: str | None = None
    children: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = NodeKind(self.kind)
        self.role = NodeRole(self.role)
        self.authority = NodeAuthority(self.authority)
        self.risk = Risk(self.risk)
        self.priority = Priority(self.priority)
        self.artifact_inputs = [
            a if isinstance(a, ArtifactRef) else ArtifactRef.from_dict(a)
            for a in self.artifact_inputs
        ]
        self.artifact_outputs = [
            a if isinstance(a, ArtifactRef) else ArtifactRef.from_dict(a)
            for a in self.artifact_outputs
        ]
        if isinstance(self.review, dict):
            self.review = ReviewPolicy(**self.review)
        if isinstance(self.route, dict):
            self.route = RouteSpec(**self.route)
        if isinstance(self.cost, dict):
            self.cost = CostEstimate(**self.cost)
        if isinstance(self.limits, dict):
            self.limits = Limits(**self.limits)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = str(self.kind)
        data["role"] = str(self.role)
        data["authority"] = str(self.authority)
        data["risk"] = str(self.risk)
        data["priority"] = str(self.priority)
        return data


@dataclass(slots=True)
class PlanUnit:
    id: str
    node_ids: list[str]
    depends_on: list[str]
    kind: NodeKind
    prompt: str
    write_scopes: list[str]
    route: RouteSpec


@dataclass(slots=True)
class ExecutionGraph:
    nodes: list[GraphNode]
    root_id: str = "Director"
    schema_version: str = SCHEMA_VERSION
    frontier: list[str] = field(default_factory=list)
    max_nodes: int = 100
    max_depth: int = 6
    max_fanout: int = 8
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.nodes = [n if isinstance(n, GraphNode) else GraphNode(**n) for n in self.nodes]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ContractError(f"unsupported graph schema {data.get('schema_version')!r}")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "root_id": self.root_id,
            "frontier": list(self.frontier),
            "max_nodes": self.max_nodes,
            "max_depth": self.max_depth,
            "max_fanout": self.max_fanout,
            "metadata": dict(self.metadata),
            "nodes": [node.to_dict() for node in self.nodes],
        }

    @classmethod
    def load_json(cls, path: str | Path) -> Self:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_json(cls, text: str) -> Self:
        return cls.from_dict(json.loads(text))

    def dump_json(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def by_id(self) -> dict[str, GraphNode]:
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ContractError("node ids must be unique")
        return {node.id: node for node in self.nodes}

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"unsupported graph schema {self.schema_version!r}")
        if len(self.nodes) > self.max_nodes:
            raise ContractError("graph exceeds max_nodes")
        if self.max_nodes < 1 or self.max_depth < 1 or self.max_fanout < 1:
            raise ContractError("graph bounds must be positive")
        nodes = self.by_id()
        if self.root_id not in nodes:
            raise ContractError(f"root node {self.root_id!r} is missing")
        for node in self.nodes:
            if not node.id:
                raise ContractError("node id cannot be empty")
            node.limits.validate(node_id=node.id)
            refs = [*node.depends_on, *node.children]
            missing = [dep for dep in refs if dep not in nodes]
            if missing:
                raise ContractError(f"node {node.id} references unknown nodes {missing}")
            if len(node.children) > self.max_fanout:
                raise ContractError(f"node {node.id} exceeds max_fanout")
            for artifact in node.artifact_outputs:
                if artifact.producer not in (None, node.id):
                    raise ContractError(f"artifact {artifact.name} producer must be its node")
                artifact.producer = node.id
        unknown_frontier = [node_id for node_id in self.frontier if node_id not in nodes]
        if unknown_frontier:
            raise ContractError(f"frontier references unknown nodes {unknown_frontier}")
        self._validate_artifacts(nodes)
        self._validate_acyclic_and_depth(nodes)
        self._validate_write_safety(nodes)
        self._validate_authority(nodes)

    def _validate_authority(self, nodes: dict[str, GraphNode]) -> None:
        """Enforce the manager and worker boundary at compile time.

        A manager that can write to the repository is not a manager, and a
        review owner that is not an advisory manager is a reviewer wearing a
        manager's name. Both are rejected here rather than left to prose.
        """

        for node in self.nodes:
            if node.kind == NodeKind.MANAGE:
                if node.role != NodeRole.COMPOSITE:
                    raise ContractError(f"manage node {node.id} must be composite")
                if node.authority != NodeAuthority.ADVISORY_ONLY:
                    raise ContractError(f"manage node {node.id} must be advisory_only")
                if node.write_scopes:
                    raise ContractError(
                        f"manage node {node.id} must have an empty write scope; "
                        "managers advise and review, they do not implement"
                    )
            elif node.authority == NodeAuthority.ADVISORY_ONLY and node.write_scopes:
                raise ContractError(f"advisory_only node {node.id} must have an empty write scope")

            if node.review_owner is None:
                continue
            if node.review_owner == node.id:
                raise ContractError(f"node {node.id} cannot review itself")
            owner = nodes.get(node.review_owner)
            if owner is None:
                raise ContractError(
                    f"node {node.id} names unknown review_owner {node.review_owner}"
                )
            if owner.id != self.root_id and owner.kind != NodeKind.MANAGE:
                raise ContractError(
                    f"review_owner {owner.id} of node {node.id} must be a manage node "
                    "or the root Director"
                )

    def _validate_artifacts(self, nodes: dict[str, GraphNode]) -> None:
        producers: dict[str, str] = {}
        for node in self.nodes:
            for artifact in node.artifact_outputs:
                if artifact.name in producers and producers[artifact.name] != node.id:
                    raise ContractError(
                        f"artifact {artifact.name} has multiple producers: "
                        f"{producers[artifact.name]} and {node.id}"
                    )
                producers[artifact.name] = node.id
        for node in self.nodes:
            for artifact in node.artifact_inputs:
                producer = artifact.producer or producers.get(artifact.name)
                if artifact.external and producer is not None:
                    raise ContractError(
                        f"external artifact {artifact.name} cannot name a graph producer"
                    )
                if artifact.required and producer is None and not artifact.external:
                    raise ContractError(
                        f"artifact {artifact.name} consumed by {node.id} has no producer"
                    )
                if producer is not None and producer not in nodes:
                    raise ContractError(f"artifact {artifact.name} producer {producer} is unknown")
                if producer is not None and producer not in node.depends_on and producer != node.id:
                    raise ContractError(
                        f"node {node.id} must depend on artifact producer {producer}"
                    )

    def _validate_acyclic_and_depth(self, nodes: dict[str, GraphNode]) -> None:
        indegree = {node_id: 0 for node_id in nodes}
        children: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            for dep in node.depends_on:
                indegree[node.id] += 1
                children[dep].append(node.id)
        queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
        seen: list[str] = []
        depth = {node_id: 1 for node_id in queue}
        while queue:
            node_id = queue.popleft()
            seen.append(node_id)
            for child in children[node_id]:
                depth[child] = max(depth.get(child, 1), depth[node_id] + 1)
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(seen) != len(nodes):
            raise ContractError("graph dependencies must be acyclic")
        if depth and max(depth.values()) > self.max_depth:
            raise ContractError("graph exceeds max_depth")

    def _validate_write_safety(self, nodes: dict[str, GraphNode]) -> None:
        reachability = {node.id: self._ancestors(node.id, nodes) for node in self.nodes}
        for index, left in enumerate(self.nodes):
            for right in self.nodes[index + 1 :]:
                overlap = {
                    left_scope
                    for left_scope in left.write_scopes
                    for right_scope in right.write_scopes
                    if _scopes_overlap(left_scope, right_scope)
                }
                if not overlap:
                    continue
                ordered = left.id in reachability[right.id] or right.id in reachability[left.id]
                merged = (
                    left.merge_strategy is not None and left.merge_strategy == right.merge_strategy
                )
                if not ordered and not merged:
                    raise ContractError(
                        "unsafe concurrent overlapping writes "
                        f"{sorted(overlap)} by {left.id} and {right.id}"
                    )

    def ready_frontier(self, completed: Iterable[str] = ()) -> list[str]:
        """Return deterministic ready nodes while preserving independent branches."""

        completed_ids = set(completed)
        nodes = self.by_id()
        return sorted(
            node.id
            for node in self.nodes
            if node.id not in completed_ids
            and all(dependency in completed_ids for dependency in node.depends_on)
            and node.id in nodes
        )

    def _ancestors(self, node_id: str, nodes: dict[str, GraphNode]) -> set[str]:
        result: set[str] = set()
        stack = list(nodes[node_id].depends_on)
        while stack:
            dep = stack.pop()
            if dep in result:
                continue
            result.add(dep)
            stack.extend(nodes[dep].depends_on)
        return result

    def topological_nodes(self) -> list[GraphNode]:
        self.validate()
        nodes = self.by_id()
        indegree = {node.id: len(node.depends_on) for node in self.nodes}
        children: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            for dep in node.depends_on:
                children[dep].append(node.id)
        queue = deque([node.id for node in self.nodes if indegree[node.id] == 0])
        ordered: list[GraphNode] = []
        while queue:
            node_id = queue.popleft()
            ordered.append(nodes[node_id])
            for child in children[node_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        return ordered

    def compile_plan_units(self) -> list[PlanUnit]:
        """Compile atomic work into route-compatible units.

        Composite nodes stay as coordination units. Adjacent atomic nodes with the same route, kind,
        dependencies, and no writes are grouped because they are safe to execute as one prompt.
        """

        ordered = self.topological_nodes()
        units: list[PlanUnit] = []
        consumed: set[str] = set()
        for node in ordered:
            if node.id in consumed:
                continue
            group = [node]
            if node.role == NodeRole.ATOMIC and not node.write_scopes:
                for candidate in ordered[ordered.index(node) + 1 :]:
                    if candidate.id in consumed or candidate.role != NodeRole.ATOMIC:
                        continue
                    same_route = candidate.route == node.route
                    same_kind = candidate.kind == node.kind
                    same_deps = set(candidate.depends_on) == set(node.depends_on)
                    if same_route and same_kind and same_deps and not candidate.write_scopes:
                        group.append(candidate)
                        consumed.add(candidate.id)
            consumed.add(node.id)
            node_ids = [item.id for item in group]
            units.append(
                PlanUnit(
                    id="+".join(node_ids),
                    node_ids=node_ids,
                    depends_on=sorted(
                        {dep for item in group for dep in item.depends_on if dep not in node_ids}
                    ),
                    kind=NodeKind(node.kind),
                    prompt="\n\n".join(
                        f"[{item.id}] {item.title}\n{item.prompt}" for item in group
                    ),
                    write_scopes=sorted({scope for item in group for scope in item.write_scopes}),
                    route=node.route,
                )
            )
        return units


def load_json(path: str | Path) -> ExecutionGraph:
    return ExecutionGraph.load_json(path)


def dump_json(graph: ExecutionGraph, path: str | Path) -> None:
    graph.dump_json(path)


def validate_graph(graph: ExecutionGraph) -> None:
    graph.validate()


def compile_plan_units(graph: ExecutionGraph) -> list[PlanUnit]:
    return graph.compile_plan_units()


def _scopes_overlap(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        return str(PurePosixPath(value.replace("\\", "/"))).rstrip("/").lower()

    a, b = normalize(left), normalize(right)
    if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
        return True
    return fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a)
