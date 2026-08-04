"""Command-line interface for Graph Coder."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from . import __version__
from .adapters.jcode import PLACEHOLDER_ROUTES, JCodeAdapter
from .config import (
    DEFAULT_CONFIG_TOML,
    GraphCoderConfig,
    atomic_write,
    ensure_layout,
    load_config,
)
from .context import compact_context
from .contracts import load_schema
from .db import connect, migrate, transaction
from .errors import ContractError, GraphCoderError, RoutingError
from .events import append_event, rebuild_projections, verify_chain
from .graph import (
    ArtifactRef,
    ExecutionGraph,
    GraphNode,
    Limits,
    NodeAuthority,
    NodeKind,
    NodeRole,
    ReviewPolicy,
    RouteSpec,
)
from .llm_stats import DEFAULT_API_BASE, LLMStatsClient
from .plans import (
    FileSnapshotStore,
    PlanDocument,
    collect_readiness_defects,
    create_snapshot,
    parse_markdown_plan,
    reconcile_completed_units,
)
from .recovery import recover, resume_human_required
from .registry import assert_fresh, build_registry
from .routing import (
    ModelCapabilities,
    ProviderCapabilities,
    RoutingDecision,
    TaskRequirements,
    VerifiedHistory,
    build_route_receipt,
    route_model,
)
from .terminal import build_windows_terminal_layout, open_windows_terminal

JsonObject = dict[str, Any]
Handler = Callable[[argparse.Namespace], JsonObject]


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if isinstance(value, (Path, Enum)):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _emit(payload: JsonObject, *, pretty: bool = True) -> None:
    json.dump(
        payload,
        sys.stdout,
        default=_json_default,
        indent=2 if pretty else None,
        sort_keys=True,
    )
    sys.stdout.write("\n")


def _root(args: argparse.Namespace) -> Path:
    return Path(args.root or os.getcwd()).resolve()


def _config(args: argparse.Namespace) -> GraphCoderConfig:
    return load_config(_root(args), getattr(args, "config", None))


def _database(args: argparse.Namespace) -> tuple[GraphCoderConfig, sqlite3.Connection]:
    config = _config(args)
    ensure_layout(config)
    connection = connect(config.database_path, config.busy_timeout_ms)
    migrate(connection)
    return config, connection


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Any) -> None:
    atomic_write(
        path,
        json.dumps(payload, default=_json_default, indent=2, sort_keys=True) + "\n",
    )


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _cmd_init(args: argparse.Namespace) -> JsonObject:
    root = _root(args)
    config = _config(args)
    ensure_layout(config)
    config_path = config.config_path
    created = False
    if not config_path.exists():
        atomic_write(config_path, DEFAULT_CONFIG_TOML)
        created = True
    _, connection = _database(args)
    try:
        project_id = _stable_id("project", str(root).casefold())
        with transaction(connection):
            connection.execute(
                """INSERT INTO projects(id,root,name) VALUES (?,?,?)
                ON CONFLICT(root) DO UPDATE SET
                    name=excluded.name,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                (project_id, str(root), root.name),
            )
        event = append_event(
            connection,
            "project.initialized",
            {"root": str(root), "version": __version__},
            idempotency_key=args.idempotency_key or f"init:{root}",
            role="Director",
        )
    finally:
        connection.close()
    return {
        "ok": True,
        "root": str(root),
        "state_directory": str(config.storage_dir),
        "database": str(config.database_path),
        "config": str(config_path),
        "config_created": created,
        "project_id": project_id,
        "event_sequence": event.sequence,
    }


def _cmd_inspect(args: argparse.Namespace) -> JsonObject:
    config = _config(args)
    adapter = JCodeAdapter()
    return {
        "ok": True,
        "version": __version__,
        "repository": compact_context(config.root),
        "state": {
            "directory": str(config.storage_dir),
            "database": str(config.database_path),
            "database_exists": config.database_path.exists(),
        },
        "jcode": adapter.compatibility(),
    }


def _plan_path(args: argparse.Namespace) -> Path:
    if not getattr(args, "file", None):
        raise ContractError("--file is required for this plan operation")
    return Path(args.file)


def _load_plan(args: argparse.Namespace) -> tuple[Path, PlanDocument]:
    path = _plan_path(args)
    return path, parse_markdown_plan(path.read_text(encoding="utf-8"))


def _cmd_plan_status(args: argparse.Namespace) -> JsonObject:
    config = _config(args)
    result: JsonObject = {
        "ok": True,
        "state_exists": config.database_path.exists(),
        "plan": None,
    }
    if getattr(args, "file", None):
        path, plan = _load_plan(args)
        result["plan"] = {
            "path": str(path),
            "plan_id": plan.plan_id,
            "content_hash": plan.content_hash,
            "readiness": plan.metadata.get("artifact_readiness"),
            "approved": bool(plan.metadata.get("approved", False)),
            "units": len(plan.units),
            "requirements": len(plan.requirements),
        }
    if config.database_path.exists():
        connection = connect(config.database_path, config.busy_timeout_ms)
        try:
            migrate(connection)
            ok, error = verify_chain(connection)
            row = connection.execute(
                "SELECT sequence,event_type,created_at FROM events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            result["ledger"] = {
                "valid": ok,
                "error": error,
                "last_event": dict(row) if row else None,
            }
        finally:
            connection.close()
    return result


