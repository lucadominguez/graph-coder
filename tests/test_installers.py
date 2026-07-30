from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_installers_are_idempotent_local_and_optional_jcode():
    sh = read("scripts/install.sh")
    ps = read("scripts/install.ps1")
    for text in (sh, ps):
        assert ".agents/skills" in text
        assert ".jcode/skills" in text
        assert "DryRun" in text or "dry-run" in text
        assert "No secrets" in text
        for skill in [
            "aps-plan",
            "idea-grill",
            "plan-forge",
            "plan-rehearsal",
            "routing-plan",
            "delegation-graph",
            "execution-manager",
        ]:
            assert skill in text
    assert "PowerShell 5.1" in ps
    assert "New-Item -ItemType Directory" in ps
    assert "mkdir -p" in sh


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
