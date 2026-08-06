import re
import shutil
import subprocess
from pathlib import Path

import pytest

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

# Retired name -> the skill that replaced it.
RETIRED_SKILLS = {"aps-plan": "graph-coder", "idea-grill": "concept-grill"}


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
    # The retired names are allowed to appear in the shadow report below, so this
    # checks the lists the copy loops actually iterate, not the whole file.
    sh_list = re.search(r"^for skill in (.+); do$", read("scripts/install.sh"), re.M)
    ps_list = re.search(r"^\$Skills = @\((.+)\)$", read("scripts/install.ps1"), re.M)
    assert sh_list and ps_list
    for source, group in (("install.sh", sh_list), ("install.ps1", ps_list)):
        installed = group.group(1)
        for retired in RETIRED_SKILLS:
            assert retired not in installed, f"{source} still installs {retired}"
        for skill in ACTIVE_SKILLS:
            assert skill in installed, f"{source} does not install {skill}"


def test_installers_report_retired_skills_left_behind_at_the_destination():
    # Copying deletes nothing, so a destination that predates the rename keeps
    # offering the old phase under the old name. Silence there cost a week of
    # edits that never reached the runtime.
    for name, flag in (
        ("scripts/install.sh", "--remove-retired"),
        ("scripts/install.ps1", "-RemoveRetired"),
    ):
        text = read(name)
        assert flag in text, f"{name} offers no way to remove a retired skill"
        for retired, replacement in RETIRED_SKILLS.items():
            assert retired in text, f"{name} does not check for {retired}"
            assert replacement in text
        assert "shadows" in text, f"{name} does not say why a retired skill matters"


def run_install_sh(destination, *args):
    return subprocess.run(
        ["sh", str(ROOT / "scripts" / "install.sh"), "--dest", str(destination), *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )


@pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX shell unavailable")
def test_install_sh_warns_about_a_retired_skill_and_removes_it_on_request(tmp_path):
    destination = tmp_path / "skills"
    shadow = destination / "idea-grill"
    shadow.mkdir(parents=True)
    (shadow / "SKILL.md").write_text("---\nname: idea-grill\n---\n", encoding="utf-8")

    warned = run_install_sh(destination)
    assert (destination / "concept-grill" / "SKILL.md").is_file()
    assert "idea-grill" in warned.stderr and "shadows" in warned.stderr
    assert shadow.is_dir(), "a warning must not delete anything on its own"

    dry = run_install_sh(destination, "--remove-retired", "--dry-run")
    assert "DRY RUN remove retired skill" in dry.stdout
    assert shadow.is_dir(), "--dry-run deleted a directory"

    removed = run_install_sh(destination, "--remove-retired")
    assert "REMOVED retired skill" in removed.stdout
    assert not shadow.exists()

    clean = run_install_sh(destination)
    assert "idea-grill" not in clean.stderr


@pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX shell unavailable")
def test_install_sh_treats_an_absolute_destination_as_absolute(tmp_path):
    # A drive-letter destination once fell through to the relative branch and the
    # skills landed under the repository instead of where they were asked for.
    destination = tmp_path / "skills"
    before = {path.name for path in ROOT.iterdir()}
    run_install_sh(destination)
    assert (destination / "graph-coder" / "SKILL.md").is_file()
    assert {path.name for path in ROOT.iterdir()} == before, "install wrote into the repository"


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
