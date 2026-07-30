"""Versioned Graph Coder artifact contracts and JSON Schema validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

CONTRACT_VERSION = "agent-planning-system/v1"
ArtifactKind = Literal[
    "plan",
    "graph",
    "task_packet",
    "worker_report",
    "review_defect",
    "manager_advice",
    "event",
]

SCHEMA_NAMES: dict[ArtifactKind, str] = {
    "plan": "plan.schema.json",
    "graph": "graph.schema.json",
    "task_packet": "task_packet.schema.json",
    "worker_report": "worker_report.schema.json",
    "review_defect": "review_defect.schema.json",
    "manager_advice": "manager_advice.schema.json",
    "event": "event.schema.json",
}


class ContractValidationError(ValueError):
    """Raised when an Graph Coder artifact does not satisfy its versioned contract."""


@dataclass(frozen=True)
class ArtifactMetadata:
    artifact_contract: str = CONTRACT_VERSION
    artifact_type: str = ""
    id: str = ""
    version: int = 1


@dataclass(frozen=True)
class RequirementRef:
    requirement_id: str
    unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnitRef:
    unit_id: str
    requirement_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContractArtifact:
    artifact_contract: str
    artifact_type: str
    id: str
    version: int
    body: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ContractArtifact:
        return cls(
            artifact_contract=str(data.get("artifact_contract", "")),
            artifact_type=str(data.get("artifact_type", "")),
            id=str(data.get("id", "")),
            version=int(data.get("version", 0)),
            body={
                k: v
                for k, v in data.items()
                if k not in {"artifact_contract", "artifact_type", "id", "version"}
            },
        )


def _schema_root() -> Path:
    packaged = Path(__file__).resolve().parent / "schemas" / "v1"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / "v1"


def load_schema(kind: ArtifactKind) -> dict[str, Any]:
    """Load a JSON Schema by artifact kind from the source tree."""

    value = json.loads((_schema_root() / SCHEMA_NAMES[kind]).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractValidationError(f"schema {kind} must be a JSON object")
    return cast(dict[str, Any], value)


def validator_for(kind: ArtifactKind) -> Draft202012Validator:
    schema = load_schema(kind)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_artifact(data: dict[str, Any], kind: ArtifactKind | None = None) -> ContractArtifact:
    """Validate an artifact mapping and return a typed wrapper."""

    actual_kind = kind or data.get("artifact_type")
    if actual_kind not in SCHEMA_NAMES:
        raise ContractValidationError(f"unknown artifact_type: {actual_kind!r}")
    validator = validator_for(cast(ArtifactKind, actual_kind))
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise ContractValidationError(_format_error(errors[0]))
    return ContractArtifact.from_mapping(data)


def _format_error(error: ValidationError) -> str:
    path = "/".join(str(p) for p in error.absolute_path) or "<root>"
    return f"{path}: {error.message}"
