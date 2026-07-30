"""Crash recovery and role-specific durable context reconstruction."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .context import inspect_worktree
from .db import transaction
from .events import append_event, rebuild_projections, verify_chain

IN_FLIGHT = ("running", "in_flight", "started")


def mark_interrupted_on_startup(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        f"SELECT id,task_id,node_id,unit_id,role FROM attempts "
        f"WHERE status IN ({','.join('?' for _ in IN_FLIGHT)})",
        IN_FLIGHT,
    ).fetchall()
    with transaction(connection):
        for row in rows:
            connection.execute(
                """UPDATE attempts
                SET status='interrupted',
                    finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id=?""",
                (row["id"],),
            )
    for row in rows:
        append_event(
            connection,
            "attempt.interrupted",
            {
                "attempt_id": row["id"],
                "task_id": row["task_id"],
                "node_id": row["node_id"],
                "unit_id": row["unit_id"],
                "role": row["role"],
                "reason": "restart",
            },
            idempotency_key=f"restart-interrupt:{row['id']}",
            role=row["role"],
            node_id=row["node_id"],
            unit_id=row["unit_id"],
            attempt_id=row["id"],
        )
    return len(rows)


def reopen_unverified_completed_units(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """SELECT plan_id,unit_id FROM units
        WHERE status IN ('completed','done') AND evidence_hash IS NULL"""
    ).fetchall()
    with transaction(connection):
        for row in rows:
            connection.execute(
                """UPDATE units
                SET status='reopened',
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE plan_id=? AND unit_id=?""",
                (row["plan_id"], row["unit_id"]),
            )
    for row in rows:
        append_event(
            connection,
            "unit.reopened",
            {"reason": "completion evidence missing after recovery"},
            idempotency_key=f"recovery-reopen:{row['plan_id']}:{row['unit_id']}",
            role="Director",
            plan_id=row["plan_id"],
            unit_id=row["unit_id"],
        )
    return [row["unit_id"] for row in rows]


def ready_frontier(connection: sqlite3.Connection) -> list[str]:
    """Nodes a worker may be dispatched to right now.

    A dependency counts as satisfied only in `completed`, which a node reaches
    only through a passing manager review. `done` is deliberately not accepted:
    it was the APS spelling for a self-declared finish, and honouring it here
    would let a worker unlock its own dependents.

    `repair_required` nodes are dispatchable again, because a manager returned
    them to a worker with bounded instructions. `blocked` and `human_required`
    nodes are not, and neither is anything downstream of them.
    """

    rows = connection.execute(
        """SELECT node_id FROM graph_nodes AS node
        WHERE node.role='atomic'
          AND node.status IN ('pending','ready','repair_required')
          AND NOT EXISTS (
            SELECT 1 FROM graph_edges AS edge
            JOIN graph_nodes AS dependency
              ON dependency.graph_id=edge.graph_id
             AND dependency.node_id=edge.source_node_id
            WHERE edge.graph_id=node.graph_id
              AND edge.target_node_id=node.node_id
              AND dependency.status <> 'completed'
          )
        ORDER BY node_id"""
    ).fetchall()
    return [row["node_id"] for row in rows]


def human_required_nodes(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Branches waiting on a person, with the evidence needed to decide."""

    return [
        dict(row)
        for row in connection.execute(
            """SELECT graph_id,node_id,node_type,failure_domain,data_json
            FROM graph_nodes WHERE status='human_required' ORDER BY node_id"""
        ).fetchall()
    ]


def resume_human_required(
    connection: sqlite3.Connection,
    *,
    node_id: str,
    decision: str,
    decided_by: str = "user",
    target_status: str = "ready",
) -> dict[str, Any]:
    """Record a human decision and recompute the frontier.

    The prior failure evidence is preserved: the decision is appended to the
    node's durable record rather than replacing it, so a later reader can still
    see what was attempted and why it stopped.
    """

    row = connection.execute(
        "SELECT graph_id,node_id,status,data_json FROM graph_nodes WHERE node_id=?",
        (node_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown node {node_id}")
    if row["status"] != "human_required":
        raise ValueError(
            f"node {node_id} is {row['status']!r}, not human_required; nothing to resume"
        )
    if target_status not in {"ready", "cancelled", "failed"}:
        raise ValueError(
            f"unsupported resume target {target_status!r}; expected ready, cancelled, or failed"
        )

    data = json.loads(row["data_json"] or "{}")
    history = list(data.get("human_decisions", []))
    history.append(
        {
            "decision": decision,
            "decided_by": decided_by,
            "resumed_to": target_status,
            "previous_status": row["status"],
        }
    )
    data["human_decisions"] = history

    with transaction(connection):
        connection.execute(
            "UPDATE graph_nodes SET status=?, data_json=? WHERE graph_id=? AND node_id=?",
            (target_status, json.dumps(data, sort_keys=True), row["graph_id"], node_id),
        )

    event = append_event(
        connection,
        "branch.resumed",
        {
            "node_id": node_id,
            "decision": decision,
            "decided_by": decided_by,
            "resumed_to": target_status,
            "attempts_preserved": len(history),
        },
        idempotency_key=f"branch-resume:{node_id}:{len(history)}",
        role="Director",
        node_id=node_id,
    )
    return {
        "node_id": node_id,
        "resumed_to": target_status,
        "decision": decision,
        "event_sequence": event.sequence,
        "ready_frontier": ready_frontier(connection),
        "human_required": [item["node_id"] for item in human_required_nodes(connection)],
    }


def recover(
    connection: sqlite3.Connection,
    *,
    role: str,
    event_limit: int = 20,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    ok, error = verify_chain(connection)
    if not ok:
        raise ValueError(f"event ledger verification failed: {error}")
    interrupted = mark_interrupted_on_startup(connection)
    reopened = reopen_unverified_completed_units(connection)
    state = rebuild_projections(connection)
    events = [
        {
            "sequence": row["sequence"],
            "type": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "event_hash": row["event_hash"],
        }
        for row in connection.execute(
            """SELECT * FROM events
            WHERE actor_role IS NULL OR actor_role=?
            ORDER BY sequence DESC LIMIT ?""",
            (role, event_limit),
        ).fetchall()
    ]
    tasks = [
        dict(row)
        for row in connection.execute(
            """SELECT id,node_id,unit_id,content,status,role FROM tasks
            WHERE role IS NULL OR role=? ORDER BY updated_at DESC LIMIT 20""",
            (role,),
        ).fetchall()
    ]
    latest_plans = [
        dict(row)
        for row in connection.execute(
            """SELECT plan_id,version,content_hash,repository_commit,
                      readiness,approved,snapshot_path
            FROM plan_versions
            WHERE (plan_id,version) IN (
                SELECT plan_id,MAX(version) FROM plan_versions GROUP BY plan_id
            ) ORDER BY plan_id"""
        ).fetchall()
    ]
    repository = inspect_worktree(repository_root) if repository_root is not None else None
    commit_mismatches = []
    if repository and repository.get("commit"):
        commit_mismatches = [
            plan["plan_id"]
            for plan in latest_plans
            if plan["repository_commit"] and plan["repository_commit"] != repository["commit"]
        ]
    return {
        "role": role,
        "interrupted_attempts": interrupted,
        "reopened_units": reopened,
        "last_sequence": state["last_sequence"],
        "ledger_valid": True,
        "tasks": tasks,
        "ready_frontier": ready_frontier(connection),
        "latest_plans": latest_plans,
        "repository": repository,
        "commit_mismatches": commit_mismatches,
        "human_required": human_required_nodes(connection),
        "recent_events": list(reversed(events)),
    }
