from graph_coder.db import connect, migrate
from graph_coder.events import append_event, rebuild_projections, verify_chain


def test_append_hash_chain_idempotency_and_redaction(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    first = append_event(
        conn,
        "task.created",
        {"task_id": "t1", "password": "secret", "role": "coder"},
        idempotency_key="k1",
        role="coder",
    )
    duplicate = append_event(
        conn, "task.created", {"task_id": "DIFFERENT"}, idempotency_key="k1", role="coder"
    )
    second = append_event(conn, "task.updated", {"task_id": "t1", "status": "done"}, role="coder")
    assert first.sequence == duplicate.sequence == 1
    assert second.sequence == 2
    assert second.prev_hash == first.event_hash
    stored = conn.execute("SELECT payload_json FROM events WHERE sequence=1").fetchone()[0]
    assert "secret" not in stored
    assert "[REDACTED]" in stored
    assert verify_chain(conn) == (True, None)
    conn.close()


def test_tamper_detection_and_projection_rebuild(tmp_path):
    conn = connect(tmp_path / "graph-coder.db")
    migrate(conn)
    append_event(conn, "task.created", {"task_id": "t1", "role": "planner"}, role="planner")
    append_event(
        conn,
        "attempt.started",
        {"attempt_id": "a1", "task_id": "t1", "role": "planner"},
        role="planner",
    )
    state = rebuild_projections(conn)
    assert state["tasks"]["t1"]["status"] == "pending"
    assert state["attempts"]["a1"]["status"] == "in_flight"
    conn.execute("UPDATE events SET payload_json='{}' WHERE sequence=1")
    ok, error = verify_chain(conn)
    assert not ok
    assert "hash mismatch" in error
    conn.close()
