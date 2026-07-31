from __future__ import annotations

import pytest

from graph_coder.errors import ContractError
from graph_coder.graph import (
    ArtifactRef,
    ExecutionGraph,
    GraphNode,
    Limits,
    NodeKind,
    NodeRole,
    ReviewPolicy,
)


def node(node_id: str, kind: str = "implement", **kwargs: object) -> GraphNode:
    return GraphNode(id=node_id, kind=kind, title=node_id, **kwargs)


def director(**kwargs: object) -> GraphNode:
    return node("Director", kind="explore", role="composite", **kwargs)


def valid_graph(extra: list[GraphNode] | None = None, **kwargs: object) -> ExecutionGraph:
    nodes = [director(), *(extra or [])]
    return ExecutionGraph(nodes=nodes, **kwargs)


def test_json_roundtrip_preserves_v1_fields() -> None:
    kinds = [kind.value for kind in NodeKind]
    nodes = [director(children=["n0"])]
    for index, kind in enumerate(kinds):
        # `manage` nodes are advisory branch owners: always composite, never
        # holding a write scope.
        managing = kind == "manage"
        role = (
            NodeRole.COMPOSITE
            if managing or kind in {"explore", "integrate"}
            else NodeRole.ATOMIC
        )
        deps = ["Director"] if index == 0 else [f"n{index - 1}"]
        nodes.append(
            node(
                f"n{index}",
                kind=kind,
                role=role,
                authority="advisory_only" if managing else "implementation",
                depends_on=deps,
                artifact_inputs=[ArtifactRef(name=f"artifact-{index - 1}", required=False)]
                if index
                else [],
                artifact_outputs=[ArtifactRef(name=f"artifact-{index}")],
                read_scopes=["src"],
                write_scopes=[] if managing else [f"file-{index}.py"],
                acceptance=["done"],
                review=ReviewPolicy(required=True, checklist=["checked"]),
                risk="high",
                priority="critical",
                limits=Limits(max_attempts=2, heartbeat_seconds=60, max_expansions=1),
                failure_domain="branch",
            )
        )
    graph = ExecutionGraph(nodes=nodes, frontier=["n0"], max_depth=20)
    graph.validate()

    loaded = ExecutionGraph.from_json(graph.to_json())

    assert loaded.schema_version == "graph-coder/v1"
    assert [n.kind for n in loaded.nodes[1:]] == [NodeKind(kind) for kind in kinds]
    assert loaded.nodes[1].role == NodeRole.COMPOSITE
    assert loaded.nodes[2].artifact_outputs[0].producer == "n1"
    assert loaded.frontier == ["n0"]


@pytest.mark.parametrize(
    ("graph", "message"),
    [
        (ExecutionGraph(nodes=[director(), director()]), "unique"),
        (valid_graph([node("a", depends_on=["missing"])]), "unknown"),
        (
            ExecutionGraph(nodes=[director(depends_on=["a"]), node("a", depends_on=["Director"])]),
            "acyclic",
        ),
        (valid_graph(frontier=["missing"]), "frontier"),
        (valid_graph([node("a", artifact_inputs=[ArtifactRef("missing")])]), "no producer"),
        (valid_graph([node("a")], max_nodes=1), "max_nodes"),
        (
            valid_graph(
                [node("a", depends_on=["Director"]), node("b", depends_on=["a"])], max_depth=2
            ),
            "max_depth",
        ),
        (
            ExecutionGraph(
                nodes=[director(children=["a", "b"]), node("a"), node("b")], max_fanout=1
            ),
            "max_fanout",
        ),
        (valid_graph([node("a", limits=Limits(max_attempts=0))]), "max_attempts"),
        (valid_graph([node("a", limits=Limits(max_expansions=101))]), "max_expansions"),
        (
            valid_graph([node("a", write_scopes=["x"]), node("b", write_scopes=["x"])]),
            "overlapping writes",
        ),
    ],
)
def test_validation_failures(graph: ExecutionGraph, message: str) -> None:
    with pytest.raises(ContractError, match=message):
        graph.validate()


def test_artifact_inputs_must_depend_on_producer() -> None:
    graph = valid_graph(
        [
            node("producer", artifact_outputs=[ArtifactRef("build")]),
            node("consumer", artifact_inputs=[ArtifactRef("build")]),
        ]
    )
    with pytest.raises(ContractError, match="must depend"):
        graph.validate()


def test_external_artifact_input_needs_no_graph_producer() -> None:
    graph = valid_graph(
        [node("consumer", artifact_inputs=[ArtifactRef("repository-schema", external=True)])]
    )
    graph.validate()


def test_overlapping_writes_allowed_when_ordered_or_merge_strategy() -> None:
    ordered = valid_graph(
        [node("a", write_scopes=["x"]), node("b", depends_on=["a"], write_scopes=["x"])]
    )
    ordered.validate()

    merged = valid_graph(
        [
            node("a", write_scopes=["x"], merge_strategy="manual-merge"),
            node("b", write_scopes=["x"], merge_strategy="manual-merge"),
        ]
    )
    merged.validate()


def test_nested_and_glob_write_scopes_conflict_and_frontier_is_local() -> None:
    nested = valid_graph([node("a", write_scopes=["src"]), node("b", write_scopes=["src/app.py"])])
    with pytest.raises(ContractError, match="overlapping writes"):
        nested.validate()

    graph = valid_graph(
        [
            node("a", depends_on=["Director"]),
            node("b", depends_on=["a"]),
            node("independent"),
        ]
    )
    assert graph.ready_frontier({"Director"}) == ["a", "independent"]


def test_duplicate_artifact_producers_are_rejected() -> None:
    graph = valid_graph(
        [
            node("a", artifact_outputs=[ArtifactRef("build")]),
            node("b", artifact_outputs=[ArtifactRef("build")]),
        ]
    )
    with pytest.raises(ContractError, match="multiple producers"):
        graph.validate()


def test_compile_plan_units_groups_safe_atomic_nodes() -> None:
    graph = valid_graph(
        [
            node("a", kind="verify", depends_on=["Director"], prompt="check a"),
            node("b", kind="verify", depends_on=["Director"], prompt="check b"),
            node("c", kind="implement", depends_on=["a"], write_scopes=["src/x.py"]),
        ]
    )

    units = graph.compile_plan_units()

    assert units[0].id == "Director"
    assert any(unit.node_ids == ["a", "b"] for unit in units)
    assert [unit.id for unit in units][-1] == "c"
