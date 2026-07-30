from __future__ import annotations

from pathlib import Path

import pytest

from graph_coder.adapters.jcode import JCodeAdapter, detect_jcode_version
from graph_coder.errors import CompatibilityError
from graph_coder.graph import ExecutionGraph, GraphNode, NodeKind, ReviewPolicy, RouteSpec


def sample_graph(capabilities: list[str] | None = None) -> ExecutionGraph:
    return ExecutionGraph(
        nodes=[
            GraphNode(
                id="Director",
                kind="explore",
                role="composite",
                title="Director",
                children=["explore", "implement", "review"],
                route=RouteSpec(capabilities=capabilities or []),
            ),
            GraphNode(
                id="explore",
                kind="spike",
                title="Explore unknowns",
                depends_on=["Director"],
                prompt="Find constraints",
                read_scopes=["src"],
                artifact_outputs=[{"name": "notes"}],
                acceptance=["constraints listed"],
                review=ReviewPolicy(required=True, checklist=["evidence cited"]),
            ),
            GraphNode(
                id="implement",
                kind="implement",
                title="Implement change",
                depends_on=["explore"],
                artifact_inputs=[{"name": "notes", "producer": "explore"}],
                write_scopes=["src/app.py"],
                acceptance=["tests pass"],
            ),
            GraphNode(
                id="review",
                kind="review",
                title="Review change",
                depends_on=["implement"],
                read_scopes=["src/app.py"],
                acceptance=["review complete"],
            ),
        ]
    )


def test_detects_version_from_fixture_and_output() -> None:
    fixture = Path("tests/fixtures/jcode/version.txt")
    adapter = JCodeAdapter.from_fixture(fixture)

    assert adapter.detect_version() == "0.55.0-dev"
    assert detect_jcode_version("Jcode v0.56.1 (clean)") == "0.56.1"
    assert adapter.compatibility() == {
        "adapter": "jcode",
        "detected_version": "0.55.0-dev",
        "target_version": "0.55.0",
        "compatible": True,
        "transport": "public swarm tool operations",
        "private_socket_dependency": False,
    }


def test_maps_all_portable_kinds_to_native_jcode_kinds() -> None:
    adapter = JCodeAdapter(version_output="jcode v0.55.0")

    assert {kind.value: adapter.native_kind(kind) for kind in NodeKind} == {
        "explore": "explore",
        "spike": "explore",
        "implement": "implement",
        "verify": "verify",
        "integrate": "synthesize",
        "review": "verify",
        "repair": "fix",
        "release": "synthesize",
    }


def test_emits_director_mediated_task_graph_and_background_run_plan() -> None:
    graph = sample_graph()
    adapter = JCodeAdapter(version_output="jcode v0.55.0")

    task_graph, run_plan = adapter.operation_bundle(graph)

    assert task_graph.action == "task_graph"
    assert task_graph.arguments["metadata"]["root_id"] == "Director"
    assert task_graph.arguments["metadata"]["director_preserved"] is True
    assert [node["id"] for node in task_graph.arguments["nodes"]] == [
        "explore",
        "implement",
        "review",
    ]
    assert task_graph.arguments["mode"] == "light"
    assert task_graph.arguments["nodes"][0]["depends_on"] == []
    assert task_graph.arguments["nodes"][0]["kind"] == "explore"
    assert task_graph.arguments["nodes"][1]["kind"] == "implement"
    assert task_graph.to_dict()["tool"] == "swarm"

    assert run_plan.action == "run_plan"
    assert run_plan.arguments["background"] is True
    assert run_plan.arguments["root_director"] == "Director"
    assert "foreground JCode Director" in run_plan.arguments["prompt"]


def test_prompts_and_reports_preserve_acceptance_review_and_scope_context() -> None:
    graph = sample_graph()
    adapter = JCodeAdapter(version_output="jcode v0.55.0")
    task = adapter.task_graph_bundle(graph).arguments["nodes"][0]

    assert "constraints listed" in task["content"]
    assert "evidence cited" in task["content"]
    assert "Read scopes: ['src']" in task["content"]
    assert task["metadata"]["acceptance"] == ["constraints listed"]
    assert task["metadata"]["review_required"] is True


def test_unsupported_capabilities_are_explicitly_rejected() -> None:
    graph = sample_graph(capabilities=["private_socket", "payments"])
    adapter = JCodeAdapter(version_output="jcode v0.55.0")

    with pytest.raises(CompatibilityError, match="payments, private_socket"):
        adapter.operation_bundle(graph)


def test_adapter_source_has_no_private_socket_dependency() -> None:
    source = Path("src/graph_coder/adapters/jcode.py").read_text(encoding="utf-8").lower()

    assert "websocket" not in source
    assert "unix socket" not in source
    assert "named pipe" not in source
