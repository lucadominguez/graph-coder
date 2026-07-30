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
