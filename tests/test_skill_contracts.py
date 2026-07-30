from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Skills carried over from the APS baseline. The Graph Coder orchestrator and the
# concept/research adapters are added by later tasks and asserted separately in
# tests/test_graph_coder_skill.py.
PORTED_SKILLS = [
    "plan-forge",
    "plan-rehearsal",
    "routing-plan",
    "delegation-graph",
    "execution-manager",
]

# APS lifecycle stages that Graph Coder deliberately does not have. No skill in
# this repository may reintroduce them.
REMOVED_APS_PHASES = [
    "PRODUCT_CONTRACT",
    "REVIEW_GRAPH",
    "FINAL_SIMULATION",
    "CONSOLIDATED_APPROVAL",
]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def skill_files():
    return sorted((ROOT / "skills").glob("*/SKILL.md"))


def test_ported_skills_use_skill_md_metadata():
    for name in PORTED_SKILLS:
        text = read(f"skills/{name}/SKILL.md")
        assert text.startswith("---\n")
        assert f"name: {name}" in text
        assert "description:" in text
        assert "STOP/escalation rules" in text


def test_obsolete_aps_orchestrators_are_absent():
    for name in ("aps-plan", "idea-grill"):
        assert not (ROOT / "skills" / name).exists(), name


def test_specialists_encode_required_surfaces_and_boundaries():
    for name in PORTED_SKILLS:
        text = read(f"skills/{name}/SKILL.md")
        for required in [
            "Decision surfaces",
            "Evidence rules",
            "Bounded authority",
            "Manager-advisory boundary",
            "STOP/escalation rules",
        ]:
            assert required in text, name
    routing = read("skills/routing-plan/SKILL.md")
    assert "ask the user to configure it in the process environment" in routing
    assert "Never ask for the plaintext value in chat" in routing


def test_no_skill_reintroduces_a_removed_aps_phase():
    for path in skill_files():
        text = path.read_text(encoding="utf-8")
        for phase in REMOVED_APS_PHASES:
            assert phase not in text, f"{path.parent.name} mentions {phase}"


def test_pressure_scenarios_cover_design_list():
    expected = {
        "ambiguous_product_intent",
        "destructive_migration_request",
        "secret_handling_pressure",
        "parallel_file_conflict",
        "cycle_in_delegation_graph",
        "missing_acceptance_checks",
        "resume_after_partial_failure",
        "route_requires_external_capability",
        "approval_after_material_revision",
        "manager_attempts_to_execute",
        "built_in_plan_shadowing",
        "windows_terminal_no_komorebi",
        "truncated_rehearsal_report",
        "reload_with_unknown_workers",
        "excluded_provider_and_duplicate_route",
        "sidepanel_over_30_workers",
    }
    found = {p.stem for p in (ROOT / "tests/pressure").glob("*.json")}
    assert expected <= found
