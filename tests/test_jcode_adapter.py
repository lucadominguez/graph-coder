from __future__ import annotations

from pathlib import Path

import pytest

from graph_coder.adapters.jcode import JCodeAdapter, detect_jcode_version
from graph_coder.errors import CompatibilityError
from graph_coder.graph import ExecutionGraph, GraphNode, NodeKind, ReviewPolicy, RouteSpec


def sample_graph(capabilities: list[str] | None = None, model: str | None = None) -> ExecutionGraph:
    """A Director, one advisory manager, and the workers it reviews."""

    worker_route = RouteSpec(model=model)
    return ExecutionGraph(
        nodes=[
            GraphNode(
                id="Director",
                kind="explore",
                role="composite",
                authority="advisory_only",
                title="Director",
                children=["manager"],
                route=RouteSpec(capabilities=capabilities or []),
            ),
            GraphNode(
                id="manager",
                kind="manage",
                role="composite",
                authority="advisory_only",
                title="Manage the change branch",
                depends_on=["Director"],
                review_owner="Director",
                children=["explore", "implement", "verify"],
            ),
            GraphNode(
                id="explore",
                kind="spike",
                title="Explore unknowns",
                depends_on=["manager"],
                prompt="Find constraints",
                read_scopes=["src"],
                artifact_outputs=[{"name": "notes"}],
                acceptance=["constraints listed"],
                review=ReviewPolicy(required=True, checklist=["evidence cited"]),
                review_owner="manager",
                route=worker_route,
            ),
            GraphNode(
                id="implement",
                kind="implement",
                title="Implement change",
                depends_on=["explore"],
                artifact_inputs=[{"name": "notes", "producer": "explore"}],
                write_scopes=["src/app.py"],
                acceptance=["tests pass"],
                review_owner="manager",
                route=worker_route,
            ),
            GraphNode(
                id="verify",
                kind="verify",
                title="Run the compatibility suite",
                depends_on=["implement"],
                read_scopes=["src/app.py"],
                acceptance=["compatibility suite passes"],
                review_owner="manager",
                route=worker_route,
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


def test_maps_dispatchable_kinds_to_native_jcode_kinds() -> None:
    adapter = JCodeAdapter(version_output="jcode v0.55.0")
    dispatchable = [kind for kind in NodeKind if kind is not NodeKind.MANAGE]

    assert {kind.value: adapter.native_kind(kind) for kind in dispatchable} == {
        "explore": "explore",
        "spike": "explore",
        "implement": "implement",
        "verify": "verify",
        "integrate": "synthesize",
        "repair": "fix",
        "release": "synthesize",
    }


def test_there_is_no_review_kind_to_map() -> None:
    with pytest.raises(ValueError, match="not a valid NodeKind"):
        NodeKind("review")


def test_managers_are_not_dispatched_as_swarm_tasks() -> None:
    adapter = JCodeAdapter(version_output="jcode v0.55.0")

    with pytest.raises(CompatibilityError, match="control-plane"):
        adapter.native_kind(NodeKind.MANAGE)

    bundle = adapter.task_graph_bundle(sample_graph())
    dispatched = [node["id"] for node in bundle.arguments["nodes"]]
    assert "manager" not in dispatched
    assert "Director" not in dispatched


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
        "verify",
    ]
    assert task_graph.arguments["mode"] == "light"
    assert task_graph.arguments["nodes"][0]["kind"] == "explore"
    assert task_graph.arguments["nodes"][1]["kind"] == "implement"
    assert task_graph.to_dict()["tool"] == "swarm"

    assert run_plan.action == "run_plan"
    assert run_plan.arguments["background"] is True
    assert run_plan.arguments["root_director"] == "Director"
    assert "foreground JCode Director" in run_plan.arguments["prompt"]


def test_manager_metadata_records_advisory_authority_and_review_assignments() -> None:
    adapter = JCodeAdapter(version_output="jcode v0.55.0")
    metadata = adapter.task_graph_bundle(sample_graph()).arguments["metadata"]

    managers = metadata["managers"]
    assert [manager["manager_id"] for manager in managers] == ["manager"]
    assert managers[0]["authority"] == "advisory_only"
    assert managers[0]["write_scopes"] == []
    assert set(managers[0]["reviews"]) == {"explore", "implement", "verify"}
    assert metadata["review_assignments"] == {
        "explore": "manager",
        "implement": "manager",
        "verify": "manager",
    }


def test_every_worker_prompt_names_its_manager_and_review_contract() -> None:
    adapter = JCodeAdapter(version_output="jcode v0.55.0")
    for task in adapter.task_graph_bundle(sample_graph()).arguments["nodes"]:
        assert "Submit your report to manager manager for review." in task["content"]
        assert "you do not mark yourself complete" in task["content"]
        assert task["metadata"]["review_owner"] == "manager"
        assert task["metadata"]["authority"] == "implementation"


def test_every_task_carries_a_visible_spawn_mode() -> None:
    """A headless or inline worker does the work and never appears in `swarm list`,
    so the Director cannot monitor it and the status roster becomes fiction. The
    adapter emits the mode rather than leaving the harness to pick its own."""

    adapter = JCodeAdapter(version_output="jcode v0.55.0")
    for task in adapter.task_graph_bundle(sample_graph()).arguments["nodes"]:
        assert task["spawn_mode"] == "visible"


def test_preflight_flags_an_unrouted_graph_rather_than_dispatching_it() -> None:
    """The observed failure: MODEL_ROUTING was skipped, every packet shipped the
    example plan's `local` placeholder, and the workers silently ran on the
    harness default. Reported, not raised, so the unrouted example still emits."""

    adapter = JCodeAdapter(version_output="jcode v0.55.0")
    report = adapter.preflight(sample_graph(model="local"))
    assert report["ready_to_dispatch"] is False
    assert report["unrouted_nodes"]
    assert "MODEL_ROUTING was skipped" in report["warnings"][0]

    routed = adapter.preflight(sample_graph(model="claude-sonnet-5"))
    assert routed["ready_to_dispatch"] is True
    assert routed["unrouted_nodes"] == []
    assert routed["warnings"] == []


def test_prompts_and_reports_preserve_acceptance_review_and_scope_context() -> None:
    graph = sample_graph()
    adapter = JCodeAdapter(version_output="jcode v0.55.0")
    task = adapter.task_graph_bundle(graph).arguments["nodes"][0]

    assert "constraints listed" in task["content"]
    assert "evidence cited" in task["content"]
    assert "Read scopes: ['src']" in task["content"]
    assert task["metadata"]["acceptance"] == ["constraints listed"]
    assert task["metadata"]["review_required"] is True
    assert task["metadata"]["graph_coder_kind"] == "spike"


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


def test_fallback_route_reaches_the_emitted_task() -> None:
    """It was compiled into node metadata and then never emitted, so a retry meant
    re-deriving the model by hand. Surfaced next to `model` so "respawn with the
    fallback" needs no lookup."""

    graph = sample_graph(model="qwen/qwen3.7-flash")
    for node in graph.nodes:
        if node.id == "implement":
            node.metadata["fallback_route"] = "google:gemini-3-flash-preview"
        if node.id == "verify":
            node.metadata["fallback_route"] = "local"

    tasks = {
        task["id"]: task
        for task in JCodeAdapter(version_output="jcode v0.55.0")
        .task_graph_bundle(graph)
        .arguments["nodes"]
    }

    assert tasks["implement"]["fallback_model"] == "google:gemini-3-flash-preview"
    # A placeholder is not a fallback, so it is withheld rather than offered.
    assert "fallback_model" not in tasks["verify"]
    assert "fallback_model" not in tasks["explore"]


def test_worker_packets_require_visible_progress() -> None:
    """A running worker's transcript cannot be read, so the filesystem is the only
    progress signal. A worker that buffers output to the end looks identical to one
    that is stuck, which cost a real run two minutes."""

    adapter = JCodeAdapter(version_output="jcode v0.55.0")
    for task in adapter.task_graph_bundle(sample_graph()).arguments["nodes"]:
        content = task["content"]
        assert f".graph-coder/progress/{task['id']}.log" in content
        assert "the only path outside that scope you may touch" in content
        assert "transcript cannot be read while you run" in content


def test_packet_progress_rules_follow_the_units_declared_contract() -> None:
    """A single-pass unit and a per-item unit need opposite instructions, and
    judging both by one rule produces false alarms on one and blindness on the
    other. The cadence comes from the plan, not from a fixed default."""

    graph = sample_graph()
    for node in graph.nodes:
        if node.id == "implement":
            node.metadata["progress_contract"] = {
                "checkpoint_every": "each detail page",
                "writes_incrementally": True,
                "command_timeout_seconds": 90,
            }
        if node.id == "verify":
            node.metadata["progress_contract"] = {
                "checkpoint_every": "single pass",
                "writes_incrementally": False,
                "command_timeout_seconds": 30,
            }

    tasks = {
        task["id"]: task["content"]
        for task in JCodeAdapter(version_output="jcode v0.55.0")
        .task_graph_bundle(graph)
        .arguments["nodes"]
    }

    assert "cadence: each detail page" in tasks["implement"]
    assert "Write your output incrementally" in tasks["implement"]
    assert "No single command may run longer than 90 seconds" in tasks["implement"]

    assert "cadence: single pass" in tasks["verify"]
    assert "writes its output once, in a single pass" in tasks["verify"]
    assert "No single command may run longer than 30 seconds" in tasks["verify"]


def test_packet_states_the_output_contract_as_a_gate() -> None:
    """A unit whose only gate is acceptance prose can be satisfied by a scraper
    that returns nothing: the code ran, the file exists, and no criterion said the
    file had to contain anything."""

    graph = sample_graph()
    for node in graph.nodes:
        if node.id == "implement":
            node.metadata["output_contract"] = [
                "Every record carries title, price, and url, all non-empty.",
                "At least 20 records from one catalogue page.",
            ]

    tasks = {
        task["id"]: task["content"]
        for task in JCodeAdapter(version_output="jcode v0.55.0")
        .task_graph_bundle(graph)
        .arguments["nodes"]
    }

    assert "Every record carries title, price, and url" in tasks["implement"]
    assert "A file that exists but is empty or malformed is a failure" in tasks["implement"]
    # A unit with no declared contract is told to escalate, not to invent one.
    assert "none declared. Escalate rather than guessing one" in tasks["explore"]
