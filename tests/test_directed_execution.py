"""Directed execution: manager review gates completion, failures stay local."""

from __future__ import annotations

import json

import pytest

from graph_coder.db import connect, migrate, transaction
from graph_coder.errors import ContractError
from graph_coder.execution import (
    EXECUTION_EVENT_TYPES,
    ExecutionState,
    apply_manager_review,
    block_descendants,
    compute_frontier,
    validate_transition,
)
from graph_coder.graph import ExecutionGraph, GraphNode
from graph_coder.recovery import human_required_nodes, ready_frontier, resume_human_required


def graph() -> ExecutionGraph:
    """Director, two managers, and two independent branches.

    Director
    ├── manager-a  ->  a1 -> a2
    └── manager-b  ->  b1 -> b2
    """

    return ExecutionGraph(
        nodes=[
            GraphNode(
                id="Director",
                kind="explore",
                role="composite",
                authority="advisory_only",
                title="Director",
                children=["manager-a", "manager-b"],
            ),
            GraphNode(
                id="manager-a",
                kind="manage",
                role="composite",
                authority="advisory_only",
                title="Manager A",
                depends_on=["Director"],
                review_owner="Director",
                children=["a1", "a2"],
            ),
            GraphNode(
                id="manager-b",
                kind="manage",
                role="composite",
                authority="advisory_only",
                title="Manager B",
                depends_on=["Director"],
                review_owner="Director",
                children=["b1", "b2"],
            ),
            GraphNode(
                id="a1",
                kind="implement",
                title="A1",
                depends_on=["manager-a"],
                write_scopes=["src/a1.py"],
                review_owner="manager-a",
            ),
            GraphNode(
                id="a2",
                kind="implement",
                title="A2",
                depends_on=["a1"],
                write_scopes=["src/a2.py"],
                review_owner="manager-a",
            ),
            GraphNode(
                id="b1",
                kind="implement",
                title="B1",
                depends_on=["manager-b"],
                write_scopes=["src/b1.py"],
                review_owner="manager-b",
            ),
            GraphNode(
                id="b2",
                kind="implement",
                title="B2",
                depends_on=["b1"],
                write_scopes=["src/b2.py"],
                review_owner="manager-b",
            ),
        ]
    )


def states(**overrides: str) -> dict[str, str]:
    base = {
        "Director": "completed",
        "manager-a": "completed",
        "manager-b": "completed",
        "a1": "pending",
        "a2": "pending",
        "b1": "pending",
        "b2": "pending",
    }
    base.update(overrides)
    return base


# --- transitions -------------------------------------------------------------


def test_the_happy_path_runs_through_review() -> None:
    state = validate_transition(ExecutionState.PENDING, "ready")
    state = validate_transition(state, "running")
    state = validate_transition(state, "awaiting_review")
    assert apply_manager_review(state, "pass") is ExecutionState.COMPLETED


def test_a_worker_cannot_complete_itself() -> None:
    with pytest.raises(ContractError, match="cannot transition"):
        validate_transition(ExecutionState.RUNNING, "completed", node_id="a1")


def test_repair_returns_the_node_to_a_worker() -> None:
    state = apply_manager_review(
        ExecutionState.AWAITING_REVIEW,
        "repair_required",
        defects=["write scope violated"],
        repair_instructions=["revert src/other.py and re-run the green command"],
    )
    assert state is ExecutionState.REPAIR_REQUIRED
    assert validate_transition(state, "running") is ExecutionState.RUNNING


def test_repair_required_needs_a_defect_and_an_instruction() -> None:
    with pytest.raises(ContractError, match="bounded defect"):
        apply_manager_review(ExecutionState.AWAITING_REVIEW, "repair_required")
    with pytest.raises(ContractError, match="repair instruction"):
        apply_manager_review(ExecutionState.AWAITING_REVIEW, "repair_required", defects=["broken"])


def test_human_required_needs_the_question_and_the_attempts() -> None:
    with pytest.raises(ContractError, match="question"):
        apply_manager_review(ExecutionState.AWAITING_REVIEW, "human_required", escalation={})

    state = apply_manager_review(
        ExecutionState.AWAITING_REVIEW,
        "human_required",
        escalation={
            "question": "which interface owns retries?",
            "attempts_made": ["advice", "same-worker repair", "fallback worker"],
            "impacted_nodes": ["a2"],
        },
    )
    assert state is ExecutionState.HUMAN_REQUIRED


def test_review_only_applies_to_a_node_awaiting_review() -> None:
    with pytest.raises(ContractError, match="awaiting_review"):
        apply_manager_review(ExecutionState.RUNNING, "pass")


def test_unknown_verdicts_and_states_are_rejected() -> None:
    with pytest.raises(ContractError, match="verdict"):
        apply_manager_review(ExecutionState.AWAITING_REVIEW, "looks-fine-to-me")
    with pytest.raises(ContractError, match="unknown execution state"):
        validate_transition("nearly-done", "completed")


def test_a_human_decision_reopens_the_branch() -> None:
    assert validate_transition(ExecutionState.HUMAN_REQUIRED, "ready") is ExecutionState.READY


# --- failure isolation -------------------------------------------------------


def test_block_descendants_returns_only_transitive_dependents() -> None:
    assert block_descendants(graph(), failed_node_id="a1") == {"a2"}
    assert block_descendants(graph(), failed_node_id="b1") == {"b2"}
    assert block_descendants(graph(), failed_node_id="a2") == set()


def test_block_descendants_never_touches_an_independent_branch() -> None:
    blocked = block_descendants(graph(), failed_node_id="manager-a")
    assert blocked == {"a1", "a2"}
    assert not blocked & {"b1", "b2", "manager-b"}


