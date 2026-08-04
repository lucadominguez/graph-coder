"""Contract tests for the /graph-coder orchestrator and its companion skills.

These assert structure and the rules that must survive an edit: the exact phase
sequence, the authority boundaries, the absence of reviewer roles, and full-plan
approval. They check that the instructions say the right thing. They do not claim
to prove an agent obeys them.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

ACTIVE_SKILLS = [
    "graph-coder",
    "concept-grill",
    "technical-research",
    "plan-forge",
    "plan-rehearsal",
    "delegation-graph",
    "routing-plan",
    "execution-manager",
]

PHASES = [
    "INTAKE_AND_CONTEXT",
    "REPOSITORY_GROUNDING",
    "CONCEPT_GRILL",
    "TECHNICAL_RESEARCH",
    "PLAN_AUTHORING",
    "COLD_REHEARSAL",
    "GRAPH_COMPILATION",
    "MODEL_ROUTING",
    "FULL_PLAN_APPROVAL",
    "DIRECTED_EXECUTION",
]

REMOVED_PHASES = [
    "PRODUCT_CONTRACT",
    "REVIEW_GRAPH",
    "FINAL_SIMULATION",
    "CONSOLIDATED_APPROVAL",
    "PLAN_MUTATION",
    "CONTEXT_RECONSTRUCTION",
]

PLAN_SECTIONS = [
    "Goal Capsule",
    "Concept and Requirements",
    "Scope and Non-Goals",
    "Acceptance and Invariants",
    "Repository Grounding",
    "Technical Research",
    "Technical Decisions",
    "System Impact",
    "Canonical Implementation Units",
    "Delegation Graph",
    "Routing Assignments",
    "Context Contract",
    "Verification Contract",
    "Failure and Recovery Contract",
    "Definition of Done",
    "Sources and Evidence",
]

EXECUTION_STATES = [
    "pending",
    "ready",
    "running",
    "awaiting_review",
    "repair_required",
    "completed",
    "blocked",
    "human_required",
    "failed",
    "cancelled",
]

UNIT_CONTRACT_FIELDS = [
    "unit_id",
    "objective",
    "dependencies",
    "acceptance_ids",
    "read_scope",
    "write_scope",
    "forbidden_scope",
    "interfaces",
    "expected_artifacts",
    "manager_id",
    "review_contract",
    "context_manifest",
    "failure_domain",
    "retry_policy",
]


def read(relative):
    return (SKILLS / relative).read_text(encoding="utf-8")


def orchestrator():
    return read("graph-coder/SKILL.md")


def all_active_skill_text():
    return {name: read(f"{name}/SKILL.md") for name in ACTIVE_SKILLS}


# --- structure ---------------------------------------------------------------


def test_every_active_skill_exists_with_valid_frontmatter():
    for name, text in all_active_skill_text().items():
        assert text.startswith("---\n"), name
        assert f"name: {name}\n" in text, name
        assert "description:" in text, name
        header, _ = text.split("---\n", 2)[1:]
        assert "\n\n" not in header, f"{name} frontmatter has a blank line"


def test_skill_descriptions_state_when_to_invoke_not_the_whole_workflow():
    for name, text in all_active_skill_text().items():
        description = next(line for line in text.splitlines() if line.startswith("description:"))
        assert len(description) < 400, f"{name} description is a workflow summary"


def test_skills_stay_under_the_line_budget():
    for path in SKILLS.rglob("*.md"):
        lines = len(path.read_text(encoding="utf-8").splitlines())
        assert lines < 500, f"{path.name} is {lines} lines"


def test_orchestrator_references_exist():
    for reference in ("artifact-map.md", "phase-gates.md", "third-party-skills.md"):
        assert (SKILLS / "graph-coder" / "references" / reference).is_file(), reference


def test_obsolete_aps_orchestrators_are_not_present():
    for name in ("aps-plan", "idea-grill"):
        assert not (SKILLS / name).exists(), name


# --- lifecycle ---------------------------------------------------------------


def test_orchestrator_declares_exactly_the_ten_phases_in_order():
    text = orchestrator()
    positions = []
    for phase in PHASES:
        assert phase in text, phase
        positions.append(text.index(phase))
    assert positions == sorted(positions), "phases are out of order"


def test_removed_aps_phases_appear_nowhere():
    for name, text in all_active_skill_text().items():
        for phase in REMOVED_PHASES:
            assert phase not in text, f"{name} mentions {phase}"


def test_no_skill_instructs_spawning_specialist_plan_reviewers():
    # Naming the removed swarm in order to deny it is fine. Instructing anyone to
    # start one is not, so match on the activation verbs rather than the noun.
    for name, text in all_active_skill_text().items():
        lowered = text.lower()
        for forbidden in (
            "activate specialist review",
            "spawn specialist review",
            "spawn reviewers",
            "invoke reviewers",
            "specialist review from actual risk",
            "assign an independent reviewer",
            "rerun specialist",
            "re-review",
        ):
            assert forbidden not in lowered, f"{name} contains {forbidden!r}"


def test_plan_forge_routes_review_to_the_manager_not_a_reviewer():
    forge = read("plan-forge/SKILL.md")
    assert "replaces any notion of an independent reviewer" in forge
    assert "review is owned by its manager" in forge
    assert "Never specify a reviewer agent, a review node" in forge


def test_plan_forge_replaces_the_reviewer_swarm_with_an_author_self_audit():
    forge = read("plan-forge/SKILL.md")
    assert "no specialist reviewer swarm" in forge
    assert "Author self-audit" in forge
    assert "The frontier author owns internal consistency" in forge


def test_plan_has_the_sixteen_canonical_sections():
    text = orchestrator() + read("plan-forge/SKILL.md")
    for section in PLAN_SECTIONS:
        assert section in text, section


def test_product_contract_is_not_a_native_artifact():
    concept = read("concept-grill/SKILL.md")
    assert "no Product Contract phase and no Product Contract document" in concept
    forge = read("plan-forge/SKILL.md")
    assert "parallel contract document" in forge


# --- authority boundaries ----------------------------------------------------


def test_director_may_never_write_implementation_code():
    text = orchestrator()
    assert "Director may write to application code        never" in text
    assert "never becomes the implementer of last resort" in text


def test_execution_orders_the_director_to_spawn_subagents():
    """The observed failure this guards: a Director that read the whole skill,
    understood every role, and then implemented the plan itself in the root
    session, because nothing ever told it in so many words to spawn anything."""

    text = orchestrator()
    assert "Execution means spawning subagents" in text
    assert "runs inside its own freshly spawned subagent" in text
    assert "you never called your harness's subagent tool, the run failed" in text
    assert "You do not implement." in text
    assert "references/dispatch.md" in text


def test_dispatch_recipe_names_a_concrete_mechanism_per_harness():
    dispatch = read("graph-coder/references/dispatch.md")
    assert "graph-coder jcode emit --graph <graph>" in dispatch
    assert "task_graph.arguments.nodes` is the spawn list" in dispatch
    assert "Send it verbatim" in dispatch
    # Both supported shapes, so no harness is left without an instruction.
    assert "swarm spawn --label" in dispatch
    assert "one subagent call per entry" in dispatch
    # And the refusal, which is what stops a silent degrade into self-implementation.
    assert "No subagent tool at all" in dispatch
    assert "Do not silently degrade into implementing the plan" in dispatch


def test_self_implementation_is_named_as_a_failure_not_left_implied():
    text = orchestrator()
    assert "implementing the units yourself in the root session" in text
    assert "spawning one subagent for the whole plan instead of one per node" in text
    # Gates are hard-wrapped prose, so match on collapsed whitespace.
    gates = " ".join(read("graph-coder/references/phase-gates.md").split())
    assert "at least one subagent was spawned per dispatchable node" in gates
    assert "did not execute the graph and does not exit" in gates
    assert "a confirmed way to spawn subagents in this harness" in gates


def test_dispatch_preflight_covers_the_three_observed_failures():
    """From a real run: stale swarm plans merged a 3-node graph into 55 nodes,
    phase 8 was skipped so every packet shipped model `local`, and inline spawns
    left the workers invisible to `swarm list`."""

    # Hard-wrapped prose, so match on collapsed whitespace.
    dispatch = " ".join(read("graph-coder/references/dispatch.md").split())
    assert "swarm cleanup --force" in dispatch
    assert "`local` is the example plan's compile placeholder, not a route" in dispatch
    assert "never appears in `swarm list`" in dispatch
    text = orchestrator()
    assert "swarm cleanup --force" in text
    assert "stop unless `ready_to_dispatch` is true" in text
    assert "without `spawn_mode: visible`" in text
    # The block the skill tells the Director to read is documented where it looks.
    assert '"ready_to_dispatch": false' in dispatch


def test_dispatch_shows_the_actual_spawn_call():
    dispatch = read("graph-coder/references/dispatch.md")
    assert "swarm spawn --label" in dispatch
    assert "--spawn_mode visible" in dispatch
    # run_plan is documented as the brittle path, with a stated fallback.
    assert "Only the coordinator can assign tasks." in dispatch
    assert "drop to per-node" in dispatch


def test_spawn_width_follows_the_dag_in_both_directions():
    dispatch = read("graph-coder/references/dispatch.md")
    assert "linear chain         spawn one, verify, then spawn the next" in dispatch
    assert "IU-STORE -> IU-BACKEND -> IU-FRONTEND" in dispatch
    assert "The reverse mistake costs just as much" in dispatch


def test_completion_is_verified_from_the_filesystem_not_the_swarm():
    dispatch = read("graph-coder/references/dispatch.md")
    # Scoped to completion evidence. Liveness is the swarm's job, asserted in
    # test_liveness_and_completion_are_separate_signals; the two must not be
    # collapsed back into "ignore the swarm".
    assert "Do not treat a swarm report as the completion evidence" in dispatch
    assert "does its job either way" in dispatch
    assert "neither is its absence from `swarm list`" in dispatch
    manager = read("execution-manager/SKILL.md")
    assert "confirmed from the filesystem and from commands" in manager
    assert "still did its work" in manager


def test_liveness_and_completion_are_separate_signals():
    """The observed failure: the Director polled the filesystem for an output file
    for two minutes while the worker sat on a 429, because a blocked worker and a
    working one look identical on disk."""

    dispatch = read("graph-coder/references/dispatch.md")
    assert "filesystem   is it done?" in dispatch
    assert "swarm status is it alive?" in dispatch
    assert "Polling only the filesystem is the trap" in dispatch
    assert "Never respawn a node whose worker is still alive" in dispatch
    manager = read("execution-manager/SKILL.md")
    assert "Watch both signals every cycle" in manager
    assert "a silent worker and a rate-limited one look the same on disk" in manager


def test_rate_limits_are_classed_as_transient_not_incapability():
    dispatch = read("graph-coder/references/dispatch.md")
    assert "transient infrastructure, never model incapability" in dispatch
    manager = read("execution-manager/SKILL.md")
    assert "A rate limit (`429`) is transient infrastructure" in manager
    # Pre-existing rule this builds on, so the two cannot drift apart.
    assert "Never treat a provider outage as model incapability" in manager


def test_unavailable_evidence_has_a_declared_degraded_path():
    """A run hit an auth failure, hand-picked a cheap model, and carried on with no
    receipt. The fallback is legitimate; doing it silently is not."""

    routing = read("routing-plan/SKILL.md")
    assert "When the evidence source is unavailable" in routing
    assert "routing_evidence: harness_model_list" in routing
    assert "swarm list_models" in routing
    assert "What makes this a failure is doing it silently" in routing
    # The auth remedy, so 401/403 is not read as "routing is impossible".
    assert "invalid, expired, or lacks access rather than missing" in routing


def test_routing_phase_is_not_skippable_and_local_is_not_a_route():
    """The run that prompted this skipped phase 8 outright, because the plan
    already had something in its route field."""

    text = orchestrator()
    assert "This phase is not optional" in text
    assert "It is not a route." in text
    gates = " ".join(read("graph-coder/references/phase-gates.md").split())
    assert "a graph still holding `local` after phase 8 means the phase did not run" in gates
    example = (ROOT / "docs/plans/example-plan.md").read_text(encoding="utf-8")
    assert "placeholder, not a route, and it must never reach execution" in example


def test_repairs_are_spawned_too():
    manager = read("execution-manager/SKILL.md")
    assert "A `repair_required` verdict is also a spawn" in manager
    assert "no subagent was spawned, no work happened" in manager
    assert "Do not fall back to implementing the graph in the foreground session." in manager


def test_managers_are_advisory_only_and_cannot_repair():
    manager = read("execution-manager/SKILL.md")
    assert "`repository_write_scope` is empty" in manager
    assert "`can_implement` is false" in manager
    assert "run a repair as itself" in manager
    assert "it is a repair for a worker, not advice" in manager
    assert "Advice never contains a patch, a diff, or replacement code." in manager


def test_manager_owns_worker_review_and_no_reviewer_agents_exist():
    text = orchestrator()
    assert "a worker's own manager owns its review" in text
    assert "No reviewer agents are created beneath workers" in text
    graph = read("delegation-graph/SKILL.md")
    assert "No node has kind `review`" in graph
    assert "review_owner" in graph


def test_only_a_passing_manager_review_completes_a_unit():
    for text in (orchestrator(), read("execution-manager/SKILL.md")):
        assert "awaiting_review" in text
        assert "makes dependents eligible" in text


def test_verify_nodes_cannot_smuggle_a_reviewer_role_back_in():
    for name in ("graph-coder", "delegation-graph", "plan-forge"):
        text = read(f"{name}/SKILL.md")
        assert "concrete validation action" in text, name


def test_manager_does_not_receive_worker_private_reasoning():
    assert "does not receive the worker's private reasoning" in orchestrator()
    assert "You do not receive the worker's private reasoning" in read("execution-manager/SKILL.md")


# --- failure isolation -------------------------------------------------------


def test_execution_states_are_declared():
    text = orchestrator()
    for state in EXECUTION_STATES:
        assert state in text, state


def test_independent_branches_continue_after_an_isolated_failure():
    text = orchestrator()
    assert "blocks that node's transitive dependents and nothing else" in text
    assert "Independent ready nodes keep running" in text
    manager = read("execution-manager/SKILL.md")
    assert "block independent branches" in manager
    assert "HUMAN-REQUIRED PACKET" in manager


def test_escalation_ladder_is_bounded():
    for name in ("graph-coder", "execution-manager"):
        text = read(f"{name}/SKILL.md")
        assert "fallback-worker repair attempt" in text, name
        assert "may add unbounded retries" in text or "into unbounded retries" in text, name


def test_escalation_is_a_control_plane_event_not_a_graph_edge():
    for name in ("graph-coder", "delegation-graph"):
        assert "control-plane events, not dependency edges" in read(f"{name}/SKILL.md"), name


# --- approval ----------------------------------------------------------------


def test_full_plan_approval_renders_the_entire_plan():
    text = orchestrator()
    assert "Render the complete canonical plan" in text
    assert "A summary is not an approval view" in text
    assert "If the plan is long, say so and render it anyway." in text
    for binding in ("plan hash", "graph hash", "route hash", "render hash"):
        assert binding in text, binding


def test_material_change_invalidates_approval():
    assert "invalidates approval" in orchestrator()
    artifact_map = read("graph-coder/references/artifact-map.md")
    assert "the previous approval is void" in artifact_map
    assert "approve a diff in place of the plan" in artifact_map


# --- context and cost --------------------------------------------------------


def test_context_is_role_scoped_and_bounded():
    text = orchestrator()
    assert "Leaf agents receive unit-local context" in text
    assert "Managers receive branch-local context" in text
    assert "rejected unless it comes from the Director" in text
    assert "is not a saving" in text


def test_cost_model_targets_failed_attempts_not_sticker_price():
    for name in ("graph-coder", "routing-plan"):
        text = read(f"{name}/SKILL.md")
        assert "expected passing cost" in text.lower(), name
    assert "Failed and repeated implementation attempts" in orchestrator()


def test_eighty_twenty_is_a_target_not_a_quota():
    assert "not a token quota to enforce" in orchestrator()


# --- routing -----------------------------------------------------------------


def test_director_is_pinned_and_no_reviewer_route_exists():
    routing = read("routing-plan/SKILL.md")
    assert "Pinned to the configured frontier model" in routing
    assert "never silently downgraded" in orchestrator().lower().replace(
        "is never silently downgraded", "never silently downgraded"
    )
    assert "no standalone reviewer route category" in routing


def test_subscription_first_is_enforced_by_the_router():
    routing = read("routing-plan/SKILL.md")
    assert "enforced by the router, not by prose" in routing
    assert "only among candidates that already cleared the hard filters" in routing


def test_routing_never_asks_for_a_plaintext_key():
    routing = read("routing-plan/SKILL.md")
    assert "ask the user to configure it in the process environment" in routing
    assert "Never ask for the plaintext value in chat" in routing


def test_every_route_emits_a_receipt():
    routing = read("routing-plan/SKILL.md")
    assert "A route with no receipt is not an assignment" in routing


# --- dependencies ------------------------------------------------------------


def test_concept_and_research_dependencies_are_declared_with_preflight():
    concept = read("concept-grill/SKILL.md")
    assert "ce-brainstorm" in concept
    assert "office-hours" in concept
    assert "superpowers:brainstorming" in concept
    assert "Never run all three by default" in concept
    assert "Never simulate a third-party skill" in concept

    third_party = read("graph-coder/references/third-party-skills.md")
    assert "MIT" in third_party
    for trigger in ("ce-brainstorm", "office-hours", "superpowers:brainstorming"):
        assert trigger in third_party, trigger


def test_research_starts_with_questions_and_dispatches_selectively():
    research = read("technical-research/SKILL.md")
    assert "Research begins with questions, not with agents" in research
    assert "Do not launch every capability" in research
    assert "must not trigger web research" in research
    assert "never establish API behavior" in research


def test_research_claims_must_change_the_plan():
    research = read("technical-research/SKILL.md")
    assert "must change something in the plan" in research
    assert "omitted from the final evidence ledger" in research


# --- plan growth -------------------------------------------------------------


def test_plan_refinement_is_monotonic():
    forge = read("plan-forge/SKILL.md")
    assert "Refinement is monotonic in substance" in forge
    assert "proven incorrect" in forge
    assert "Never shorten the plan for presentation" in forge


def test_units_carry_the_complete_contract():
    forge = read("plan-forge/SKILL.md")
    for field in UNIT_CONTRACT_FIELDS:
        assert field in forge, field


def test_cold_rehearsal_uses_the_exact_future_packet_and_forbids_edits():
    rehearsal = read("plan-rehearsal/SKILL.md")
    assert "exact task packet the future worker will receive" in rehearsal
    assert "Do not edit application files." in rehearsal
    assert "executability trial, not an execution review" in rehearsal
    assert "producer, path, schema, and" in rehearsal
