from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from graph_coder.cli import build_parser, main
from graph_coder.events import verify_chain

FIXTURES = Path(__file__).parent / "fixtures"


def test_parser_exposes_complete_command_surface() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    for command in (
        "init",
        "inspect",
        "plan",
        "graph",
        "route",
        "event",
        "run",
        "context",
        "jcode",
        "terminal",
    ):
        assert command in help_text


def test_terminal_open_defaults_to_dry_run(tmp_path, capsys) -> None:
    result = main(["--root", str(tmp_path), "terminal", "open"])
    output = capsys.readouterr().out
    assert result == 0
    assert '"executed": false' in output
    assert "wt.exe" in output


def test_init_is_idempotent(tmp_path, capsys) -> None:
    assert main(["--root", str(tmp_path), "init", "--idempotency-key", "same"]) == 0
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "init", "--idempotency-key", "same"]) == 0
    output = capsys.readouterr().out
    assert '"event_sequence": 1' in output


def test_cli_persists_plan_graph_route_and_emits_jcode_bundle(tmp_path, capsys) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text(
        (FIXTURES / "plans" / "valid_plan.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    graph_path = tmp_path / "graph.json"
    jcode_path = tmp_path / "jcode.json"
    route_path = tmp_path / "route.json"
    route_path.write_text(
        (FIXTURES / "routing" / "cli_input.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    root_args = ["--root", str(tmp_path)]
    assert main([*root_args, "init"]) == 0
    assert (
        main(
            [
                *root_args,
                "event",
                "append",
                "--type",
                "plan.approved",
                "--payload",
                "{}",
                "--role",
                "Director",
                "--plan-id",
                "P-demo",
                "--repository-commit",
                "abc123",
                "--artifact-hash",
                "plan-hash",
            ]
        )
        == 0
    )
    assert main([*root_args, "plan", "validate", "--file", str(plan_path)]) == 0
    assert main([*root_args, "plan", "snapshot", "--file", str(plan_path)]) == 0
    assert (
        main(
            [
                *root_args,
                "graph",
                "compile",
                "--plan",
                str(plan_path),
                "--output",
                str(graph_path),
            ]
        )
        == 0
    )
    explain_root = tmp_path / "read-only-explain"
    assert (
        main(
            [
                "--root",
                str(explain_root),
                "route",
                "explain",
                "--input",
                str(route_path),
            ]
        )
        == 0
    )
    assert not (explain_root / ".graph-coder" / "state.db").exists()
    assert main([*root_args, "graph", "validate", "--file", str(graph_path)]) == 0
    assert (
        main(
            [
                *root_args,
                "route",
                "assign",
                "--input",
                str(route_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                *root_args,
                "jcode",
                "emit",
                "--graph",
                str(graph_path),
                "--output",
                str(jcode_path),
            ]
        )
        == 0
    )
    assert main([*root_args, "run", "recover"]) == 0
    assert main([*root_args, "run", "status"]) == 0
    assert main([*root_args, "context", "build"]) == 0
    capsys.readouterr()

    connection = sqlite3.connect(tmp_path / ".graph-coder" / "state.db")
    connection.row_factory = sqlite3.Row
    try:
        assert connection.execute("SELECT count(*) FROM projects").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM plan_versions").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM requirements").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM units").fetchone()[0] == 1
        # Director, one advisory manager, and the single worker it reviews.
        assert connection.execute("SELECT count(*) FROM graph_nodes").fetchone()[0] == 3
        manager = connection.execute(
            "SELECT node_id,node_type,write_scope_json FROM graph_nodes WHERE node_type='manage'"
        ).fetchone()
        assert manager["node_id"] == "M-CONTRACTS"
        assert manager["write_scope_json"] == "[]"
        assert connection.execute("SELECT primary_model FROM routes").fetchone()[0] == "open/test"
        approved = connection.execute(
            """SELECT plan_id,repository_commit,artifact_hashes_json
            FROM events WHERE event_type='plan.approved'"""
        ).fetchone()
        assert tuple(approved) == ("P-demo", "abc123", '["plan-hash"]')
        assert verify_chain(connection) == (True, None)
    finally:
        connection.close()

    bundle = json.loads(jcode_path.read_text(encoding="utf-8"))
    operations = bundle["operations"]
    assert all(
        operation.get("params", {}).get("nodes", [{}])[0].get("id") != "Director"
        for operation in operations
    )
    assert any(operation["action"] == "run_plan" for operation in operations)


def test_malformed_route_input_is_a_refusal_not_a_traceback(tmp_path, capsys) -> None:
    # A hand-authored payload is the normal way to call `route assign`, so the
    # two mistakes it invites -- a missing key and an unexpected field -- must
    # come back as JSON with exit 2, like every other failure.
    assert main(["--root", str(tmp_path), "init"]) == 0
    capsys.readouterr()

    missing_task = tmp_path / "missing-task.json"
    missing_task.write_text(json.dumps({"plan_id": "P-demo"}), encoding="utf-8")
    assert main(["--root", str(tmp_path), "route", "assign", "--input", str(missing_task)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "KeyError"
    assert "missing required field" in payload["message"]

    unknown_field = tmp_path / "unknown-field.json"
    unknown_field.write_text(
        json.dumps({"task": {"task_id": "IU-demo", "role": "worker", "risk": "medium"}}),
        encoding="utf-8",
    )
    assert main(["--root", str(tmp_path), "route", "assign", "--input", str(unknown_field)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "TypeError"
    assert "risk" in payload["message"]


def test_shipped_example_plan_validates_and_compiles(tmp_path, capsys) -> None:
    # The README quickstart runs these exact commands against these exact files.
    # It shipped once pointing at a plan that did not exist, so the example is a
    # test fixture now, not just documentation.
    repository_root = Path(__file__).resolve().parent.parent
    plan_path = repository_root / "docs" / "plans" / "example-plan.md"
    route_request = repository_root / "docs" / "plans" / "example-route-request.json"
    assert plan_path.exists(), "the README quickstart points at this plan"
    assert route_request.exists(), "the README routing example points at this request"

    assert main(["--root", str(tmp_path), "init"]) == 0
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "plan", "validate", "--file", str(plan_path)]) == 0
    assert json.loads(capsys.readouterr().out)["defects"] == []
    assert main(["--root", str(tmp_path), "plan", "snapshot", "--file", str(plan_path)]) == 0
    capsys.readouterr()

    graph_path = tmp_path / "graph.json"
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "graph",
                "compile",
                "--plan",
                str(plan_path),
                "--output",
                str(graph_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "graph", "validate", "--file", str(graph_path)]) == 0
    capsys.readouterr()

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert set(nodes) == {
        "Director",
        "M-API",
        "M-STORAGE",
        "IU-MIGRATION",
        "IU-STORE",
        "IU-SCHEMA",
        "IU-ENDPOINT",
    }
    for manager_id in ("M-API", "M-STORAGE"):
        assert nodes[manager_id]["kind"] == "manage"
        assert nodes[manager_id]["authority"] == "advisory_only"
        assert nodes[manager_id]["write_scopes"] == []
    assert nodes["IU-ENDPOINT"]["review_owner"] == "M-API"
    assert nodes["IU-STORE"]["review_owner"] == "M-STORAGE"

    # The routing example must name capabilities the registry can actually
    # produce, or it refuses on evidence rather than demonstrating a route.
    request = json.loads(route_request.read_text(encoding="utf-8"))
    assert set(request["task"]["required_tools"]) <= {"edit", "bash", "read"}


def test_route_set_fixes_placeholder_routes_without_hand_editing(tmp_path, capsys) -> None:
    """The gap this closes: preflight said MODEL_ROUTING was skipped and offered no
    way to fix it. A run had to hand-edit graph.json, could not target one of three
    identical `"model": "local"` lines with a text edit, and wrote a throwaway
    script instead."""

    repository_root = Path(__file__).resolve().parent.parent
    plan_path = repository_root / "docs" / "plans" / "example-plan.md"
    graph_path = tmp_path / "graph.json"

    assert main(["--root", str(tmp_path), "init"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "graph",
                "compile",
                "--plan",
                str(plan_path),
                "--output",
                str(graph_path),
            ]
        )
        == 0
    )
    capsys.readouterr()

    # Before: every node unrouted, so dispatch is refused.
    assert main(["--root", str(tmp_path), "jcode", "emit", "--graph", str(graph_path)]) == 0
    before = json.loads(capsys.readouterr().out)["preflight"]
    assert before["ready_to_dispatch"] is False
    assert len(before["unrouted_nodes"]) == 4

    # One command fills every placeholder, which a text edit could not do.
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "route",
                "set",
                "--graph",
                str(graph_path),
                "--model",
                "qwen/qwen3.7-flash",
                "--fallback",
                "google:gemini-3-flash-preview",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert {entry["node_id"] for entry in result["updated"]} == set(before["unrouted_nodes"])
    assert all(entry["previous_model"] == "local" for entry in result["updated"])
    # Degraded evidence is recorded, never passed off as a router decision.
    assert result["route_evidence"] == "harness_model_list"
    assert "not from a router decision" in result["degraded"]

    # After: dispatchable, with the fallback carried through to the packet.
    assert main(["--root", str(tmp_path), "jcode", "emit", "--graph", str(graph_path)]) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["preflight"]["ready_to_dispatch"] is True
    assert emitted["preflight"]["unrouted_nodes"] == []
    for task in emitted["operations"][0]["arguments"]["nodes"]:
        assert task["model"] == "qwen/qwen3.7-flash"
        assert task["fallback_model"] == "google:gemini-3-flash-preview"


def test_route_set_targets_one_node_and_refuses_unknown_ids(tmp_path, capsys) -> None:
    repository_root = Path(__file__).resolve().parent.parent
    plan_path = repository_root / "docs" / "plans" / "example-plan.md"
    graph_path = tmp_path / "graph.json"

    assert main(["--root", str(tmp_path), "init"]) == 0
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "graph",
                "compile",
                "--plan",
                str(plan_path),
                "--output",
                str(graph_path),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "route",
                "set",
                "--graph",
                str(graph_path),
                "--node",
                "IU-STORE",
                "--model",
                "anthropic:claude-sonnet-5",
                "--evidence",
                "operator",
            ]
        )
        == 0
    )
    updated = json.loads(capsys.readouterr().out)["updated"]
    assert [entry["node_id"] for entry in updated] == ["IU-STORE"]

    # The other three keep their placeholder, so the fix stays scoped.
    assert main(["--root", str(tmp_path), "jcode", "emit", "--graph", str(graph_path)]) == 0
    assert json.loads(capsys.readouterr().out)["preflight"]["unrouted_nodes"] == [
        "IU-ENDPOINT",
        "IU-MIGRATION",
        "IU-SCHEMA",
    ]

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "route",
                "set",
                "--graph",
                str(graph_path),
                "--node",
                "IU-NOPE",
                "--model",
                "anthropic:claude-sonnet-5",
            ]
        )
        == 2
    )
    refusal = json.loads(capsys.readouterr().out)
    assert refusal["ok"] is False
    assert "no such node" in refusal["message"]