def _cmd_plan_validate(args: argparse.Namespace) -> JsonObject:
    path, plan = _load_plan(args)
    defects = collect_readiness_defects(plan)
    return {
        "ok": not defects,
        "path": str(path),
        "plan_id": plan.plan_id,
        "content_hash": plan.content_hash,
        "defects": defects,
    }


def _cmd_plan_snapshot(args: argparse.Namespace) -> JsonObject:
    path, plan = _load_plan(args)
    config, connection = _database(args)
    try:
        existing = connection.execute(
            """SELECT version,content_hash,snapshot_path FROM plan_versions
            WHERE plan_id=? AND content_hash=?""",
            (plan.plan_id, plan.content_hash),
        ).fetchone()
        if existing:
            snapshot_payload = {
                "plan_id": plan.plan_id,
                "version": existing["version"],
                "content_hash": existing["content_hash"],
                "path": existing["snapshot_path"],
            }
        else:
            snapshot = create_snapshot(plan, FileSnapshotStore(config.snapshots_dir))
            snapshot_payload = asdict(snapshot)
            unit_ids = {unit.unit_id for unit in plan.units}
            with transaction(connection):
                connection.execute(
                    """INSERT INTO plan_versions(
                        plan_id,version,content_hash,source_path,snapshot_path,
                        repository_commit,readiness,approved,metadata_json
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        plan.plan_id,
                        snapshot.version,
                        plan.content_hash,
                        str(path),
                        str(snapshot.path),
                        str(plan.metadata["planned_at_commit"]),
                        plan.readiness,
                        int(bool(plan.metadata["approved"])),
                        json.dumps(plan.metadata, sort_keys=True),
                    ),
                )
                connection.execute("DELETE FROM requirements WHERE plan_id=?", (plan.plan_id,))
                connection.executemany(
                    """INSERT INTO requirements(
                        plan_id,requirement_id,description,unit_ids_json
                    ) VALUES (?,?,?,?)""",
                    [
                        (
                            plan.plan_id,
                            requirement.requirement_id,
                            requirement.description,
                            json.dumps(requirement.unit_ids),
                        )
                        for requirement in plan.requirements
                    ],
                )
                if unit_ids:
                    placeholders = ",".join("?" for _ in unit_ids)
                    connection.execute(
                        f"DELETE FROM units WHERE plan_id=? AND unit_id NOT IN ({placeholders})",
                        (plan.plan_id, *sorted(unit_ids)),
                    )
                else:
                    connection.execute("DELETE FROM units WHERE plan_id=?", (plan.plan_id,))
                connection.executemany(
                    """INSERT INTO units(
                        plan_id,unit_id,semantic_hash,objective,status,
                        requirement_ids_json,write_scope_json
                    ) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(plan_id,unit_id) DO UPDATE SET
                        semantic_hash=excluded.semantic_hash,
                        objective=excluded.objective,
                        status=CASE
                            WHEN units.semantic_hash=excluded.semantic_hash
                             AND units.status IN ('completed','done')
                             AND units.evidence_hash IS NOT NULL
                            THEN units.status
                            ELSE excluded.status
                        END,
                        requirement_ids_json=excluded.requirement_ids_json,
                        write_scope_json=excluded.write_scope_json,
                        evidence_hash=CASE
                            WHEN units.semantic_hash=excluded.semantic_hash
                            THEN units.evidence_hash
                            ELSE NULL
                        END,
                        updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                    [
                        (
                            plan.plan_id,
                            unit.unit_id,
                            unit.semantic_hash,
                            unit.objective,
                            unit.status,
                            json.dumps(unit.requirement_ids),
                            json.dumps(unit.write_scope),
                        )
                        for unit in plan.units
                    ],
                )
        event = append_event(
            connection,
            "plan.snapshotted",
            {
                "plan_id": snapshot_payload["plan_id"],
                "version": snapshot_payload["version"],
                "content_hash": snapshot_payload["content_hash"],
                "source": str(path),
                "snapshot": str(snapshot_payload["path"]),
            },
            idempotency_key=args.idempotency_key
            or f"plan-snapshot:{plan.plan_id}:{plan.content_hash}",
            role="Director",
            plan_id=plan.plan_id,
            repository_commit=str(plan.metadata["planned_at_commit"]),
            worktree=str(config.root),
            artifact_hashes=(plan.content_hash,),
        )
    finally:
        connection.close()
    return {"ok": True, "snapshot": snapshot_payload, "event_sequence": event.sequence}


