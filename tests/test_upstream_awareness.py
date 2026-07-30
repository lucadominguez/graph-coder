"""Contract tests for the read-only APS upstream-awareness checker.

The checker must answer one question: has APS moved since the commit Graph Coder
pinned? It must never merge, rebase, rewrite the lock, or touch either worktree.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_aps_upstream as checker  # noqa: E402

GIT_ENV_ARGS = [
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
]


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *GIT_ENV_ARGS, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit_file(repo: Path, relative: str, content: str, message: str) -> str:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def upstream(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    commit_file(repo, "src/agent_planning_system/plans.py", "# v1\n", "initial")
    return repo


def write_lock(tmp_path: Path, upstream_repo: Path, commit: str, **overrides: object) -> Path:
    lock = {
        "upstream": {
            "name": "agent-planning-system",
            "repository_url": upstream_repo.as_posix(),
            "commit": commit,
            "branch": "main",
            "license": "MIT",
        },
        "inspected_at": "2026-07-30",
        "policy": {"automatic_import": False, "automatic_lock_update": False},
    }
    lock.update(overrides)
    path = tmp_path / "aps.lock.json"
    path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    return path


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_reports_current_when_pinned_commit_is_remote_head(tmp_path: Path, upstream: Path) -> None:
    head = git(upstream, "rev-parse", "HEAD")
    lock = write_lock(tmp_path, upstream, head)

    report = checker.check_upstream(lock)

    assert report.status == "current"
    assert report.exit_code == 0
    assert report.pinned_commit == head
    assert report.remote_commit == head
    assert report.commits == []


def test_reports_behind_with_commits_and_changed_paths(tmp_path: Path, upstream: Path) -> None:
    pinned = git(upstream, "rev-parse", "HEAD")
    commit_file(upstream, "src/agent_planning_system/routing.py", "# routing\n", "feat: routing")
    commit_file(upstream, "README.md", "# readme\n", "docs: readme")
    head = git(upstream, "rev-parse", "HEAD")
    lock = write_lock(tmp_path, upstream, pinned)

    report = checker.check_upstream(lock)

    assert report.status == "behind"
    assert report.exit_code == 2
    assert report.remote_commit == head
    assert [entry["subject"] for entry in report.commits] == ["docs: readme", "feat: routing"]
    assert "src/agent_planning_system/routing.py" in report.changed_paths
    assert "README.md" in report.changed_paths
    # Source changes are the ones a human must actually look at.
    assert "src/agent_planning_system/routing.py" in report.relevant_changed_paths
    assert "README.md" not in report.relevant_changed_paths


def test_reports_diverged_when_pinned_commit_is_unreachable(tmp_path: Path, upstream: Path) -> None:
    pinned = git(upstream, "rev-parse", "HEAD")
    lock = write_lock(tmp_path, upstream, pinned)
    git(upstream, "checkout", "--orphan", "rewritten")
    git(upstream, "rm", "-rf", ".")
    commit_file(upstream, "src/agent_planning_system/plans.py", "# rewritten\n", "rewrite history")
    git(upstream, "branch", "-D", "main")
    git(upstream, "branch", "-m", "main")

    report = checker.check_upstream(lock)

    assert report.status == "diverged"
    assert report.exit_code == 2
    assert report.pinned_commit == pinned


def test_reports_ahead_when_pinned_commit_is_newer_than_remote(
    tmp_path: Path, upstream: Path
) -> None:
    remote_head = git(upstream, "rev-parse", "HEAD")
    ahead = commit_file(upstream, "extra.py", "# extra\n", "feat: extra")
    git(upstream, "branch", "later")
    git(upstream, "reset", "--hard", remote_head)
    lock = write_lock(tmp_path, upstream, ahead)

    report = checker.check_upstream(lock)

    assert report.status == "ahead"
    assert report.exit_code == 2


def test_unavailable_remote_is_an_error_not_a_silent_pass(tmp_path: Path) -> None:
    lock = write_lock(tmp_path, tmp_path / "does-not-exist", "0" * 40)

    with pytest.raises(checker.UpstreamCheckError):
        checker.check_upstream(lock)

    assert checker.main(["--lock", str(lock)]) == 1


def test_malformed_lock_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "aps.lock.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(checker.UpstreamLockError):
        checker.load_lock(path)

    path.write_text(json.dumps({"upstream": {"commit": "abc"}}), encoding="utf-8")
    with pytest.raises(checker.UpstreamLockError):
        checker.load_lock(path)

    assert checker.main(["--lock", str(path)]) == 1


def test_missing_lock_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(checker.UpstreamLockError):
        checker.load_lock(tmp_path / "absent.json")


def test_check_modifies_neither_repository(tmp_path: Path, upstream: Path) -> None:
    pinned = git(upstream, "rev-parse", "HEAD")
    commit_file(upstream, "src/agent_planning_system/graph.py", "# graph\n", "feat: graph")
    lock = write_lock(tmp_path, upstream, pinned)

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "upstream").mkdir()
    (consumer / "upstream" / "aps.lock.json").write_text(
        lock.read_text(encoding="utf-8"), encoding="utf-8"
    )
    before_consumer = tree_digest(consumer)
    before_upstream = tree_digest(upstream)
    upstream_head_before = git(upstream, "rev-parse", "HEAD")

    report = checker.check_upstream(consumer / "upstream" / "aps.lock.json")

    assert report.status == "behind"
    assert tree_digest(consumer) == before_consumer, "checker must not rewrite the lock"
    assert tree_digest(upstream) == before_upstream, "checker must not touch the APS worktree"
    assert git(upstream, "rev-parse", "HEAD") == upstream_head_before


def test_cli_exit_codes_and_json_output(
    tmp_path: Path, upstream: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    head = git(upstream, "rev-parse", "HEAD")
    current_lock = write_lock(tmp_path, upstream, head)
    assert checker.main(["--lock", str(current_lock), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "current"

    commit_file(upstream, "src/agent_planning_system/db.py", "# db\n", "feat: db")
    assert checker.main(["--lock", str(current_lock), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "behind"
    assert payload["commits"]


def test_checker_never_offers_an_import_or_update_path() -> None:
    source = (Path(__file__).resolve().parents[1] / "scripts" / "check_aps_upstream.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("git merge", "git rebase", "git pull", "git cherry-pick", "gh pr create"):
        assert forbidden not in source
    # The lock is human-owned: nothing in the checker may write it.
    assert "write_text" not in source


def test_workflow_is_read_only_and_cannot_import() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "upstream-awareness.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert 'cron: "0 7 * * 1"' in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "persist-credentials: false" in workflow

    for forbidden in (
        "git push",
        "git merge",
        "git rebase",
        "gh pr create",
        "peter-evans/create-pull-request",
        "contents: write",
        "pull-requests: write",
    ):
        assert forbidden not in workflow, forbidden

    # Exit code 2 means upstream moved. That is informational, never an import.
    assert "::notice title=APS moved::" in workflow


def test_repository_lock_pins_a_real_commit() -> None:
    root = Path(__file__).resolve().parents[1]
    lock = checker.load_lock(root / "upstream" / "aps.lock.json")
    assert lock.repository_url.endswith("agent-planning-system.git")
    assert len(lock.commit) == 40
    assert lock.license == "MIT"
    assert lock.branch == "main"
