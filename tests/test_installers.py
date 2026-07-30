from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


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


def test_installers_are_idempotent_local_and_optional_jcode():
    sh = read("scripts/install.sh")
    ps = read("scripts/install.ps1")
    for text in (sh, ps):
        assert ".agents/skills" in text
        assert ".jcode/skills" in text
        assert "DryRun" in text or "dry-run" in text
        assert "No secrets" in text
        for skill in ACTIVE_SKILLS:
            assert skill in text, skill
    assert "PowerShell 5.1" in ps
    assert "New-Item -ItemType Directory" in ps
    assert "mkdir -p" in sh


def test_installers_install_all_eight_active_skills_and_nothing_retired():
    for name in ("scripts/install.sh", "scripts/install.ps1"):
        text = read(name)
        for retired in ("aps-plan", "idea-grill"):
            assert retired not in text, f"{name} still installs {retired}"


def test_every_installed_skill_exists_in_the_repository():
    for skill in ACTIVE_SKILLS:
        assert (ROOT / "skills" / skill / "SKILL.md").is_file(), skill
    present = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
    assert present == set(ACTIVE_SKILLS)


def test_terminal_helpers_use_wt_without_komorebi_and_support_dry_run():
    texts = [
        read("scripts/graph-coder-terminal-helper.ps1"),
        read("scripts/graph-coder-terminal-helper.sh"),
        read("docs/superpowers/operator-terminal.md"),
        read("docs/installation.md"),
    ]
    for text in texts:
        assert "wt.exe" in text
        assert "DryRun" in text or "dry-run" in text
        assert "Komorebi" in text or "komorebi" in text
