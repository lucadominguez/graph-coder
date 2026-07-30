from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from graph_coder.contracts import (
    CONTRACT_VERSION,
    SCHEMA_NAMES,
    ContractValidationError,
    load_schema,
    validate_artifact,
)

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


def test_all_contract_schemas_are_draft_2020_12_and_pin_version() -> None:
    assert set(SCHEMA_NAMES) == {
        "plan",
        "graph",
        "task_packet",
        "worker_report",
        "review_defect",
        "manager_advice",
        "event",
    }
    for kind in SCHEMA_NAMES:
        schema = load_schema(kind)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["properties"]["artifact_contract"] == {"const": CONTRACT_VERSION}
        assert schema["properties"]["artifact_type"] == {"const": kind}


def test_valid_fixture_returns_typed_artifact() -> None:
    data = json.loads((FIXTURES / "valid" / "plan.json").read_text(encoding="utf-8"))
    artifact = validate_artifact(data)
    assert artifact.artifact_contract == CONTRACT_VERSION
    assert artifact.artifact_type == "plan"
    assert artifact.id == "P-demo"
    assert artifact.body["units"][0]["unit_id"] == "U-001"


def test_invalid_fixture_reports_path_and_reason() -> None:
    data = json.loads((FIXTURES / "valid" / "plan.json").read_text(encoding="utf-8"))
    data["artifact_contract"] = "wrong/v1"
    with pytest.raises(ContractValidationError, match="artifact_contract"):
        validate_artifact(data, "plan")


def test_each_artifact_kind_validates_a_minimal_valid_document() -> None:
    common = {"artifact_contract": CONTRACT_VERSION, "id": "A1", "version": 1}
    docs = {
        "graph": common
        | {
            "artifact_type": "graph",
            "root_id": "Director",
            "bounds": {
                "max_nodes": 100,
                "max_depth": 6,
                "max_fanout": 8,
                "default_attempt_limit": 2,
            },
            "nodes": [
                {
                    "id": "n1",
                    "type": "implement",
                    "atomicity": "atomic",
                    "role": "worker",
                    "unit_ids": ["U-001"],
                    "parent_owner": "Director",
                    "dependencies": [],
                    "artifact_inputs": [],
                    "artifact_outputs": [],
                    "read_scope": ["src"],
                    "write_scope": ["src/x.py"],
                    "acceptance": ["passes"],
                    "review_gate": {},
                    "route": {},
                    "risk": "medium",
                    "priority": "normal",
                    "attempt_limit": 2,
                    "heartbeat_seconds": 300,
                    "expansion_allowed": False,
                    "child_cap": 0,
                    "failure_domain": "node",
                }
            ],
            "edges": [],
        },
        "task_packet": common
        | {
            "artifact_type": "task_packet",
            "plan_id": "P-demo",
            "plan_version": 1,
            "graph_id": "G1",
            "graph_version": 1,
            "node_id": "n1",
            "unit_id": "U-001",
            "attempt": 1,
            "objective": "Do work",
            "input_artifacts": [],
            "instructions": ["implement"],
            "inspect_targets": ["src/x.py"],
            "read_scope": ["src"],
            "write_scope": ["src/x.py"],
            "forbidden_scope": ["secrets"],
            "acceptance": ["passes"],
            "verification_commands": ["pytest"],
            "stop_conditions": ["destructive action"],
            "report_schema": {},
        },
        "worker_report": common
        | {
            "artifact_type": "worker_report",
            "plan_id": "P-demo",
            "plan_version": 1,
            "graph_id": "G1",
            "graph_version": 1,
            "node_id": "n1",
            "unit_id": "U-001",
            "attempt": 1,
            "status": "completed",
            "summary": "Done",
            "files_changed": ["src/x.py"],
            "commands": [{"command": "pytest", "exit_code": 0}],
            "artifacts": [],
            "decisions": [],
            "deviations": [],
            "evidence": ["pytest"],
            "suggested_next_action": "review",
        },
        "review_defect": common
        | {
            "artifact_type": "review_defect",
            "defect_id": "D1",
            "severity": "P1",
            "evidence": ["file:line"],
            "affected_ids": ["U-001"],
            "affected_section": "Implementation Units",
            "consequence": "Bug",
            "proposed_resolution": "Fix it",
            "reviewer_identity": "reviewer",
            "model_receipt": "verified:model",
            "status": "open",
        },
        "manager_advice": common
        | {
            "artifact_type": "manager_advice",
            "node_id": "n1",
            "problem": "failure",
            "evidence": ["trace"],
            "likely_cause": "transient",
            "allowed_recovery_options": ["retry"],
            "recommended_option": "retry",
            "tradeoff": "cost",
            "worker_actions": ["retry once"],
            "escalation_threshold": "second failure",
        },
        "event": common
        | {
            "artifact_type": "event",
            "sequence": 1,
            "prior_hash": "0" * 64,
            "event_hash": "1" * 64,
            "event_type": "snapshot.created",
            "timestamp_utc": "2026-07-27T00:00:00Z",
            "actor_role": "Director",
            "payload": {},
            "artifact_hashes": [],
        },
    }
    for kind, document in docs.items():
        assert validate_artifact(document).artifact_type == kind
