import sqlite3

import pytest

from graph_coder.db import connect, migrate, transaction


def test_migration_pragmas_and_core_tables(tmp_path):
    conn = connect(tmp_path / "graph-coder.db", busy_timeout_ms=3210)
    migrate(conn)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 3210
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "schema_migrations",
        "projects",
        "runs",
        "plan_versions",
        "requirements",
        "units",
        "graph_nodes",
        "graph_edges",
        "routes",
        "agents",
        "tasks",
        "attempts",
        "events",
        "artifacts",
        "reviews",
        "decisions",
        "escalations",
        "model_history",
        "projections",
    } <= tables
    assert conn.execute("SELECT version FROM schema_migrations").fetchone()[0] == 1
    conn.close()


REQUIRED_CORE_TABLES = {
    "schema_migrations",
    "projects",
    "runs",
    "plan_versions",
    "requirements",
    "units",
    "graph_nodes",
    "graph_edges",
    "routes",
    "agents",
    "tasks",
    "attempts",
    "events",
    "artifacts",
    "reviews",
    "decisions",
    "escalations",
    "model_history",
    "projections",
}


def test_all_design_contract_core_tables_exist(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = REQUIRED_CORE_TABLES - tables
    assert not missing, f"design-contract core tables missing from schema: {sorted(missing)}"


def test_migrate_is_idempotent_and_preserves_data(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    conn.execute("INSERT INTO runs(id,goal) VALUES ('r1','goal')")
    migrate(conn)
    assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1


def test_ledger_and_plan_version_uniqueness_constraints(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    conn.execute(
        "INSERT INTO plan_versions(plan_id,version,content_hash,readiness) "
        "VALUES ('P',1,'h1','implementation-ready')"
    )
    with pytest.raises(Exception, match=r"UNIQUE|unique"):
        conn.execute(
            "INSERT INTO plan_versions(plan_id,version,content_hash,readiness) "
            "VALUES ('P',1,'h2','implementation-ready')"
        )
    with pytest.raises(Exception, match=r"UNIQUE|unique"):
        conn.execute(
            "INSERT INTO plan_versions(plan_id,version,content_hash,readiness) "
            "VALUES ('P',2,'h1','implementation-ready')"
        )


def test_events_table_supports_hash_linked_ledger_columns(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    assert {
        "sequence",
        "schema_version",
        "event_id",
        "idempotency_key",
        "actor_role",
        "model_receipt",
        "event_type",
        "timestamp_utc",
        "repository_commit",
        "worktree",
        "payload_json",
        "artifact_hashes_json",
        "prev_hash",
        "event_hash",
    } <= columns


def test_transaction_rolls_back_and_foreign_keys(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    with pytest.raises(RuntimeError), transaction(conn):
        conn.execute("INSERT INTO runs(id) VALUES ('r1')")
        raise RuntimeError("boom")
    assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tasks(id,run_id,content) VALUES ('t1','missing','x')")
    conn.close()
