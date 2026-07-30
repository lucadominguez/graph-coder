"""Canonical Graph Coder plan parsing, validation, snapshots, and reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

import yaml

from .contracts import CONTRACT_VERSION, ContractValidationError

REQUIREMENTS_READY_HEADINGS = (
    "Goal Capsule",
    "Product Contract",
    "Planning Contract",
    "Sources and Evidence",
)
IMPLEMENTATION_READY_HEADINGS = (
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
)
READINESS_VALUES = {"requirements-ready", "implementation-ready"}
_COMPLETED = {"completed", "done"}
ID_PATTERNS = {
    "plan": re.compile(r"^P-[A-Za-z0-9][A-Za-z0-9._-]*$"),
    "requirement": re.compile(r"^R-[A-Za-z0-9][A-Za-z0-9._-]*$"),
    "acceptance": re.compile(r"^AE-[A-Za-z0-9][A-Za-z0-9._-]*$"),
    "invariant": re.compile(r"^I-[A-Za-z0-9][A-Za-z0-9._-]*$"),
    "unit": re.compile(r"^U-[A-Za-z0-9][A-Za-z0-9._-]*$"),
}


@dataclass(frozen=True)
class ImplementationUnit:
    unit_id: str
    objective: str
    acceptance: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    status: str = "pending"
    requirement_ids: tuple[str, ...] = ()
    semantic_hash: str = ""
    title: str = ""
    acceptance_example_ids: tuple[str, ...] = ()
    rationale: str = ""
    input_artifacts: tuple[str, ...] = ()
    inspect_targets: tuple[str, ...] = ()
    read_scope: tuple[str, ...] = ()
    forbidden_scope: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ()
    procedure: tuple[str, ...] = ()
    forward_proof: tuple[str, ...] = ()
    regression_proof: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    output_artifacts: tuple[str, ...] = ()
    risk: str = "medium"
    complexity: str = "medium"
    capability_profile: dict[str, Any] = field(default_factory=dict)
    primary_route: str | None = None
    fallback_route: str | None = None
    attempt_limit: int = 2
    escalation_conditions: tuple[str, ...] = ()
    reviewer: str = ""
    stop_conditions: tuple[str, ...] = ()
    completion_evidence: tuple[str, ...] = ()

    def with_hash(self) -> ImplementationUnit:
        return replace(self, semantic_hash=semantic_unit_hash(self))


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    description: str
    unit_ids: tuple[str, ...]


@dataclass(frozen=True)
class AcceptanceExample:
    example_id: str
    description: str
    unit_ids: tuple[str, ...]


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    description: str
    unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanDocument:
    metadata: dict[str, Any]
    headings: dict[str, str]
    units: tuple[ImplementationUnit, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    acceptance_examples: tuple[AcceptanceExample, ...] = ()
    invariants: tuple[Invariant, ...] = ()
    content_hash: str = ""
    plan_id: str = ""
    source: str = ""

    @property
    def readiness(self) -> str:
        return str(self.metadata.get("artifact_readiness", ""))

    def with_identity(self, source: str) -> PlanDocument:
        return replace(
            self,
            content_hash=sha256_text(source),
            plan_id=str(self.metadata["plan_id"]),
            source=source,
        )


@dataclass(frozen=True)
class Snapshot:
    plan_id: str
    version: int
    content_hash: str
    path: Path


class SnapshotStore(Protocol):
    def latest_version(self, plan_id: str) -> int: ...

    def write_snapshot(self, plan: PlanDocument, version: int) -> Snapshot: ...


@dataclass
class FileSnapshotStore:
    root: Path

    def latest_version(self, plan_id: str) -> int:
        plan_dir = self.root / plan_id
        if not plan_dir.exists():
            return 0
        versions = [
            int(path.stem[1:]) for path in plan_dir.glob("v*.json") if path.stem[1:].isdigit()
        ]
        return max(versions, default=0)

    def write_snapshot(self, plan: PlanDocument, version: int) -> Snapshot:
        plan_dir = self.root / plan.plan_id
        plan_dir.mkdir(parents=True, exist_ok=True)
        target = plan_dir / f"v{version}.json"
        payload = {
            "artifact_contract": CONTRACT_VERSION,
            "artifact_type": "plan",
            "id": plan.plan_id,
            "version": version,
            "content_hash": plan.content_hash,
            "plan_version": plan.metadata["plan_version"],
            "planned_at_commit": plan.metadata["planned_at_commit"],
            "metadata": plan.metadata,
            "requirements": [asdict(item) for item in plan.requirements],
            "acceptance_examples": [asdict(item) for item in plan.acceptance_examples],
            "invariants": [asdict(item) for item in plan.invariants],
            "units": [asdict(item) for item in plan.units],
            "source": plan.source,
        }
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=plan_dir
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return Snapshot(plan.plan_id, version, plan.content_hash, target)


def parse_markdown_plan(text: str) -> PlanDocument:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.S)
    if not match:
        raise ContractValidationError("plan markdown must start with YAML frontmatter")
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ContractValidationError("frontmatter must be a mapping")
    _require_metadata(metadata)
    headings = _extract_headings(match.group(2))
    readiness = str(metadata["artifact_readiness"])
    required_headings = (
        IMPLEMENTATION_READY_HEADINGS
        if readiness == "implementation-ready"
        else REQUIREMENTS_READY_HEADINGS
    )
    missing = [heading for heading in required_headings if heading not in headings]
    if missing:
        raise ContractValidationError("missing required plan headings: " + ", ".join(missing))
    units = tuple(_unit_from_mapping(item).with_hash() for item in metadata.get("units", []))
    requirements = tuple(
        Requirement(
            str(item["requirement_id"]),
            str(item.get("description", "")),
            tuple(str(value) for value in item.get("unit_ids", ())),
        )
        for item in metadata.get("requirements", [])
    )
    acceptance_examples = tuple(
        AcceptanceExample(
            str(item["example_id"]),
            str(item.get("description", "")),
            tuple(str(value) for value in item.get("unit_ids", ())),
        )
        for item in metadata.get("acceptance_examples", [])
    )
    invariants = tuple(
        Invariant(
            str(item["invariant_id"]),
            str(item.get("description", "")),
            tuple(str(value) for value in item.get("unit_ids", ())),
        )
        for item in metadata.get("invariants", [])
    )
    plan = PlanDocument(
        metadata=metadata,
        headings=headings,
        units=units,
        requirements=requirements,
        acceptance_examples=acceptance_examples,
        invariants=invariants,
    ).with_identity(text)
    _validate_ids(plan)
    if readiness == "implementation-ready":
        check_traceability(plan)
        check_maximum_reliability_gates(plan)
    return plan


def _require_metadata(metadata: dict[str, Any]) -> None:
    required = (
        "artifact_contract",
        "artifact_readiness",
        "plan_id",
        "plan_version",
        "planned_at_commit",
        "primary_planning_model",
        "planning_model_receipt",
        "approved",
    )
    missing = [key for key in required if key not in metadata]
    if missing:
        raise ContractValidationError("required frontmatter missing: " + ", ".join(missing))
    if metadata["artifact_contract"] != CONTRACT_VERSION:
        raise ContractValidationError("artifact_contract must be agent-planning-system/v1")
    if metadata["artifact_readiness"] not in READINESS_VALUES:
        raise ContractValidationError(
            "artifact_readiness must be requirements-ready or implementation-ready"
        )
    if not ID_PATTERNS["plan"].match(str(metadata["plan_id"])):
        raise ContractValidationError("plan_id must be a stable P- identifier")
    if not isinstance(metadata["plan_version"], int) or metadata["plan_version"] < 1:
        raise ContractValidationError("plan_version must be a positive integer")
    if metadata["planning_model_receipt"] not in {"verified", "unverified"}:
        raise ContractValidationError("planning_model_receipt must be verified or unverified")
    if not isinstance(metadata["approved"], bool):
        raise ContractValidationError("approved must be boolean")
    if metadata["approved"] and metadata["artifact_readiness"] != "implementation-ready":
        raise ContractValidationError("only implementation-ready plans may be approved")


def _extract_headings(body: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, re.M))
    headings: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        headings[match.group(1).strip()] = body[start:end].strip()
    return headings


def _strings(item: dict[str, Any], name: str) -> tuple[str, ...]:
    return tuple(str(value) for value in item.get(name, ()))


def _unit_from_mapping(item: dict[str, Any]) -> ImplementationUnit:
    return ImplementationUnit(
        unit_id=str(item["unit_id"]),
        title=str(item.get("title", "")),
        objective=str(item["objective"]),
        acceptance=_strings(item, "acceptance"),
        requirement_ids=_strings(item, "requirement_ids"),
        acceptance_example_ids=_strings(item, "acceptance_example_ids"),
        rationale=str(item.get("rationale", "")),
        dependencies=_strings(item, "dependencies"),
        input_artifacts=_strings(item, "input_artifacts"),
        inspect_targets=_strings(item, "inspect_targets"),
        read_scope=_strings(item, "read_scope"),
        write_scope=_strings(item, "write_scope"),
        forbidden_scope=_strings(item, "forbidden_scope"),
        interfaces=_strings(item, "interfaces"),
        procedure=_strings(item, "procedure"),
        forward_proof=_strings(item, "forward_proof"),
        regression_proof=_strings(item, "regression_proof"),
        commands=_strings(item, "commands"),
        output_artifacts=_strings(item, "output_artifacts"),
        risk=str(item.get("risk", "medium")),
        complexity=str(item.get("complexity", "medium")),
        capability_profile=dict(item.get("capability_profile", {})),
        primary_route=item.get("primary_route"),
        fallback_route=item.get("fallback_route"),
        attempt_limit=int(item.get("attempt_limit", 2)),
        escalation_conditions=_strings(item, "escalation_conditions"),
        reviewer=str(item.get("reviewer", "")),
        stop_conditions=_strings(item, "stop_conditions"),
        completion_evidence=_strings(item, "completion_evidence"),
        status=str(item.get("status", "pending")),
        semantic_hash=str(item.get("semantic_hash", "")),
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def semantic_unit_hash(unit: ImplementationUnit | dict[str, Any]) -> str:
    if isinstance(unit, ImplementationUnit):
        payload = {
            "objective": unit.objective,
            "acceptance": sorted(unit.acceptance),
            "dependencies": sorted(unit.dependencies),
            "write_scope": sorted(unit.write_scope),
        }
    else:
        payload = {
            "objective": unit.get("objective", ""),
            "acceptance": sorted(unit.get("acceptance", ())),
            "dependencies": sorted(unit.get("dependencies", ())),
            "write_scope": sorted(unit.get("write_scope", ())),
        }
    return "U-" + sha256_text(canonical_json(payload))[:24]


def create_snapshot(plan: PlanDocument, store: SnapshotStore) -> Snapshot:
    version = max(store.latest_version(plan.plan_id) + 1, int(plan.metadata["plan_version"]))
    return store.write_snapshot(plan, version)


def _validate_ids(plan: PlanDocument) -> None:
    groups = (
        ("requirement", [item.requirement_id for item in plan.requirements]),
        ("acceptance", [item.example_id for item in plan.acceptance_examples]),
        ("invariant", [item.invariant_id for item in plan.invariants]),
        ("unit", [item.unit_id for item in plan.units]),
    )
    for kind, values in groups:
        if len(values) != len(set(values)):
            raise ContractValidationError(f"duplicate {kind} identifiers")
        invalid = [value for value in values if not ID_PATTERNS[kind].match(value)]
        if invalid:
            raise ContractValidationError(f"invalid {kind} identifiers: {invalid}")


def check_traceability(plan: PlanDocument) -> None:
    requirement_to_units = {item.requirement_id: set(item.unit_ids) for item in plan.requirements}
    unit_to_requirements = {item.unit_id: set(item.requirement_ids) for item in plan.units}
    acceptance_to_units = {item.example_id: set(item.unit_ids) for item in plan.acceptance_examples}
    unit_to_acceptance = {item.unit_id: set(item.acceptance_example_ids) for item in plan.units}
    for requirement_id, unit_ids in requirement_to_units.items():
        if not unit_ids:
            raise ContractValidationError(
                f"requirement {requirement_id} has no implementation or verification unit"
            )
        for unit_id in unit_ids:
            if unit_id not in unit_to_requirements:
                raise ContractValidationError(
                    f"requirement {requirement_id} references missing unit {unit_id}"
                )
            if requirement_id not in unit_to_requirements[unit_id]:
                raise ContractValidationError(
                    f"traceability mismatch: {requirement_id} -> {unit_id}"
                )
    for unit_id, requirement_ids in unit_to_requirements.items():
        if not requirement_ids:
            raise ContractValidationError(f"unit {unit_id} has no requirements")
        for requirement_id in requirement_ids:
            if requirement_id not in requirement_to_units:
                raise ContractValidationError(
                    f"unit {unit_id} references missing requirement {requirement_id}"
                )
            if unit_id not in requirement_to_units[requirement_id]:
                raise ContractValidationError(
                    f"traceability mismatch: {unit_id} -> {requirement_id}"
                )
    for example_id, unit_ids in acceptance_to_units.items():
        if not unit_ids:
            raise ContractValidationError(f"acceptance example {example_id} has no unit")
        for unit_id in unit_ids:
            if unit_id not in unit_to_acceptance or example_id not in unit_to_acceptance[unit_id]:
                raise ContractValidationError(
                    f"acceptance traceability mismatch: {example_id} -> {unit_id}"
                )
    for unit_id, example_ids in unit_to_acceptance.items():
        for example_id in example_ids:
            if (
                example_id not in acceptance_to_units
                or unit_id not in acceptance_to_units[example_id]
            ):
                raise ContractValidationError(
                    f"acceptance traceability mismatch: {unit_id} -> {example_id}"
                )


def check_maximum_reliability_gates(plan: PlanDocument) -> None:
    defects = collect_readiness_defects(plan)
    if defects:
        raise ContractValidationError("; ".join(defects))


def collect_readiness_defects(plan: PlanDocument) -> list[str]:
    defects: list[str] = []
    if plan.readiness != "implementation-ready":
        defects.append("plan is not implementation-ready")
        return defects
    if not plan.requirements:
        defects.append("no requirements")
    if not plan.acceptance_examples:
        defects.append("no acceptance examples")
    if not plan.invariants:
        defects.append("no invariants")
    unit_ids = {unit.unit_id for unit in plan.units}
    for unit in plan.units:
        required_fields = {
            "acceptance": unit.acceptance,
            "inspect targets": unit.inspect_targets,
            "write scope": unit.write_scope,
            "procedure": unit.procedure,
            "forward proof": unit.forward_proof,
            "regression proof": unit.regression_proof,
            "commands": unit.commands,
            "output artifacts": unit.output_artifacts,
            "reviewer": (unit.reviewer,),
            "STOP conditions": unit.stop_conditions,
            "completion evidence": unit.completion_evidence,
        }
        for field_name, value in required_fields.items():
            if not value:
                defects.append(f"unit {unit.unit_id} missing {field_name}")
        unknown_dependencies = set(unit.dependencies) - unit_ids
        if unknown_dependencies:
            defects.append(
                f"unit {unit.unit_id} has unknown dependencies {sorted(unknown_dependencies)}"
            )
        if not 1 <= unit.attempt_limit <= 10:
            defects.append(f"unit {unit.unit_id} has invalid attempt limit")
        if unit.status in _COMPLETED and not unit.completion_evidence:
            defects.append(f"completed unit {unit.unit_id} lacks completion evidence")
    release = plan.metadata.get("release_gate", {})
    required_truths = (
        "all_leaf_rehearsals_passed",
        "high_risk_double_rehearsed",
        "artifact_handoffs_complete",
        "existing_failures_classified",
        "operations_complete_when_applicable",
        "manager_failure_classes_complete",
    )
    for key in required_truths:
        if release.get(key) is not True:
            defects.append(f"release gate {key} is not satisfied")
    zero_fields = (
        "open_p0_defects",
        "open_p1_defects",
        "unsafe_write_overlaps",
        "launch_blocking_questions",
    )
    for key in zero_fields:
        if release.get(key) != 0:
            defects.append(f"release gate {key} must be zero")
    for key in ("max_active_workers", "max_total_nodes", "max_graph_depth", "attempt_limit"):
        if not isinstance(release.get(key), int) or release[key] < 1:
            defects.append(f"release gate {key} must be a positive bound")
    if not isinstance(release.get("execution_cost_ceiling"), (int, float)):
        defects.append("release gate execution_cost_ceiling must be explicit")
    return defects


def reconcile_completed_units(
    previous: PlanDocument, current: PlanDocument
) -> tuple[ImplementationUnit, ...]:
    previous_by_id = {unit.unit_id: unit for unit in previous.units}
    reconciled: list[ImplementationUnit] = []
    for unit in current.units:
        expected = semantic_unit_hash(unit)
        old = previous_by_id.get(unit.unit_id)
        invalid = bool(
            collect_readiness_defects(
                replace(
                    current,
                    units=(unit,),
                    requirements=tuple(
                        requirement
                        for requirement in current.requirements
                        if unit.unit_id in requirement.unit_ids
                    ),
                )
            )
        )
        changed = old is not None and old.semantic_hash and old.semantic_hash != expected
        evidence_missing = (
            old is not None and old.status in _COMPLETED and not old.completion_evidence
        )
        if unit.status in _COMPLETED and (old is None or changed or invalid or evidence_missing):
            status = "reopened"
        elif old is not None and old.status in _COMPLETED and not changed and not invalid:
            status = old.status
        else:
            status = unit.status
        reconciled.append(replace(unit, status=status, semantic_hash=expected))
    return tuple(reconciled)
