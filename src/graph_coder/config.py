"""Project configuration and atomic filesystem helpers."""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "planning": {
        "profile": "maximum-reliability",
        "primary_model": "planner-primary",
        "fallback_models": ["planner-fallback-1", "planner-fallback-2"],
        "audit_models": ["planner-auditor-1", "planner-auditor-2"],
        "allow_unapproved_fallback": False,
    },
    "routing": {
        "external_weight": 0.60,
        "local_weight": 0.30,
        "quality_margin": 0.05,
        "prefer_open_weight": True,
        "data_max_age_hours": 24,
    },
    "execution": {
        "max_active_workers": 8,
        "max_total_nodes": 100,
        "max_graph_depth": 6,
        "default_attempt_limit": 2,
        "recursive_spawning": False,
    },
    "manager": {
        "safe_transient_retries": 1,
        "stale_heartbeat_seconds": 300,
        "continue_independent_work": True,
    },
    "jcode": {
        "skills_location": ".agents/skills",
        "director_foreground": True,
        "workers_headless": True,
    },
    "storage": {
        "directory": ".graph-coder",
        "database": "state.db",
        "snapshots": "snapshots",
        "cache": "cache/llm-stats",
        "projections": "projections",
        "context": "context",
        "artifacts": "artifacts",
    },
    "sqlite": {"busy_timeout_ms": 5000},
    "events": {"verify_on_startup": True},
    "recovery": {"packet_event_limit": 20, "interrupt_inflight_on_startup": True},
}

DEFAULT_CONFIG_TOML = """[planning]
profile = "maximum-reliability"
primary_model = "planner-primary"
fallback_models = ["planner-fallback-1", "planner-fallback-2"]
audit_models = ["planner-auditor-1", "planner-auditor-2"]
allow_unapproved_fallback = false

[routing]
external_weight = 0.60
local_weight = 0.30
quality_margin = 0.05
prefer_open_weight = true
data_max_age_hours = 24

[execution]
max_active_workers = 8
max_total_nodes = 100
max_graph_depth = 6
default_attempt_limit = 2
recursive_spawning = false

[manager]
safe_transient_retries = 1
stale_heartbeat_seconds = 300
continue_independent_work = true

[jcode]
skills_location = ".agents/skills"
director_foreground = true
workers_headless = true
"""


@dataclass(frozen=True)
class PlanningConfig:
    profile: str
    primary_model: str
    fallback_models: tuple[str, ...]
    audit_models: tuple[str, ...]
    allow_unapproved_fallback: bool


@dataclass(frozen=True)
class RoutingConfig:
    external_weight: float
    local_weight: float
    quality_margin: float
    prefer_open_weight: bool
    data_max_age_hours: int


@dataclass(frozen=True)
class ExecutionConfig:
    max_active_workers: int
    max_total_nodes: int
    max_graph_depth: int
    default_attempt_limit: int
    recursive_spawning: bool


@dataclass(frozen=True)
class ManagerConfig:
    safe_transient_retries: int
    stale_heartbeat_seconds: int
    continue_independent_work: bool


@dataclass(frozen=True)
class JCodeConfig:
    skills_location: str
    director_foreground: bool
    workers_headless: bool


@dataclass(frozen=True)
class GraphCoderConfig:
    root: Path
    config_path: Path
    storage_dir: Path
    database_path: Path
    snapshots_dir: Path
    cache_dir: Path
    projections_dir: Path
    context_dir: Path
    artifacts_dir: Path
    busy_timeout_ms: int
    verify_on_startup: bool
    packet_event_limit: int
    planning: PlanningConfig
    routing: RoutingConfig
    execution: ExecutionConfig
    manager: ManagerConfig
    jcode: JCodeConfig


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: _merge(value, {}) if isinstance(value, dict) else value for key, value in base.items()
    }
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"configuration section {name!r} must be a table")
    return value


def load_config(
    root: str | os.PathLike[str], config_path: str | os.PathLike[str] | None = None
) -> GraphCoderConfig:
    root_path = Path(root)
    storage_dir = root_path / str(DEFAULTS["storage"]["directory"])
    preferred = storage_dir / "config.toml"
    legacy = root_path / ".graph-coder.toml"
    path = Path(config_path) if config_path else preferred
    if config_path is None and not preferred.exists() and legacy.exists():
        path = legacy
    override: dict[str, Any] = {}
    if path.exists():
        with path.open("rb") as handle:
            override = tomllib.load(handle)
    data = _merge(DEFAULTS, override)
    storage = _section(data, "storage")
    storage_dir = root_path / str(storage["directory"])
    planning = _section(data, "planning")
    routing = _section(data, "routing")
    execution = _section(data, "execution")
    manager = _section(data, "manager")
    jcode = _section(data, "jcode")
    sqlite = _section(data, "sqlite")
    events = _section(data, "events")
    recovery = _section(data, "recovery")
    return GraphCoderConfig(
        root=root_path,
        config_path=path,
        storage_dir=storage_dir,
        database_path=storage_dir / str(storage["database"]),
        snapshots_dir=storage_dir / str(storage["snapshots"]),
        cache_dir=storage_dir / str(storage["cache"]),
        projections_dir=storage_dir / str(storage["projections"]),
        context_dir=storage_dir / str(storage["context"]),
        artifacts_dir=storage_dir / str(storage["artifacts"]),
        busy_timeout_ms=int(sqlite["busy_timeout_ms"]),
        verify_on_startup=bool(events["verify_on_startup"]),
        packet_event_limit=int(recovery["packet_event_limit"]),
        planning=PlanningConfig(
            profile=str(planning["profile"]),
            primary_model=str(planning["primary_model"]),
            fallback_models=tuple(str(item) for item in planning["fallback_models"]),
            audit_models=tuple(str(item) for item in planning["audit_models"]),
            allow_unapproved_fallback=bool(planning["allow_unapproved_fallback"]),
        ),
        routing=RoutingConfig(
            external_weight=float(routing["external_weight"]),
            local_weight=float(routing["local_weight"]),
            quality_margin=float(routing["quality_margin"]),
            prefer_open_weight=bool(routing["prefer_open_weight"]),
            data_max_age_hours=int(routing["data_max_age_hours"]),
        ),
        execution=ExecutionConfig(
            max_active_workers=int(execution["max_active_workers"]),
            max_total_nodes=int(execution["max_total_nodes"]),
            max_graph_depth=int(execution["max_graph_depth"]),
            default_attempt_limit=int(execution["default_attempt_limit"]),
            recursive_spawning=bool(execution["recursive_spawning"]),
        ),
        manager=ManagerConfig(
            safe_transient_retries=int(manager["safe_transient_retries"]),
            stale_heartbeat_seconds=int(manager["stale_heartbeat_seconds"]),
            continue_independent_work=bool(manager["continue_independent_work"]),
        ),
        jcode=JCodeConfig(
            skills_location=str(jcode["skills_location"]),
            director_foreground=bool(jcode["director_foreground"]),
            workers_headless=bool(jcode["workers_headless"]),
        ),
    )


def ensure_layout(config: GraphCoderConfig) -> None:
    for directory in (
        config.storage_dir,
        config.snapshots_dir,
        config.cache_dir,
        config.projections_dir,
        config.context_dir,
        config.artifacts_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def atomic_write(path: str | os.PathLike[str], data: str | bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        if isinstance(data, bytes):
            with os.fdopen(fd, "wb") as binary_handle:
                binary_handle.write(data)
                binary_handle.flush()
                os.fsync(binary_handle.fileno())
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as text_handle:
                text_handle.write(data)
                text_handle.flush()
                os.fsync(text_handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        finally:
            raise
