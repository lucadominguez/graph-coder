from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from graph_coder.contracts import ContractValidationError
from graph_coder.plans import (
    FileSnapshotStore,
    ImplementationUnit,
    PlanDocument,
    Requirement,
    check_maximum_reliability_gates,
    check_traceability,
    create_snapshot,
    parse_markdown_plan,
    reconcile_completed_units,
    semantic_unit_hash,
)

FIXTURES = Path(__file__).parent / "fixtures" / "plans"


def fixture_text() -> str:
    return (FIXTURES / "valid_plan.md").read_text(encoding="utf-8")


def test_parse_markdown_yaml_frontmatter_requires_contract_readiness_metadata_and_headings() -> (
    None
):
    plan = parse_markdown_plan(fixture_text())
    assert plan.metadata["artifact_contract"] == "agent-planning-system/v1"
    assert plan.metadata["artifact_readiness"] == "implementation-ready"
    assert plan.metadata["plan_id"] == "P-demo"
    assert plan.plan_id == "P-demo"
    assert set(plan.headings) >= {
        "Goal Capsule",
        "Product Contract",
        "Planning Contract",
        "System Impact",
        "Implementation Units",
        "Execution Graph",
        "Routing Assignments",
        "Verification Contract",
        "Failure and Recovery Contract",
        "Definition of Done",
        "Sources and Evidence",
    }
    assert len(plan.content_hash) == 64
    assert plan.units[0].semantic_hash.startswith("U-")


def test_invalid_plan_fixture_is_rejected() -> None:
    bad_text = (FIXTURES / "invalid_plan.md").read_text(encoding="utf-8")
    with pytest.raises(ContractValidationError, match="artifact_contract"):
        parse_markdown_plan(bad_text)


@pytest.mark.parametrize(
    ("bad_text", "message"),
    [
        (fixture_text().replace("agent-planning-system/v1", "wrong/v1"), "artifact_contract"),
        (
            fixture_text().replace(
                "artifact_readiness: implementation-ready", "artifact_readiness: draft"
            ),
            "artifact_readiness",
        ),
        (fixture_text().replace("planned_at_commit: abc123\n", ""), "planned_at_commit"),
        (
            fixture_text().replace(
                "## System Impact\nOnly allowed contract and plan files are modified.\n\n", ""
            ),
            "headings",
        ),
    ],
)
def test_parse_rejects_invalid_implementation_ready_plan(bad_text: str, message: str) -> None:
    with pytest.raises(ContractValidationError, match=message):
        parse_markdown_plan(bad_text)


def test_atomic_snapshots_increment_versions_and_write_content(tmp_path: Path) -> None:
    plan = parse_markdown_plan(fixture_text())
    store = FileSnapshotStore(tmp_path)
    first = create_snapshot(plan, store)
    second = create_snapshot(plan, store)
    assert (first.version, second.version) == (1, 2)
    assert first.path.exists() and second.path.exists()
    payload = json.loads(second.path.read_text(encoding="utf-8"))
    assert payload["id"] == plan.plan_id
    assert payload["version"] == 2
    assert payload["content_hash"] == plan.content_hash
    assert not list((tmp_path / plan.plan_id).glob("*.tmp"))


def test_semantic_unit_hash_uses_only_objective_acceptance_dependencies_and_write_scope() -> None:
    unit = ImplementationUnit(
        "U-demo", "Do work", ("A",), ("D",), ("src/x.py",), "pending", ("R-demo",)
    )
    same = replace(unit, status="completed", requirement_ids=("R-other",), semantic_hash="ignored")
    changed = replace(unit, acceptance=("B",))
    assert semantic_unit_hash(unit) == semantic_unit_hash(same)
    assert semantic_unit_hash(unit) != semantic_unit_hash(changed)


def test_traceability_is_bidirectional() -> None:
    unit = ImplementationUnit(
        "U-demo", "Do work", ("A",), write_scope=("src/x.py",), requirement_ids=("R-demo",)
    ).with_hash()
    plan = PlanDocument({}, {}, (unit,), (Requirement("R-demo", "Req", ("U-demo",)),))
    check_traceability(plan)
    bad = PlanDocument(
        {}, {}, (replace(unit, requirement_ids=()),), (Requirement("R-demo", "Req", ("U-demo",)),)
    )
    with pytest.raises(ContractValidationError, match=r"mismatch|no requirements"):
        check_traceability(bad)


def test_maximum_reliability_gate_checks_required_controls() -> None:
    plan = parse_markdown_plan(fixture_text())
    check_maximum_reliability_gates(plan)
    bad = replace(
        plan,
        metadata=plan.metadata
        | {"release_gate": plan.metadata["release_gate"] | {"open_p0_defects": 1}},
    )
    with pytest.raises(ContractValidationError, match="open_p0_defects"):
        check_maximum_reliability_gates(bad)


def test_reconciliation_reopens_changed_or_invalid_completed_units() -> None:
    previous = parse_markdown_plan(fixture_text())
    old_unit = replace(previous.units[0], status="completed")
    previous = replace(previous, units=(old_unit,))
    changed_unit = replace(old_unit, objective="Changed objective", status="completed")
    invalid_unit = replace(
        old_unit, unit_id="U-other", status="completed", acceptance=(), requirement_ids=("R-demo",)
    )
    current = replace(previous, units=(changed_unit, invalid_unit))
    reconciled = reconcile_completed_units(previous, current)
    assert [unit.status for unit in reconciled] == ["reopened", "reopened"]
    assert all(unit.semantic_hash == semantic_unit_hash(unit) for unit in reconciled)