def _cmd_plan_reconcile(args: argparse.Namespace) -> JsonObject:
    _, current = _load_plan(args)
    previous = parse_markdown_plan(Path(args.previous).read_text(encoding="utf-8"))
    reconciled = reconcile_completed_units(previous, current)
    kept = [unit.unit_id for unit in reconciled if unit.status in {"done", "completed"}]
    reopened = [unit.unit_id for unit in reconciled if unit.status == "reopened"]
    return {
        "ok": True,
        "plan_id": current.plan_id,
        "kept_completed": kept,
        "reopened": reopened,
    }


def _unit_prompt(unit: Any) -> str:
    sections = [
        f"Objective: {unit.objective}",
        "Inspect: " + ", ".join(unit.inspect_targets or unit.read_scope),
        "Allowed writes: " + ", ".join(unit.write_scope),
        "Forbidden: " + ", ".join(unit.forbidden_scope),
        "Procedure:\n"
        + "\n".join(f"{index}. {step}" for index, step in enumerate(unit.procedure, 1)),
        "Verification commands:\n" + "\n".join(unit.commands),
        "Acceptance:\n" + "\n".join(unit.acceptance),
        "STOP conditions:\n" + "\n".join(unit.stop_conditions),
        "Completion evidence:\n" + "\n".join(unit.completion_evidence),
    ]
    return "\n\n".join(section for section in sections if section.split(":", 1)[-1].strip())


def _graph_from_plan(path: Path) -> ExecutionGraph:
    plan = parse_markdown_plan(path.read_text(encoding="utf-8"))
    ids = {unit.unit_id for unit in plan.units}
    artifact_producers = {
        artifact: unit.unit_id for unit in plan.units for artifact in unit.output_artifacts
    }
    gate = plan.metadata.get("release_gate", {})
    graph_id = f"G-{plan.plan_id}-v{plan.metadata['plan_version']}"
    # One advisory manager per declared manager_id, never one per worker. Each
    # manager owns a coherent branch and reviews only the units inside it.
    units_by_manager: dict[str, list[str]] = {}
    for unit in plan.units:
        manager_id = unit.manager_id or "M-DEFAULT"
        units_by_manager.setdefault(manager_id, []).append(unit.unit_id)
    manager_ids = sorted(units_by_manager)

    nodes = [
        GraphNode(
            id="Director",
            kind=NodeKind.INTEGRATE,
            title="Graph Coder Director",
            prompt=(
                "Direct, advise, and review branch outputs. Never edit implementation files "
                "and never complete a failed worker's task yourself. Coordinate only through "
                "public swarm operations."
            ),
            role=NodeRole.COMPOSITE,
            authority=NodeAuthority.ADVISORY_ONLY,
            route=RouteSpec(adapter="jcode"),
            children=manager_ids,
            parent_owner=None,
            metadata={
                "graph_id": graph_id,
                "plan_id": plan.plan_id,
                "content_hash": plan.content_hash,
            },
        )
    ]
    nodes.extend(
        GraphNode(
            id=manager_id,
            kind=NodeKind.MANAGE,
            title=f"Manage branch {manager_id}",
            prompt=(
                f"Advise and review the units in {manager_id}. You have no write scope: "
                "you may not edit files, run a repair yourself, or mark work complete "
                "without evidence. Delegate repairs to a worker and escalate what you "
                "cannot resolve."
            ),
            role=NodeRole.COMPOSITE,
            authority=NodeAuthority.ADVISORY_ONLY,
            review_owner="Director",
            parent_owner="Director",
            children=sorted(units_by_manager[manager_id]),
            write_scopes=[],
            route=RouteSpec(adapter="jcode"),
            metadata={"graph_id": graph_id, "reviews": sorted(units_by_manager[manager_id])},
        )
        for manager_id in manager_ids
    )
    for unit in plan.units:
        missing = set(unit.dependencies) - ids
        if missing:
            raise ContractError(f"unit {unit.unit_id} has unknown dependencies: {sorted(missing)}")
        nodes.append(
            GraphNode(
                id=unit.unit_id,
                kind=NodeKind.IMPLEMENT,
                title=unit.title or unit.objective,
                prompt=_unit_prompt(unit),
                unit_ids=[unit.unit_id],
                parent_owner=unit.manager_id or "M-DEFAULT",
                authority=NodeAuthority.IMPLEMENTATION,
                review_owner=unit.manager_id or "M-DEFAULT",
                depends_on=list(unit.dependencies),
                artifact_inputs=[
                    ArtifactRef(
                        name=name,
                        producer=artifact_producers.get(name),
                        external=name not in artifact_producers,
                    )
                    for name in unit.input_artifacts
                ],
                artifact_outputs=[ArtifactRef(name=name) for name in unit.output_artifacts],
                read_scopes=list(unit.read_scope),
                write_scopes=list(unit.write_scope),
                acceptance=list(unit.acceptance),
                review=ReviewPolicy(
                    required=True,
                    reviewers=[unit.manager_id] if unit.manager_id else [],
                    checklist=[*unit.forward_proof, *unit.regression_proof],
                ),
                route=RouteSpec(
                    adapter="jcode",
                    model=unit.primary_route,
                    # Visible, not headless. A headless worker does the work and
                    # never appears in `swarm list`, so the Director cannot see it
                    # start, stall, or finish, and the status roster it is required
                    # to keep becomes fiction. Observability is part of the
                    # contract, so it is the default rather than an option.
                    spawn_mode="visible",
                    capabilities=sorted(str(key) for key in unit.capability_profile),
                ),
                risk=unit.risk,
                limits=Limits(max_attempts=unit.attempt_limit),
                metadata={
                    "semantic_hash": unit.semantic_hash,
                    "requirement_ids": list(unit.requirement_ids),
                    "acceptance_example_ids": list(unit.acceptance_example_ids),
                    "forbidden_scope": list(unit.forbidden_scope),
                    "interfaces": list(unit.interfaces),
                    "fallback_route": unit.fallback_route,
                    "escalation_conditions": list(unit.escalation_conditions),
                    "complexity": unit.complexity,
                },
            )
        )
    frontier = sorted(unit.unit_id for unit in plan.units if not unit.dependencies)
    graph = ExecutionGraph(
        nodes=nodes,
        root_id="Director",
        frontier=frontier,
        max_nodes=int(gate.get("max_total_nodes", 100)),
        max_depth=int(gate.get("max_graph_depth", 6)),
        max_fanout=int(gate.get("max_active_workers", 8)),
        metadata={
            "graph_id": graph_id,
            "plan_id": plan.plan_id,
            "plan_version": plan.metadata["plan_version"],
            "plan_content_hash": plan.content_hash,
        },
    )
    graph.validate()
    return graph


