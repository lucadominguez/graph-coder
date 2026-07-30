"""Execution states, manager review transitions, and branch-local failure isolation.

The single rule this module exists to enforce: a unit becomes `completed` only
through a passing manager review, and only that transition makes its dependents
eligible. A worker reporting success is not completion.

The second rule: a node that cannot proceed blocks its transitive dependents and
nothing else. Independent branches keep running.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .errors import ContractError

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from .graph import ExecutionGraph


class ExecutionState(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    REPAIR_REQUIRED = "repair_required"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    HUMAN_REQUIRED = "human_required"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: States from which no further work is dispatched for that node.
TERMINAL_STATES: frozenset[ExecutionState] = frozenset(
    {ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED}
)

#: The only state that satisfies a dependency. Deliberately just one value: a
#: worker's own claim of success does not unlock anything downstream.
DEPENDENCY_SATISFYING_STATES: frozenset[ExecutionState] = frozenset({ExecutionState.COMPLETED})

ALLOWED_TRANSITIONS: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.PENDING: frozenset(
        {
            ExecutionState.READY,
            ExecutionState.BLOCKED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.READY: frozenset(
        {
            ExecutionState.RUNNING,
            ExecutionState.BLOCKED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.RUNNING: frozenset(
        {
            ExecutionState.AWAITING_REVIEW,
            ExecutionState.BLOCKED,
            ExecutionState.HUMAN_REQUIRED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }
    ),
    # Only a manager verdict leaves awaiting_review.
    ExecutionState.AWAITING_REVIEW: frozenset(
        {
            ExecutionState.COMPLETED,
            ExecutionState.REPAIR_REQUIRED,
            ExecutionState.HUMAN_REQUIRED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.REPAIR_REQUIRED: frozenset(
        {
            ExecutionState.RUNNING,
            ExecutionState.HUMAN_REQUIRED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.BLOCKED: frozenset(
        {
            ExecutionState.PENDING,
            ExecutionState.READY,
            ExecutionState.HUMAN_REQUIRED,
            ExecutionState.CANCELLED,
        }
    ),
    # A human decision reopens the branch; the failure evidence is not erased.
    ExecutionState.HUMAN_REQUIRED: frozenset(
        {
            ExecutionState.READY,
            ExecutionState.RUNNING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.COMPLETED: frozenset({ExecutionState.REPAIR_REQUIRED}),
    ExecutionState.FAILED: frozenset({ExecutionState.READY, ExecutionState.CANCELLED}),
    ExecutionState.CANCELLED: frozenset(),
}

#: Verdicts a manager may return. There is no "approve with comments".
MANAGER_VERDICTS: frozenset[str] = frozenset({"pass", "repair_required", "human_required"})

VERDICT_TO_STATE: dict[str, ExecutionState] = {
    "pass": ExecutionState.COMPLETED,
    "repair_required": ExecutionState.REPAIR_REQUIRED,
    "human_required": ExecutionState.HUMAN_REQUIRED,
}

#: Execution events appended to the ledger. Advice, context, and escalation are
#: control-plane events, never dependency edges, so the DAG stays acyclic.
EXECUTION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "worker.dispatched",
        "worker.submitted",
        "manager.review_requested",
        "manager.review_passed",
        "manager.repair_requested",
        "manager.advice_requested",
        "manager.advice_supplied",
        "manager.escalated",
        "context.requested",
        "context.supplied",
        "branch.human_required",
        "branch.resumed",
    }
)


def coerce_state(value: str | ExecutionState) -> ExecutionState:
    try:
        return ExecutionState(value)
    except ValueError as error:
        raise ContractError(f"unknown execution state {value!r}") from error


def validate_transition(
    current: str | ExecutionState,
    target: str | ExecutionState,
    *,
    node_id: str = "<node>",
) -> ExecutionState:
    """Return the target state, or raise if the transition is not permitted."""

    source = coerce_state(current)
    destination = coerce_state(target)
    if destination not in ALLOWED_TRANSITIONS[source]:
        raise ContractError(
            f"node {node_id}: {source} cannot transition to {destination}"
        )
    return destination


def apply_manager_review(
    current: str | ExecutionState,
    verdict: str,
    *,
    node_id: str = "<node>",
    defects: list[str] | tuple[str, ...] = (),
    repair_instructions: list[str] | tuple[str, ...] = (),
    escalation: dict[str, object] | None = None,
) -> ExecutionState:
    """Apply a manager verdict to a node awaiting review.

    A `repair_required` verdict without a bounded defect and a repair instruction
    is not a review, it is a complaint. A `human_required` verdict without the
    unresolved question and the attempts already made leaves the next reader
    guessing.
    """

    source = coerce_state(current)
    if verdict not in MANAGER_VERDICTS:
        raise ContractError(
            f"unknown manager verdict {verdict!r}; expected one of {sorted(MANAGER_VERDICTS)}"
        )
    if source is not ExecutionState.AWAITING_REVIEW:
        raise ContractError(
            f"node {node_id}: a manager review applies to awaiting_review, not {source}"
        )
    if verdict == "repair_required":
        if not defects:
            raise ContractError(
                f"node {node_id}: repair_required needs at least one bounded defect"
            )
        if not repair_instructions:
            raise ContractError(
                f"node {node_id}: repair_required needs at least one repair instruction"
            )
    if verdict == "human_required":
        missing = [
            key
            for key in ("question", "attempts_made", "impacted_nodes")
            if not (escalation or {}).get(key)
        ]
        if missing:
            raise ContractError(
                f"node {node_id}: human_required escalation missing {', '.join(missing)}"
            )
    return validate_transition(source, VERDICT_TO_STATE[verdict], node_id=node_id)


def dependents(graph: ExecutionGraph) -> dict[str, list[str]]:
    """Map each node to the nodes that depend on it."""

    edges: dict[str, list[str]] = defaultdict(list)
    for node in graph.nodes:
        for dependency in node.depends_on:
            edges[dependency].append(node.id)
    return edges


def block_descendants(graph: ExecutionGraph, *, failed_node_id: str) -> set[str]:
    """Return the transitive dependents of a node, and nothing else.

    Siblings, cousins, and every other independent branch are absent from the
    result by construction. That is the point: an isolated failure must not stop
    work that does not depend on it.
    """

    nodes = graph.by_id()
    if failed_node_id not in nodes:
        raise ContractError(f"unknown node {failed_node_id}")

    edges = dependents(graph)
    blocked: set[str] = set()
    queue = deque(edges.get(failed_node_id, ()))
    while queue:
        node_id = queue.popleft()
        if node_id in blocked or node_id == failed_node_id:
            continue
        blocked.add(node_id)
        queue.extend(edges.get(node_id, ()))
    return blocked


@dataclass(frozen=True)
class Frontier:
    ready: tuple[str, ...]
    blocked: tuple[str, ...]
    awaiting_review: tuple[str, ...]
    human_required: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "ready": list(self.ready),
            "blocked": list(self.blocked),
            "awaiting_review": list(self.awaiting_review),
            "human_required": list(self.human_required),
        }


def compute_frontier(
    graph: ExecutionGraph, states: dict[str, str | ExecutionState]
) -> Frontier:
    """Derive the ready frontier from durable node states.

    A node is ready only when every dependency reached `completed`, which only a
    passing manager review can do. Nodes downstream of a `human_required` or
    `blocked` node are reported as blocked rather than ready, and everything else
    that is eligible keeps running.
    """

    nodes = graph.by_id()
    resolved = {
        node_id: coerce_state(states.get(node_id, ExecutionState.PENDING))
        for node_id in nodes
    }

    isolated: set[str] = set()
    for node_id, state in sorted(resolved.items()):
        if state in {ExecutionState.HUMAN_REQUIRED, ExecutionState.BLOCKED, ExecutionState.FAILED}:
            isolated |= block_descendants(graph, failed_node_id=node_id)

    ready: list[str] = []
    blocked: list[str] = []
    for node_id in sorted(nodes):
        state = resolved[node_id]
        if state in TERMINAL_STATES or state in {
            ExecutionState.RUNNING,
            ExecutionState.AWAITING_REVIEW,
            ExecutionState.HUMAN_REQUIRED,
        }:
            continue
        satisfied = all(
            resolved[dependency] in DEPENDENCY_SATISFYING_STATES
            for dependency in nodes[node_id].depends_on
        )
        if node_id in isolated or not satisfied:
            blocked.append(node_id)
        else:
            ready.append(node_id)

    return Frontier(
        ready=tuple(ready),
        blocked=tuple(blocked),
        awaiting_review=tuple(
            node_id
            for node_id in sorted(nodes)
            if resolved[node_id] is ExecutionState.AWAITING_REVIEW
        ),
        human_required=tuple(
            node_id
            for node_id in sorted(nodes)
            if resolved[node_id] is ExecutionState.HUMAN_REQUIRED
        ),
    )
