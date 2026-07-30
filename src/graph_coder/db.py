"""SQLite schema, migrations, and transaction helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        root TEXT NOT NULL UNIQUE,
        name TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
        plan_id TEXT,
        goal TEXT,
        lifecycle_phase TEXT NOT NULL DEFAULT 'INTAKE',
        status TEXT NOT NULL DEFAULT 'active',
        budget_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS plan_versions (
        plan_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        source_path TEXT,
        snapshot_path TEXT,
        repository_commit TEXT,
        readiness TEXT NOT NULL,
        approved INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        PRIMARY KEY (plan_id, version),
        UNIQUE (plan_id, content_hash)
    )""",
    """CREATE TABLE IF NOT EXISTS requirements (
        plan_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        unit_ids_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (plan_id, requirement_id)
    )""",
    """CREATE TABLE IF NOT EXISTS units (
        plan_id TEXT NOT NULL,
        unit_id TEXT NOT NULL,
        semantic_hash TEXT NOT NULL,
        objective TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        requirement_ids_json TEXT NOT NULL DEFAULT '[]',
        write_scope_json TEXT NOT NULL DEFAULT '[]',
        evidence_hash TEXT,
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        PRIMARY KEY (plan_id, unit_id)
    )""",
    """CREATE TABLE IF NOT EXISTS graph_nodes (
        graph_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        node_type TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        failure_domain TEXT NOT NULL DEFAULT 'node',
        write_scope_json TEXT NOT NULL DEFAULT '[]',
        semantic_hash TEXT,
        data_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (graph_id, node_id)
    )""",
    """CREATE TABLE IF NOT EXISTS graph_edges (
        graph_id TEXT NOT NULL,
        source_node_id TEXT NOT NULL,
        target_node_id TEXT NOT NULL,
        artifact_type TEXT,
        PRIMARY KEY (graph_id, source_node_id, target_node_id)
    )""",
    """CREATE TABLE IF NOT EXISTS routes (
        plan_id TEXT NOT NULL,
        unit_id TEXT NOT NULL,
        primary_model TEXT NOT NULL,
        primary_provider TEXT,
        fallback_model TEXT,
        fallback_provider TEXT,
        source_hash TEXT NOT NULL,
        explanation_json TEXT NOT NULL,
        data_freshness TEXT,
        expected_passing_cost REAL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        PRIMARY KEY (plan_id, unit_id)
    )""",
    """CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'idle',
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        parent_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
        node_id TEXT,
        unit_id TEXT,
        role TEXT,
        content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS attempts (
        id TEXT PRIMARY KEY,
        run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
        task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
        node_id TEXT,
        unit_id TEXT,
        agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
        role TEXT NOT NULL,
        model_id TEXT,
        provider_id TEXT,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        heartbeat_at TEXT,
        finished_at TEXT,
        failure_class TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        schema_version TEXT NOT NULL DEFAULT 'agent-planning-system/v1',
        event_id TEXT NOT NULL UNIQUE,
        idempotency_key TEXT UNIQUE,
        run_id TEXT,
        plan_id TEXT,
        node_id TEXT,
        unit_id TEXT,
        attempt_id TEXT,
        actor_role TEXT,
        model_receipt TEXT,
        event_type TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        repository_commit TEXT,
        worktree TEXT,
        payload_json TEXT NOT NULL,
        artifact_hashes_json TEXT NOT NULL DEFAULT '[]',
        prev_hash TEXT NOT NULL,
        event_hash TEXT NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY,
        run_id TEXT,
        plan_id TEXT,
        node_id TEXT,
        unit_id TEXT,
        artifact_type TEXT NOT NULL,
        path TEXT,
        content_hash TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS reviews (
        id TEXT PRIMARY KEY,
        plan_id TEXT,
        node_id TEXT,
        unit_id TEXT,
        reviewer_role TEXT NOT NULL,
        model_receipt TEXT,
        severity TEXT,
        status TEXT NOT NULL,
        defect_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS decisions (
        id TEXT PRIMARY KEY,
        plan_id TEXT,
        decision_class TEXT NOT NULL,
        authority TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS escalations (
        id TEXT PRIMARY KEY,
        run_id TEXT,
        node_id TEXT,
        status TEXT NOT NULL,
        reason TEXT NOT NULL,
        options_json TEXT NOT NULL DEFAULT '[]',
        resolution_json TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        resolved_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS model_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        task_category TEXT NOT NULL,
        stack TEXT,
        risk TEXT,
        complexity TEXT,
        verified INTEGER NOT NULL DEFAULT 0,
        passed INTEGER NOT NULL,
        attempt_cost REAL,
        latency_ms REAL,
        observed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
    """CREATE TABLE IF NOT EXISTS projections (
        name TEXT PRIMARY KEY,
        version INTEGER NOT NULL,
        data_json TEXT NOT NULL,
        updated_sequence INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""",
]


def connect(path: str | Path, busy_timeout_ms: int = 5000) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=busy_timeout_ms / 1000, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        for statement in SCHEMA:
            connection.execute(statement)
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
            (SCHEMA_VERSION,),
        )


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except Exception:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")
