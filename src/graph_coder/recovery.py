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
    rows = connection.execute(
        """SELECT node_id FROM graph_nodes AS node
        WHERE node.role='atomic'
          AND node.status IN ('pending','ready')
          AND NOT EXISTS (
            SELECT 1 FROM graph_edges AS edge
            JOIN graph_nodes AS dependency
              ON dependency.graph_id=edge.graph_id
             AND dependency.node_id=edge.source_node_id
            WHERE edge.graph_id=node.graph_id
              AND edge.target_node_id=node.node_id
              AND dependency.status NOT IN ('completed','done')
          )
        ORDER BY node_id"""
    ).fetchall()
    return [row["node_id"] for row in rows]


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
        "recent_events": list(reversed(events)),
    }