def _cmd_graph_compile(args: argparse.Namespace) -> JsonObject:
    graph = _graph_from_plan(Path(args.plan))
    payload = graph.to_dict()
    config, connection = _database(args)
    graph_id = str(graph.metadata["graph_id"])
    plan_id = str(graph.metadata["plan_id"])
    try:
        with transaction(connection):
            connection.execute("DELETE FROM graph_edges WHERE graph_id=?", (graph_id,))
            connection.execute("DELETE FROM graph_nodes WHERE graph_id=?", (graph_id,))
            connection.executemany(
                """INSERT INTO graph_nodes(
                    graph_id,node_id,node_type,role,status,failure_domain,
                    write_scope_json,semantic_hash,data_json
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        graph_id,
                        node.id,
                        str(node.kind),
                        str(node.role),
                        "ready" if node.id in graph.frontier else "pending",
                        node.failure_domain,
                        json.dumps(node.write_scopes),
                        node.metadata.get("semantic_hash"),
                        json.dumps(node.to_dict(), sort_keys=True),
                    )
                    for node in graph.nodes
                ],
            )
            connection.executemany(
                """INSERT INTO graph_edges(
                    graph_id,source_node_id,target_node_id,artifact_type
                ) VALUES (?,?,?,?)""",
                [
                    (graph_id, dependency, node.id, "dependency")
                    for node in graph.nodes
                    for dependency in node.depends_on
                ],
            )
        event = append_event(
            connection,
            "graph.compiled",
            {"graph_id": graph_id, "nodes": len(graph.nodes), "source": str(args.plan)},
            idempotency_key=args.idempotency_key
            or f"graph-compile:{graph_id}:{graph.metadata['plan_content_hash']}",
            role="Director",
            plan_id=plan_id,
            worktree=str(config.root),
            artifact_hashes=(str(graph.metadata["plan_content_hash"]),),
        )
    finally:
        connection.close()
    if args.output:
        _write_json(args.output, payload)
    return {
        "ok": True,
        "graph": payload,
        "graph_id": graph_id,
        "event_sequence": event.sequence,
        "output": args.output,
    }


def _cmd_graph_validate(args: argparse.Namespace) -> JsonObject:
    graph = ExecutionGraph.load_json(args.file)
    graph.validate()
    return {
        "ok": True,
        "schema_version": graph.schema_version,
        "nodes": len(graph.nodes),
        "frontier": graph.frontier,
    }


def _cmd_route_refresh(args: argparse.Namespace) -> JsonObject:
    config = _config(args)
    cache_path = config.storage_dir / "cache" / "llm-stats" / "models.json"
    client = LLMStatsClient(
        base_url=args.base_url,
        cache_path=cache_path,
        cache_ttl_seconds=args.max_age_hours * 3600,
    )
    result = client.fetch_models_with_cache()
    return {
        "ok": True,
        "source": result.source,
        "stale": result.stale,
        "records": result.records,
        "fetched_at": result.fetched_at,
        "expires_at": result.expires_at,
    }


def _frozenset_fields(payload: dict[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    value = dict(payload)
    for field in fields:
        if field in value:
            value[field] = frozenset(value[field])
    return value


def _registry_from_cache(
    args: argparse.Namespace, payload: dict[str, Any]
) -> tuple[list[ModelCapabilities], list[ProviderCapabilities], JsonObject]:
    """Build router inputs from the cached LLM Stats registry.

    Routing decides how the user's money is spent, so stale evidence is refused
    rather than quietly used. `route refresh` is the fix and the error says so.
    """

    config = _config(args)
    cache_path = config.storage_dir / "cache" / "llm-stats" / "models.json"
    if not cache_path.exists():
        raise RoutingError(
            f"no LLM Stats cache at {cache_path}: run `graph-coder route refresh` first"
        )
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    records = cached.get("records", [])
    age_hours = assert_fresh(
        cached.get("fetched_at"),
        max_age_hours=float(getattr(args, "max_age_hours", 24.0)),
        source=str(cached.get("source", "cache")),
        stale=bool(cached.get("stale", False)),
    )
    registry = payload.get("registry", {})
    build = build_registry(
        records,
        subscription_provider_ids=frozenset(registry.get("subscription_provider_ids", [])),
        context_window_overrides=dict(registry.get("context_window_overrides", {})),
        input_tokens_per_attempt=int(registry.get("input_tokens_per_attempt", 40_000)),
        output_tokens_per_attempt=int(registry.get("output_tokens_per_attempt", 8_000)),
    )
    report = dict(build.report)
    report["evidence_age_hours"] = round(age_hours, 3)
    report["cache_path"] = str(cache_path)
    return build.models, build.providers, report


def _route_from_payload(
    payload: dict[str, Any], args: argparse.Namespace | None = None
) -> tuple[TaskRequirements, RoutingDecision]:
    task = TaskRequirements(
        **_frozenset_fields(
            payload["task"],
            (
                "required_configuration",
                "required_tools",
                "required_modalities",
                "allowed_model_classes",
                "required_policies",
                "allowed_provider_ids",
                "denied_provider_ids",
                "allowed_model_ids",
                "denied_model_ids",
            ),
        )
    )
    registry_report: JsonObject | None = None
    if args is not None and getattr(args, "from_cache", False):
        models, providers, registry_report = _registry_from_cache(args, payload)
    else:
        models = [
            ModelCapabilities(**_frozenset_fields(item, ("tools", "modalities", "policies")))
            for item in payload["models"]
        ]
        providers = [
            ProviderCapabilities(**_frozenset_fields(item, ("configured", "environments")))
            for item in payload["providers"]
        ]
    history = [VerifiedHistory(**item) for item in payload.get("history", [])]
    decision = route_model(task, models, providers, history)
    if registry_report is not None:
        decision.explanation["registry"] = registry_report
    return task, decision


def _decision_payload(decision: Any) -> JsonObject:
    return {
        "selected": decision.selected,
        "candidates": decision.candidates,
        "eliminations": decision.eliminations,
        "explanation": decision.explanation,
    }


def _receipt_for(
    task: TaskRequirements, decision: RoutingDecision, payload: dict[str, Any]
) -> JsonObject:
    """Build the route receipt that must accompany every assignment."""

    return build_route_receipt(
        task,
        decision,
        registry_timestamp=str(
            payload.get("registry_timestamp")
            or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        ),
        evidence_freshness=str(payload.get("evidence_freshness", "cache")),
    )


def _cmd_route_assign(args: argparse.Namespace) -> JsonObject:
    source = _read_json(args.input)
    task, decision = _route_from_payload(source, args)
    receipt = _receipt_for(task, decision, source)
    if decision.selected is None:
        # A refusal still gets a receipt: the disqualification reasons are the
        # whole point of asking.
        return {"ok": False, **_decision_payload(decision), "receipt": receipt}
    plan_id = getattr(args, "plan_id", None) or source.get("plan_id")
    unit_id = (
        getattr(args, "unit_id", None) or source.get("unit_id") or source["task"].get("task_id")
    )
    persisted = False
    event_sequence = None
    if plan_id:
        selected = decision.selected
        source_hash = _canonical_hash(source)
        model_providers = {
            str(model["model_id"]): str(model["provider_id"]) for model in source.get("models", [])
        }
        config, connection = _database(args)
        try:
            with transaction(connection):
                connection.execute(
                    """INSERT INTO routes(
                        plan_id,unit_id,primary_model,primary_provider,
                        fallback_model,fallback_provider,source_hash,
                        explanation_json,data_freshness,expected_passing_cost
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(plan_id,unit_id) DO UPDATE SET
                        primary_model=excluded.primary_model,
                        primary_provider=excluded.primary_provider,
                        fallback_model=excluded.fallback_model,
                        fallback_provider=excluded.fallback_provider,
                        source_hash=excluded.source_hash,
                        explanation_json=excluded.explanation_json,
                        data_freshness=excluded.data_freshness,
                        expected_passing_cost=excluded.expected_passing_cost,
                        created_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                    (
                        str(plan_id),
                        str(unit_id),
                        selected.model.model_id,
                        selected.provider.provider_id,
                        selected.fallback_model_id,
                        model_providers.get(selected.fallback_model_id or ""),
                        source_hash,
                        json.dumps(
                            _decision_payload(decision), default=_json_default, sort_keys=True
                        ),
                        f"{selected.model.evidence_age_hours:.3f}h",
                        selected.expected_passing_cost,
                    ),
                )
            event = append_event(
                connection,
                "route.changed",
                {
                    "primary_model": selected.model.model_id,
                    "primary_provider": selected.provider.provider_id,
                    "fallback_model": selected.fallback_model_id,
                    "source_hash": source_hash,
                },
                idempotency_key=getattr(args, "idempotency_key", None)
                or f"route:{plan_id}:{unit_id}:{source_hash}",
                role="Director",
                plan_id=str(plan_id),
                unit_id=str(unit_id),
                worktree=str(config.root),
            )
            event_sequence = event.sequence
            persisted = True
        finally:
            connection.close()
    payload = {
        "ok": True,
        **_decision_payload(decision),
        "receipt": receipt,
        "persisted": persisted,
        "event_sequence": event_sequence,
    }
    if args.output:
        _write_json(args.output, payload)
    return payload


def _cmd_route_explain(args: argparse.Namespace) -> JsonObject:
    source = _read_json(args.input)
    task, decision = _route_from_payload(source, args)
    payload = {
        "ok": decision.selected is not None,
        **_decision_payload(decision),
        "receipt": _receipt_for(task, decision, source),
    }
    if args.output:
        _write_json(args.output, payload)
    return payload


def _cmd_event_append(args: argparse.Namespace) -> JsonObject:
    payload = _read_json(args.payload_file) if args.payload_file else json.loads(args.payload)
    _, connection = _database(args)
    try:
        event = append_event(
            connection,
            args.type,
            payload,
            idempotency_key=args.idempotency_key,
            role=args.role,
            run_id=args.run_id,
            plan_id=args.plan_id,
            node_id=args.node_id,
            unit_id=args.unit_id,
            attempt_id=args.attempt_id,
            model_receipt=args.model_receipt,
            repository_commit=args.repository_commit,
            worktree=args.worktree,
            artifact_hashes=tuple(args.artifact_hash),
        )
    finally:
        connection.close()
    return {"ok": True, "event": event}


def _cmd_run_status(args: argparse.Namespace) -> JsonObject:
    config = _config(args)
    if not config.database_path.exists():
        return {"ok": True, "initialized": False, "runs": [], "tasks": []}
    connection = connect(config.database_path, config.busy_timeout_ms)
    try:
        migrate(connection)
        ledger_ok, error = verify_chain(connection)
        projections = rebuild_projections(connection)
        runs = [
            dict(row) for row in connection.execute("SELECT * FROM runs ORDER BY updated_at DESC")
        ]
        tasks = [
            dict(row) for row in connection.execute("SELECT * FROM tasks ORDER BY updated_at DESC")
        ]
    finally:
        connection.close()
    return {
        "ok": ledger_ok,
        "initialized": True,
        "ledger_error": error,
        "runs": runs,
        "tasks": tasks,
        "projection": projections,
    }


def _cmd_run_recover(args: argparse.Namespace) -> JsonObject:
    config, connection = _database(args)
    try:
        packet = recover(
            connection,
            role=args.role,
            event_limit=config.packet_event_limit,
            repository_root=config.root,
        )
    finally:
        connection.close()
    return {"ok": True, "recovery": packet}


def _cmd_run_resume(args: argparse.Namespace) -> JsonObject:
    _, connection = _database(args)
    try:
        result = resume_human_required(
            connection,
            node_id=args.node_id,
            decision=args.decision,
            decided_by=args.decided_by,
            target_status=args.status,
        )
    finally:
        connection.close()
    return {"ok": True, "resume": result}


def _cmd_context_build(args: argparse.Namespace) -> JsonObject:
    repository = compact_context(_root(args), limit=args.limit)
    config = _config(args)
    recovery_packet: JsonObject | None = None
    if config.database_path.exists():
        connection = connect(config.database_path, config.busy_timeout_ms)
        try:
            migrate(connection)
            recovery_packet = recover(
                connection,
                role=args.role,
                event_limit=args.limit,
                repository_root=config.root,
            )
        finally:
            connection.close()
    payload = {"ok": True, "role": args.role, "repository": repository, "state": recovery_packet}
    if args.output:
        _write_json(args.output, payload)
    return payload


def _cmd_route_set(args: argparse.Namespace) -> JsonObject:
    """Write a route onto graph nodes without hand-editing the graph file.

    This exists because `jcode emit` preflight could say "MODEL_ROUTING was
    skipped" and then offer nothing to fix it with. A run had to hand-edit
    `graph.json`, and could not, because every node carried the identical line
    `"model": "local"` and a text edit cannot target one of three identical
    occurrences. It wrote a throwaway Python script instead. That is a tool gap,
    not a user error.

    The evidence basis is recorded on the node, so a route set from a harness
    model list is never mistaken later for one the router derived.
    """

    path = Path(args.graph)
    graph = ExecutionGraph.load_json(path)
    nodes = graph.by_id()

    targets = (
        list(args.node)
        if args.node
        else [
            node.id
            for node in graph.nodes
            if node.id != graph.root_id
            and node.kind != NodeKind.MANAGE
            and (node.route.model or "") in PLACEHOLDER_ROUTES
        ]
    )
    unknown = [node_id for node_id in targets if node_id not in nodes]
    if unknown:
        raise ContractError(f"no such node in {path}: {', '.join(sorted(unknown))}")
    if not targets:
        raise ContractError(
            f"no nodes to set in {path}: name them with --node, or leave --node off "
            "to fill every node still carrying a placeholder route"
        )

    updated: list[dict[str, Any]] = []
    for node_id in targets:
        node = nodes[node_id]
        previous = node.route.model
        node.route = replace(
            node.route,
            model=args.model,
            spawn_mode=node.route.spawn_mode or "visible",
        )
        node.metadata["route_evidence"] = args.evidence
        if args.fallback:
            node.metadata["fallback_route"] = args.fallback
        updated.append(
            {
                "node_id": node_id,
                "previous_model": previous,
                "model": args.model,
                "fallback_route": node.metadata.get("fallback_route"),
                "route_evidence": args.evidence,
            }
        )

    graph.validate()
    graph.dump_json(path)
    payload: JsonObject = {
        "ok": True,
        "graph": str(path),
        "updated": updated,
        "route_evidence": args.evidence,
    }
    if args.evidence != "llm_stats":
        payload["degraded"] = (
            f"routes were set from `{args.evidence}`, not from a router decision over "
            "refreshed LLM Stats evidence. There is no benchmark score behind these "
            "choices, so record the basis in the plan and surface the degradation at "
            "approval rather than presenting them as routed."
        )
    return payload


def _cmd_jcode_emit(args: argparse.Namespace) -> JsonObject:
    graph = ExecutionGraph.load_json(args.graph)
    adapter = JCodeAdapter()
    payload = {
        "ok": True,
        "compatibility": adapter.compatibility(),
        # Read this before dispatching. `ready_to_dispatch: false` means the graph
        # will run, but not the run that was approved.
        "preflight": adapter.preflight(graph),
        "operations": [operation.to_dict() for operation in adapter.operation_bundle(graph)],
        "report_schema": load_schema("worker_report"),
    }
    if args.output:
        _write_json(args.output, payload)
    return payload


def _cmd_terminal_open(args: argparse.Namespace) -> JsonObject:
    layout = build_windows_terminal_layout(
        _root(args), graph_coder_command=args.graph_coder_command
    )
    processes = open_windows_terminal(layout, execute=args.execute)
    return {
        "ok": True,
        "executed": args.execute,
        "commands": layout.as_lists(),
        "process_ids": [process.pid for process in processes],
    }


def _add_root_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", help="project root; defaults to the current directory")
    parser.add_argument("--config", help="explicit Graph Coder TOML configuration path")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")


def _set_handler(parser: argparse.ArgumentParser, handler: Handler) -> None:
    parser.set_defaults(handler=handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graph-coder", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_root_options(parser)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize durable Graph Coder state")
    init.add_argument("--idempotency-key")
    _set_handler(init, _cmd_init)
    _set_handler(
        commands.add_parser("inspect", help="inspect repository and adapter compatibility"),
        _cmd_inspect,
    )

    plan = commands.add_parser("plan", help="canonical plan operations").add_subparsers(
        dest="plan_command", required=True
    )
    plan_status = plan.add_parser("status", help="show plan and ledger status")
    plan_status.add_argument("--file")
    _set_handler(plan_status, _cmd_plan_status)
    for name, handler in (("validate", _cmd_plan_validate), ("snapshot", _cmd_plan_snapshot)):
        command = plan.add_parser(name)
        command.add_argument("--file", required=True)
        if name == "snapshot":
            command.add_argument("--idempotency-key")
        _set_handler(command, handler)
    reconcile = plan.add_parser("reconcile")
    reconcile.add_argument("--file", required=True)
    reconcile.add_argument("--previous", required=True)
    _set_handler(reconcile, _cmd_plan_reconcile)

    graph = commands.add_parser("graph", help="typed DAG operations").add_subparsers(
        dest="graph_command", required=True
    )
    compile_command = graph.add_parser("compile")
    compile_command.add_argument("--plan", required=True)
    compile_command.add_argument("--output")
    compile_command.add_argument("--idempotency-key")
    _set_handler(compile_command, _cmd_graph_compile)
    validate_graph = graph.add_parser("validate")
    validate_graph.add_argument("--file", required=True)
    _set_handler(validate_graph, _cmd_graph_validate)

    route = commands.add_parser("route", help="deterministic routing operations").add_subparsers(
        dest="route_command", required=True
    )
    refresh = route.add_parser("refresh")
    refresh.add_argument("--base-url", default=DEFAULT_API_BASE)
    refresh.add_argument("--max-age-hours", type=float, default=24.0)
    _set_handler(refresh, _cmd_route_refresh)

    route_set = route.add_parser(
        "set", help="write a route onto graph nodes without editing the graph by hand"
    )
    route_set.add_argument("--graph", required=True)
    route_set.add_argument(
        "--node",
        action="append",
        help="node id to set; repeatable. Omit to fill every node still carrying a "
        "placeholder route.",
    )
    route_set.add_argument("--model", required=True)
    route_set.add_argument("--fallback", help="fallback model recorded for retry")
    route_set.add_argument(
        "--evidence",
        default="harness_model_list",
        choices=["harness_model_list", "operator", "llm_stats"],
        help="what the choice rests on; anything but llm_stats is recorded as degraded",
    )
    _set_handler(route_set, _cmd_route_set)
    for name, handler in (("assign", _cmd_route_assign), ("explain", _cmd_route_explain)):
        command = route.add_parser(name)
        command.add_argument("--input", required=True)
        command.add_argument("--output")
        command.add_argument(
            "--from-cache",
            action="store_true",
            help="build the model registry from the LLM Stats cache instead of --input models",
        )
        command.add_argument(
            "--max-age-hours",
            type=float,
            default=24.0,
            help="refuse to route on LLM Stats evidence older than this",
        )
        if name == "assign":
            command.add_argument("--plan-id")
            command.add_argument("--unit-id")
            command.add_argument("--idempotency-key")
        _set_handler(command, handler)

    event = commands.add_parser("event", help="append-only ledger operations").add_subparsers(
        dest="event_command", required=True
    )
    append = event.add_parser("append")
    append.add_argument("--type", required=True)
    group = append.add_mutually_exclusive_group(required=True)
    group.add_argument("--payload")
    group.add_argument("--payload-file")
    append.add_argument("--role")
    append.add_argument("--idempotency-key")
    append.add_argument("--run-id")
    append.add_argument("--plan-id")
    append.add_argument("--node-id")
    append.add_argument("--unit-id")
    append.add_argument("--attempt-id")
    append.add_argument("--model-receipt")
    append.add_argument("--repository-commit")
    append.add_argument("--worktree")
    append.add_argument("--artifact-hash", action="append", default=[])
    _set_handler(append, _cmd_event_append)

    run = commands.add_parser("run", help="execution status and recovery").add_subparsers(
        dest="run_command", required=True
    )
    _set_handler(run.add_parser("status"), _cmd_run_status)
    run_recover = run.add_parser("recover")
    run_recover.add_argument("--role", default="Director")
    _set_handler(run_recover, _cmd_run_recover)
    run_resume = run.add_parser("resume", help="record a human decision on a human_required branch")
    run_resume.add_argument("--node-id", required=True)
    run_resume.add_argument("--decision", required=True, help="what the human decided, and why")
    run_resume.add_argument("--decided-by", default="user")
    run_resume.add_argument("--status", default="ready", choices=("ready", "cancelled", "failed"))
    _set_handler(run_resume, _cmd_run_resume)

    context = commands.add_parser("context", help="role-specific context packets").add_subparsers(
        dest="context_command", required=True
    )
    build = context.add_parser("build")
    build.add_argument("--role", default="Director")
    build.add_argument("--limit", type=int, default=20)
    build.add_argument("--output")
    _set_handler(build, _cmd_context_build)

    jcode = commands.add_parser("jcode", help="JCode adapter operations").add_subparsers(
        dest="jcode_command", required=True
    )
    emit = jcode.add_parser("emit")
    emit.add_argument("--graph", required=True)
    emit.add_argument("--output")
    _set_handler(emit, _cmd_jcode_emit)

    terminal = commands.add_parser("terminal", help="Windows Terminal organization").add_subparsers(
        dest="terminal_command", required=True
    )
    terminal_open = terminal.add_parser("open")
    terminal_open.add_argument("--graph-coder-command", default="graph-coder")
    terminal_open.add_argument(
        "--execute", action="store_true", help="open tabs; default is a safe dry run"
    )
    _set_handler(terminal_open, _cmd_terminal_open)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
        _emit(result, pretty=not args.compact)
        return 0 if result.get("ok", True) else 2
    except (
        GraphCoderError,
        ValueError,
        OSError,
        sqlite3.Error,
        json.JSONDecodeError,
        # A hand-authored --input payload is the normal way to call `route
        # assign`, so a missing key or an unexpected field is user error, not a
        # crash. Without these, argument shapes escape as tracebacks and exit 1,
        # breaking the contract that every failure is JSON with exit 2.
        KeyError,
        TypeError,
    ) as exc:
        message = str(exc)
        if isinstance(exc, KeyError):
            message = f"missing required field {message}"
        _emit({"ok": False, "error": type(exc).__name__, "message": message}, pretty=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
