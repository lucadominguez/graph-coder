import pytest

from graph_coder.db import connect, migrate
from graph_coder.events import append_event
from graph_coder.recovery import recover


def seed(conn):
    conn.execute("INSERT INTO runs(id,goal) VALUES ('r1','goal')")
    conn.execute(
        """INSERT INTO tasks(id,run_id,content,role,status)
        VALUES ('t1','r1','code','coder','pending')"""
    )
    conn.execute(
        """INSERT INTO tasks(id,run_id,content,role,status)
        VALUES ('t2','r1','plan','planner','pending')"""
    )
    conn.execute(
        "INSERT INTO attempts(id,task_id,role,status) VALUES ('a1','t1','coder','in_flight')"
    )
    append_event(conn, "task.created", {"task_id": "t1", "role": "coder"}, role="coder")
    append_event(
        conn,
        "attempt.started",
        {"attempt_id": "a1", "task_id": "t1", "role": "coder"},
        role="coder",
    )


def test_restart_marks_inflight_interrupted_and_role_packet(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    seed(conn)
    packet = recover(conn, role="coder", event_limit=10)
    assert packet["interrupted_attempts"] == 1
    assert conn.execute("SELECT status FROM attempts WHERE id='a1'").fetchone()[0] == "interrupted"
    assert packet["role"] == "coder"
    assert [t["id"] for t in packet["tasks"]] == ["t1"]
    assert any(e["type"] == "attempt.interrupted" for e in packet["recent_events"])
    assert recover(conn, role="coder")["interrupted_attempts"] == 0
    conn.close()


def test_recovery_refuses_tampered_chain(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    seed(conn)
    conn.execute("UPDATE events SET payload_json='{}' WHERE sequence=1")
    with pytest.raises(ValueError, match="verification failed"):
        recover(conn, role="coder")
    conn.close()


def test_recovery_reopens_missing_evidence_and_reports_ready_frontier_and_drift(
    tmp_path, monkeypatch
):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    conn.execute(
        """INSERT INTO plan_versions(
            plan_id,version,content_hash,repository_commit,readiness,approved
        ) VALUES ('P-demo',1,'hash','old-commit','implementation-ready',1)"""
    )
    conn.execute(
        """INSERT INTO units(plan_id,unit_id,semantic_hash,objective,status)
        VALUES ('P-demo','U-missing','one','missing evidence','completed')"""
    )
    conn.execute(
        """INSERT INTO units(
            plan_id,unit_id,semantic_hash,objective,status,evidence_hash
        ) VALUES ('P-demo','U-proven','two','has evidence','completed','proof')"""
    )
    graph_nodes = [
        ("G-demo", "Director", "integrate", "composite", "pending"),
        ("G-demo", "U-first", "implement", "atomic", "pending"),
        ("G-demo", "U-second", "verify", "atomic", "pending"),
    ]
    conn.executemany(
        """INSERT INTO graph_nodes(graph_id,node_id,node_type,role,status)
        VALUES (?,?,?,?,?)""",
        graph_nodes,
    )
    conn.execute(
        """INSERT INTO graph_edges(graph_id,source_node_id,target_node_id)
        VALUES ('G-demo','U-first','U-second')"""
    )
    append_event(conn, "plan.snapshotted", {"version": 1}, plan_id="P-demo", role="Director")
    monkeypatch.setattr(
        "graph_coder.recovery.inspect_worktree",
        lambda root: {"commit": "new-commit", "status": [], "root": str(root)},
    )

    packet = recover(conn, role="Director", repository_root=tmp_path)

    assert packet["reopened_units"] == ["U-missing"]
    assert packet["ready_frontier"] == ["U-first"]
    assert packet["commit_mismatches"] == ["P-demo"]
    statuses = dict(conn.execute("SELECT unit_id,status FROM units"))
    assert statuses == {"U-missing": "reopened", "U-proven": "completed"}
    conn.close()