def test_block_descendants_rejects_an_unknown_node() -> None:
    with pytest.raises(ContractError, match="unknown node"):
        block_descendants(graph(), failed_node_id="ghost")


# --- frontier ----------------------------------------------------------------


def test_dependencies_unlock_only_after_a_passing_review() -> None:
    awaiting = compute_frontier(graph(), states(a1="awaiting_review"))
    assert "a2" not in awaiting.ready
    assert "a1" in awaiting.awaiting_review

    reviewed = compute_frontier(graph(), states(a1="completed"))
    assert "a2" in reviewed.ready


def test_a_human_required_branch_blocks_only_its_descendants() -> None:
    frontier = compute_frontier(graph(), states(a1="human_required"))

    assert "a1" in frontier.human_required
    assert "a2" in frontier.blocked
    # The whole point: the other branch is still runnable.
    assert "b1" in frontier.ready
    assert "b2" not in frontier.ready


def test_independent_work_continues_after_an_isolated_failure() -> None:
    frontier = compute_frontier(graph(), states(a1="human_required", b1="completed"))
    assert "b2" in frontier.ready
    assert set(frontier.ready) & {"a1", "a2"} == set()


def test_repair_required_nodes_are_ready_for_a_worker_again() -> None:
    frontier = compute_frontier(graph(), states(a1="repair_required"))
    assert "a1" in frontier.ready


def test_running_and_completed_nodes_are_not_redispatched() -> None:
    frontier = compute_frontier(graph(), states(a1="completed", a2="running", b1="cancelled"))
    assert "a1" not in frontier.ready
    assert "a2" not in frontier.ready
    assert "b1" not in frontier.ready


def test_frontier_is_deterministic_and_serializable() -> None:
    first = compute_frontier(graph(), states(a1="human_required"))
    second = compute_frontier(graph(), states(a1="human_required"))
    assert first == second
    assert set(first.to_dict()) == {"ready", "blocked", "awaiting_review", "human_required"}


# --- events ------------------------------------------------------------------


def durable_graph(tmp_path):
    """Persist the two-branch graph with a1 stuck on a human decision."""

    connection = connect(tmp_path / "graph-coder.db")
    migrate(connection)
    rows = [
        ("g1", "Director", "explore", "composite", "completed"),
        ("g1", "manager-a", "manage", "composite", "completed"),
        ("g1", "manager-b", "manage", "composite", "completed"),
        ("g1", "a1", "implement", "atomic", "human_required"),
        ("g1", "a2", "implement", "atomic", "pending"),
        ("g1", "b1", "implement", "atomic", "completed"),
        ("g1", "b2", "implement", "atomic", "pending"),
    ]
    edges = [
        ("g1", "manager-a", "a1"),
        ("g1", "a1", "a2"),
        ("g1", "manager-b", "b1"),
        ("g1", "b1", "b2"),
    ]
    with transaction(connection):
        for graph_id, node_id, node_type, role, status in rows:
            connection.execute(
                """INSERT INTO graph_nodes(graph_id,node_id,node_type,role,status,data_json)
                VALUES (?,?,?,?,?,'{}')""",
                (graph_id, node_id, node_type, role, status),
            )
        for graph_id, source, target in edges:
            connection.execute(
                """INSERT INTO graph_edges(graph_id,source_node_id,target_node_id)
                VALUES (?,?,?)""",
                (graph_id, source, target),
            )
    return connection


def test_durable_frontier_excludes_descendants_of_a_human_required_node(tmp_path) -> None:
    connection = durable_graph(tmp_path)
    try:
        frontier = ready_frontier(connection)
        # b2's dependency passed review, so it runs. a2's did not.
        assert "b2" in frontier
        assert "a2" not in frontier
        assert [item["node_id"] for item in human_required_nodes(connection)] == ["a1"]
    finally:
        connection.close()


def test_resume_records_the_decision_and_preserves_failure_evidence(tmp_path) -> None:
    connection = durable_graph(tmp_path)
    try:
        result = resume_human_required(
            connection,
            node_id="a1",
            decision="interface owner is the manager; retries stay in the worker",
            decided_by="luca",
        )

        assert result["resumed_to"] == "ready"
        assert "a1" in result["ready_frontier"]
        assert result["human_required"] == []
        assert result["event_sequence"] >= 1

        stored = connection.execute(
            "SELECT status,data_json FROM graph_nodes WHERE node_id='a1'"
        ).fetchone()
        assert stored["status"] == "ready"
        history = json.loads(stored["data_json"])["human_decisions"]
        assert len(history) == 1
        # The record of why it stopped survives the resume.
        assert history[0]["previous_status"] == "human_required"
        assert history[0]["decided_by"] == "luca"

        events = [
            row["event_type"]
            for row in connection.execute("SELECT event_type FROM events ORDER BY sequence")
        ]
        assert "branch.resumed" in events
    finally:
        connection.close()


def test_resume_refuses_a_node_that_is_not_human_required(tmp_path) -> None:
    connection = durable_graph(tmp_path)
    try:
        with pytest.raises(ValueError, match="not human_required"):
            resume_human_required(connection, node_id="b1", decision="carry on")
        with pytest.raises(ValueError, match="unknown node"):
            resume_human_required(connection, node_id="ghost", decision="carry on")
    finally:
        connection.close()


def test_the_execution_event_vocabulary_is_complete() -> None:
    for event in (
        "worker.submitted",
        "manager.review_requested",
        "manager.review_passed",
        "manager.repair_requested",
        "manager.advice_requested",
        "manager.escalated",
        "branch.human_required",
        "branch.resumed",
    ):
        assert event in EXECUTION_EVENT_TYPES, event
