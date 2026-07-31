"""JCode v0.55 adapter for Graph Coder portable execution graphs.

The adapter intentionally emits public swarm tool operation bundles. It does not depend on
private sockets or implementation-specific protocols.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from graph_coder.errors import CompatibilityError
from graph_coder.graph import (
    ExecutionGraph,
    GraphNode,
    NodeKind,
    NodeRole,
    PlanUnit,
)

TARGET_VERSION = "0.55.0"
SUPPORTED_CAPABILITIES = {
    "task_graph",
    "run_plan",
    "background_execution",
    "director_mediated",
    "typed_reports",
}

# Managers are deliberately absent from this map. They are control-plane agents,
# like the Director: they advise and review, so they are never dispatched as
# swarm implementation tasks. Disguising a manager as a worker would hand it a
# write scope the graph explicitly denies it.
_KIND_TO_NATIVE = {
    NodeKind.EXPLORE: "explore",
    NodeKind.SPIKE: "explore",
    NodeKind.IMPLEMENT: "implement",
    NodeKind.VERIFY: "verify",
    NodeKind.INTEGRATE: "synthesize",
    NodeKind.REPAIR: "fix",
    NodeKind.RELEASE: "synthesize",
}


@dataclass(frozen=True, slots=True)
class JCodeOperation:
    """A Director-mediated swarm tool call description."""

    action: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"tool": "swarm", "action": self.action, "arguments": self.arguments}


@dataclass(slots=True)
class JCodeAdapter:
    """Compile Graph Coder graphs to JCode public swarm operations."""

    version_output: str | None = None
    command: tuple[str, ...] = ("jcode", "--version")
    target_version: str = TARGET_VERSION
    supported_capabilities: set[str] = field(default_factory=lambda: set(SUPPORTED_CAPABILITIES))

    native_kind_map: ClassVar[dict[NodeKind, str]] = _KIND_TO_NATIVE

    @classmethod
    def from_fixture(cls, path: str | Path) -> JCodeAdapter:
        return cls(version_output=Path(path).read_text(encoding="utf-8"))

    def detect_version(self) -> str | None:
        return detect_jcode_version(self.version_output, command=self.command)

    def compatibility(self) -> dict[str, Any]:
        version = self.detect_version()
        return {
            "adapter": "jcode",
            "detected_version": version,
            "target_version": self.target_version,
            "compatible": _version_tuple(version) >= _version_tuple(self.target_version)
            if version
            else False,
            "transport": "public swarm tool operations",
            "private_socket_dependency": False,
        }

    def validate_capabilities(self, graph: ExecutionGraph) -> None:
        requested = {
            capability
            for node in graph.nodes
            for capability in node.route.capabilities
            if capability not in self.supported_capabilities
        }
        if requested:
            raise CompatibilityError(
                "JCode adapter does not support capabilities: " + ", ".join(sorted(requested))
            )

    def native_kind(self, kind: NodeKind | str) -> str:
        resolved = NodeKind(kind)
        if resolved is NodeKind.MANAGE:
            raise CompatibilityError(
                "manage nodes are control-plane agents and are not dispatched as swarm "
                "tasks; they advise and review their own subtree"
            )
        return self.native_kind_map[resolved]

    def dispatchable(self, graph: ExecutionGraph) -> list[GraphNode]:
        """Nodes JCode actually runs: everything except the Director and managers."""

        return [
            node
            for node in graph.topological_nodes()
            if node.id != graph.root_id and node.kind != NodeKind.MANAGE
        ]

    def control_plane(self, graph: ExecutionGraph) -> list[GraphNode]:
        return [node for node in graph.topological_nodes() if node.kind == NodeKind.MANAGE]

    def task_graph_bundle(self, graph: ExecutionGraph) -> JCodeOperation:
        graph.validate()
        self.validate_capabilities(graph)
        dispatch_nodes = self.dispatchable(graph)
        managers = self.control_plane(graph)
        recursive = bool(graph.metadata.get("recursive_spawning", False))
        return JCodeOperation(
            action="task_graph",
            arguments={
                "mode": "deep" if recursive else "light",
                "nodes": [self._node_to_task(node, graph.root_id) for node in dispatch_nodes],
                "metadata": {
                    "schema_version": graph.schema_version,
                    "root_id": graph.root_id,
                    "director_preserved": graph.root_id == "Director",
                    "target_jcode_version": self.target_version,
                    "recursive_spawning": recursive,
                    "private_protocol_dependency": False,
                    "managers": [
                        {
                            "manager_id": manager.id,
                            "authority": str(manager.authority),
                            "write_scopes": list(manager.write_scopes),
                            "reviews": [
                                node.id for node in graph.nodes if node.review_owner == manager.id
                            ],
                        }
                        for manager in managers
                    ],
                    "review_assignments": {
                        node.id: node.review_owner for node in dispatch_nodes if node.review_owner
                    },
                },
            },
        )

    def run_plan_bundle(self, graph: ExecutionGraph) -> JCodeOperation:
        graph.validate()
        self.validate_capabilities(graph)
        return JCodeOperation(
            action="run_plan",
            arguments={
                "background": True,
                "wake": True,
                "notify": True,
                "retain_agents": False,
                "concurrency_limit": int(graph.metadata.get("max_active_workers", 8)),
                "root_director": graph.root_id,
                "prompt": self.director_prompt(graph),
            },
        )

    def operation_bundle(self, graph: ExecutionGraph) -> list[JCodeOperation]:
        return [self.task_graph_bundle(graph), self.run_plan_bundle(graph)]

    def director_prompt(self, graph: ExecutionGraph) -> str:
        # Managers and the Director coordinate; they are not dispatched work.
        units = [
            unit
            for unit in graph.compile_plan_units()
            if graph.root_id not in unit.node_ids and NodeKind(unit.kind) is not NodeKind.MANAGE
        ]
        lines = [
            "You are the foreground JCode Director. Preserve Director control.",
            "You direct, advise, and review branch outputs. You never edit implementation "
            "files and never complete a failed worker's task yourself.",
            f"Execute Graph Coder graph {graph.schema_version} "
            f"against JCode target {self.target_version}.",
            "Use public swarm task_graph/run_plan operations with background execution.",
            "Plan units:",
        ]
        for unit in units:
            lines.append(self._unit_prompt(unit))
        return "\n".join(lines)

    def report_template(self, node: GraphNode) -> str:
        acceptance = "; ".join(node.acceptance) or "No acceptance criteria supplied."
        review = "; ".join(node.review.checklist) or "No review checklist supplied."
        scopes = f"read={node.read_scopes or ['<none>']} write={node.write_scopes or ['<none>']}"
        return (
            f"Report for {node.id} ({node.kind}).\n"
            f"Acceptance: {acceptance}\nReview: {review}\nScopes: {scopes}\n"
            "Include validation performed, changed artifacts, blockers, and confidence."
        )

    def _node_to_task(self, node: GraphNode, root_id: str) -> dict[str, Any]:
        content = self._node_prompt(node)
        task: dict[str, Any] = {
            "id": node.id,
            "content": content,
            "kind": self.native_kind(node.kind),
            "depends_on": [dependency for dependency in node.depends_on if dependency != root_id],
            "priority": str(node.priority),
            "metadata": {
                "graph_coder_kind": str(node.kind),
                "role": str(node.role),
                "authority": str(node.authority),
                "review_owner": node.review_owner,
                "unit_ids": list(node.unit_ids),
                "parent_owner": node.parent_owner,
                "risk": str(node.risk),
                "failure_domain": node.failure_domain,
                "read_scopes": list(node.read_scopes),
                "write_scopes": list(node.write_scopes),
                "artifact_inputs": [asdict(a) for a in node.artifact_inputs],
                "artifact_outputs": [asdict(a) for a in node.artifact_outputs],
                "acceptance": list(node.acceptance),
                "review_required": node.review.required,
                "review_checklist": list(node.review.checklist),
                "max_attempts": node.limits.max_attempts,
                "heartbeat_seconds": node.limits.heartbeat_seconds,
                "max_expansions": node.limits.max_expansions,
            },
        }
        if node.route.model:
            task["model"] = node.route.model
        if node.route.effort:
            task["effort"] = node.route.effort
        if node.role == NodeRole.COMPOSITE and node.children:
            task["children"] = list(node.children)
        return task

    def _node_prompt(self, node: GraphNode) -> str:
        review_line = (
            f"Submit your report to manager {node.review_owner} for review. Only its passing "
            "review completes this node; you do not mark yourself complete."
            if node.review_owner
            else "No manager is assigned to review this node."
        )
        return "\n".join(
            [
                f"Graph Coder node {node.id}: {node.title}",
                review_line,
                f"Portable kind: {node.kind}; native kind: {self.native_kind(node.kind)}.",
                f"Read scopes: {node.read_scopes or ['<none>']}.",
                f"Write scopes: {node.write_scopes or ['<none>']}.",
                f"Acceptance: {node.acceptance or ['<none>']}.",
                f"Review checklist: {node.review.checklist or ['<none>']}.",
                node.prompt,
                self.report_template(node),
            ]
        )

    def _unit_prompt(self, unit: PlanUnit) -> str:
        return (
            f"- {unit.id}: kind={self.native_kind(unit.kind)} depends={unit.depends_on} "
            f"writes={unit.write_scopes}\n{unit.prompt}"
        )


def detect_jcode_version(
    output: str | None = None, *, command: tuple[str, ...] = ("jcode", "--version")
) -> str | None:
    """Detect a JCode semantic version from supplied text or command output."""

    text = output
    if text is None:
        try:
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True, timeout=5
            )
        except (OSError, subprocess.SubprocessError):
            return None
        text = f"{completed.stdout}\n{completed.stderr}"
    match = re.search(r"v?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.\-]+)?)", text)
    return match.group(1) if match else None


def _version_tuple(version: str | None) -> tuple[int, int, int]:
    if version is None:
        return (0, 0, 0)
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return (0, 0, 0)
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)
