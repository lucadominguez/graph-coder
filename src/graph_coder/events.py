"""Hash-linked append-only event ledger and derived projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import atomic_write
from .db import transaction
from .redaction import redact

CONTRACT_VERSION = "graph-coder/v1"
GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class EventRecord:
    sequence: int
    event_id: str
    event_type: str
    payload: dict[str, Any]
    prev_hash: str
    event_hash: str
    idempotency_key: str | None = None
    role: str | None = None
    timestamp_utc: str = ""
    run_id: str | None = None
    plan_id: str | None = None
    node_id: str | None = None
    unit_id: str | None = None
    attempt_id: str | None = None
    model_receipt: str | None = None
    repository_commit: str | None = None
    worktree: str | None = None
    artifact_hashes: tuple[str, ...] = ()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_payload(row: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(row).encode("utf-8")).hexdigest()


def compute_hash(row: sqlite3.Row | dict[str, Any]) -> str:
    mapping = dict(row)
    return _hash_payload(
        {
            "sequence": mapping["sequence"],
            "schema_version": mapping["schema_version"],
            "event_id": mapping["event_id"],
            "idempotency_key": mapping.get("idempotency_key"),
            "run_id": mapping.get("run_id"),
            "plan_id": mapping.get("plan_id"),
            "node_id": mapping.get("node_id"),
            "unit_id": mapping.get("unit_id"),
            "attempt_id": mapping.get("attempt_id"),
            "actor_role": mapping.get("actor_role"),
            "model_receipt": mapping.get("model_receipt"),
            "event_type": mapping["event_type"],
            "timestamp_utc": mapping["timestamp_utc"],
            "repository_commit": mapping.get("repository_commit"),
            "worktree": mapping.get("worktree"),
            "payload": json.loads(mapping["payload_json"]),
            "artifact_hashes": json.loads(mapping["artifact_hashes_json"]),
            "prev_hash": mapping["prev_hash"],
        }
    )


def append_event(
    connection: sqlite3.Connection,
    event_type: str,
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    role: str | None = None,
    run_id: str | None = None,
    plan_id: str | None = None,
    node_id: str | None = None,
    unit_id: str | None = None,
    attempt_id: str | None = None,
    model_receipt: str | None = None,
    repository_commit: str | None = None,
    worktree: str | None = None,
    artifact_hashes: list[str] | tuple[str, ...] = (),
) -> EventRecord:
    clean_payload = redact(payload)
    clean_hashes = tuple(str(item) for item in redact(list(artifact_hashes)))
    payload_json = canonical_json(clean_payload)
    hashes_json = canonical_json(clean_hashes)
    event_id = str(uuid.uuid4())
    timestamp_utc = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    with transaction(connection):
        if idempotency_key:
            existing = connection.execute(
                "SELECT * FROM events WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing:
                return _row_to_event(existing)
        last = connection.execute(
            "SELECT sequence,event_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        prev_hash = last["event_hash"] if last else GENESIS_HASH
        cursor = connection.execute(
            """INSERT INTO events(
                schema_version,event_id,idempotency_key,run_id,plan_id,node_id,unit_id,
                attempt_id,actor_role,model_receipt,event_type,timestamp_utc,
                repository_commit,worktree,payload_json,artifact_hashes_json,prev_hash,event_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                CONTRACT_VERSION,
                event_id,
                idempotency_key,
                run_id,
                plan_id,
                node_id,
                unit_id,
                attempt_id,
                role,
                model_receipt,
                event_type,
                timestamp_utc,
                repository_commit,
                worktree,
                payload_json,
                hashes_json,
                prev_hash,
                "pending",
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.DatabaseError("event insert did not return a sequence")
        sequence = int(cursor.lastrowid)
        pending = connection.execute(
            "SELECT * FROM events WHERE sequence=?", (sequence,)
        ).fetchone()
        event_hash = compute_hash(pending)
        connection.execute(
            "UPDATE events SET event_hash=? WHERE sequence=?", (event_hash, sequence)
        )
    return EventRecord(
        sequence=sequence,
        event_id=event_id,
        event_type=event_type,
        payload=clean_payload,
        prev_hash=prev_hash,
        event_hash=event_hash,
        idempotency_key=idempotency_key,
        role=role,
        timestamp_utc=timestamp_utc,
        run_id=run_id,
        plan_id=plan_id,
        node_id=node_id,
        unit_id=unit_id,
        attempt_id=attempt_id,
        model_receipt=model_receipt,
        repository_commit=repository_commit,
        worktree=worktree,
        artifact_hashes=clean_hashes,
    )


def verify_chain(connection: sqlite3.Connection) -> tuple[bool, str | None]:
    previous = GENESIS_HASH
    expected_sequence = 1
    for row in connection.execute("SELECT * FROM events ORDER BY sequence"):
        if row["sequence"] != expected_sequence:
            return False, f"non-monotonic sequence at {row['sequence']}"
        if row["prev_hash"] != previous:
            return False, f"broken previous hash at {row['sequence']}"
        expected = compute_hash(row)
        if row["event_hash"] != expected:
            return False, f"hash mismatch at {row['sequence']}"
        previous = row["event_hash"]
        expected_sequence += 1
    return True, None


def rebuild_projections(connection: sqlite3.Connection) -> dict[str, Any]:
    state: dict[str, Any] = {
        "tasks": {},
        "attempts": {},
        "plans": {},
        "routes": {},
        "escalations": {},
        "last_sequence": 0,
    }
    for row in connection.execute("SELECT * FROM events ORDER BY sequence"):
        payload = json.loads(row["payload_json"])
        event_type = row["event_type"]
        if event_type == "task.created":
            state["tasks"][payload["task_id"]] = {
                "status": payload.get("status", "pending"),
                "role": payload.get("role"),
            }
        elif event_type == "task.updated" and payload.get("task_id") in state["tasks"]:
            state["tasks"][payload["task_id"]].update(payload)
        elif event_type == "attempt.started":
            state["attempts"][payload["attempt_id"]] = {
                "status": "in_flight",
                "role": payload.get("role"),
                "task_id": payload.get("task_id"),
            }
        elif event_type == "attempt.interrupted" and payload.get("attempt_id") in state["attempts"]:
            state["attempts"][payload["attempt_id"]]["status"] = "interrupted"
        elif event_type.startswith("plan.") and row["plan_id"]:
            state["plans"][row["plan_id"]] = {
                "event": event_type,
                "sequence": row["sequence"],
                **payload,
            }
        elif event_type == "route.changed" and row["unit_id"]:
            state["routes"][row["unit_id"]] = payload
        elif event_type.startswith("escalation."):
            escalation_id = payload.get("escalation_id")
            if escalation_id:
                state["escalations"][escalation_id] = payload
        state["last_sequence"] = row["sequence"]
    connection.execute(
        """INSERT OR REPLACE INTO projections(name,version,data_json,updated_sequence)
        VALUES (?,?,?,?)""",
        ("control", 1, canonical_json(state), state["last_sequence"]),
    )
    return state


def write_jsonl_projection(connection: sqlite3.Connection, path: str | Path) -> None:
    lines = []
    for row in connection.execute("SELECT * FROM events ORDER BY sequence"):
        event = _row_to_event(row)
        lines.append(canonical_json(event.__dict__))
    atomic_write(path, "\n".join(lines) + ("\n" if lines else ""))


def _row_to_event(row: sqlite3.Row) -> EventRecord:
    return EventRecord(
        sequence=row["sequence"],
        event_id=row["event_id"],
        event_type=row["event_type"],
        payload=json.loads(row["payload_json"]),
        prev_hash=row["prev_hash"],
        event_hash=row["event_hash"],
        idempotency_key=row["idempotency_key"],
        role=row["actor_role"],
        timestamp_utc=row["timestamp_utc"],
        run_id=row["run_id"],
        plan_id=row["plan_id"],
        node_id=row["node_id"],
        unit_id=row["unit_id"],
        attempt_id=row["attempt_id"],
        model_receipt=row["model_receipt"],
        repository_commit=row["repository_commit"],
        worktree=row["worktree"],
        artifact_hashes=tuple(json.loads(row["artifact_hashes_json"])),
    )
