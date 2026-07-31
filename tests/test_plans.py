from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from graph_coder.contracts import ContractValidationError
from graph_coder.plans import (
    APPROVAL_HASHES,
    CANONICAL_SECTIONS,
    FileSnapshotStore,
    ImplementationUnit,
    PlanDocument,
    Requirement,
    approval_binding,
    approval_is_valid,
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
    assert plan.metadata["artifact_contract"] == "graph-coder/v1"
    assert plan.metadata["artifact_readiness"] == "implementation-ready"
    assert plan.metadata["plan_id"] == "P-demo"
    assert plan.plan_id == "P-demo"
    assert set(plan.headings) >= set(CANONICAL_SECTIONS)
    # Product Contract is not a native section: concept and requirements live in
    # the plan itself.
    assert "Product Contract" not in plan.headings
    assert len(plan.content_hash) == 64
    assert plan.units[0].semantic_hash.startswith("U-")
    assert plan.units[0].manager_id == "M-CONTRACTS"
    assert plan.units[0].retry_policy["then"] == "human_required"


def test_canonical_sections_are_the_sixteen_in_order() -> None:
    assert len(CANONICAL_SECTIONS) == 16
    plan = parse_markdown_plan(fixture_text())
    body = plan.source.split("---", 2)[2]
    positions = [body.index(f"## {section}") for section in CANONICAL_SECTIONS]
    assert positions == sorted(positions)


def test_approved_plans_must_bind_four_hashes_and_a_full_render() -> None:
    for name in APPROVAL_HASHES:
        broken = fixture_text().replace(f"  {name}: sha256:", f"  {name}_disabled: sha256:")
        with pytest.raises(ContractValidationError, match="missing required hashes"):
            parse_markdown_plan(broken)

    summary_only = fixture_text().replace(
        "rendered_full_plan: true", "rendered_full_plan: false"
    )
    with pytest.raises(ContractValidationError, match="summary is not an approval view"):
        parse_markdown_plan(summary_only)


def test_a_material_change_voids_the_approval() -> None:
    plan = parse_markdown_plan(fixture_text())
    recorded = approval_binding(plan)

    still_valid, drifted = approval_is_valid(plan, recorded)
    assert still_valid and drifted == []

    moved = {**recorded, "graph_hash": "sha256:" + "9" * 64}
    still_valid, drifted = approval_is_valid(plan, moved)
    assert not still_valid
    assert drifted == ["graph_hash"]


def test_semantic_hash_covers_the_execution_contract_but_not_prose() -> None:
    unit = parse_markdown_plan(fixture_text()).units[0]
    baseline = semantic_unit_hash(unit)

    # Prose is not part of the contract.
    assert semantic_unit_hash(replace(unit, title="Renamed", rationale="Reworded")) == baseline

    # These are.
    for changed in (
        replace(unit, write_scope=("src/other.py",)),
        replace(unit, forbidden_scope=()),
        replace(unit, commands=("pytest -q",)),
        replace(unit, interfaces=("something_else",)),
        replace(unit, manager_id="M-OTHER"),
        replace(unit, review_contract={"scope_check": False}),
        replace(unit, context_manifest={"max_bytes": 1}),
        replace(unit, retry_policy={"then": "human_required", "same_worker_attempts": 9}),
        replace(unit, primary_route="remote"),
    ):
        assert semantic_unit_hash(changed) != baseline


def test_invalid_plan_fixture_is_rejected() -> None:
    bad_text = (FIXTURES / "invalid_plan.md").read_text(encoding="utf-8")
    with pytest.raises(ContractValidationError, match="artifact_contract"):
        parse_markdown_plan(bad_text)


@pytest.mark.parametrize(
    ("bad_text", "message"),
    [
        (fixture_text().replace("graph-coder/v1", "wrong/v1"), "artifact_contract"),
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
