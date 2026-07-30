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
        description = next(
            line for line in text.splitlines() if line.startswith("description:")
        )
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
    assert "You do not receive the worker's private reasoning" in read(
        "execution-manager/SKILL.md"
    )


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
