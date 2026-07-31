#!/usr/bin/env python3
"""Read-only upstream-awareness check against the pinned APS commit.

Graph Coder is an independent repository that was seeded from the Agent Planning
System. This script answers one question and takes no action: has APS `main`
moved past the commit recorded in `upstream/aps.lock.json`?

It clones nothing into the working tree, fetches into a throwaway directory,
and never merges, rebases, imports code, or edits the lock. Deciding what to do
about upstream drift is a human's job.

Exit codes:
    0  pinned commit is APS `main`
    1  the lock is unusable or APS could not be reached
    2  APS moved: new commits, a rewritten history, or an unknown pinned commit
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_LOCK = Path("upstream/aps.lock.json")

# Paths where an upstream change is worth a human's attention. Everything else
# (readmes, changelogs, editor config) is reported but not flagged.
RELEVANT_PREFIXES = ("src/", "schemas/", "skills/", "scripts/", "tests/")

FETCH_TIMEOUT_SECONDS = 120


class UpstreamLockError(ValueError):
    """The lock file is missing, malformed, or incomplete."""


class UpstreamCheckError(RuntimeError):
    """APS could not be inspected."""


@dataclass(frozen=True)
class UpstreamLock:
    repository_url: str
    commit: str
    branch: str
    license: str
    inspected_at: str
    source_path: Path


@dataclass(frozen=True)
class UpstreamReport:
    status: str
    pinned_commit: str
    remote_commit: str | None
    repository_url: str
    branch: str
    commits: list[dict[str, str]] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    relevant_changed_paths: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "current" else 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "repository_url": self.repository_url,
            "branch": self.branch,
            "pinned_commit": self.pinned_commit,
            "remote_commit": self.remote_commit,
            "commits": self.commits,
            "changed_paths": self.changed_paths,
            "relevant_changed_paths": self.relevant_changed_paths,
            "action_taken": "none",
        }


def load_lock(path: str | Path) -> UpstreamLock:
    lock_path = Path(path)
    if not lock_path.is_file():
        raise UpstreamLockError(f"lock file not found: {lock_path}")
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise UpstreamLockError(f"lock file is not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise UpstreamLockError("lock file must contain a JSON object")

    upstream = raw.get("upstream")
    if not isinstance(upstream, dict):
        raise UpstreamLockError("lock file is missing the 'upstream' object")

    required = ("repository_url", "commit", "branch", "license")
    missing = [key for key in required if not upstream.get(key)]
    if missing:
        raise UpstreamLockError(f"lock file is missing upstream fields: {', '.join(missing)}")

    commit = str(upstream["commit"]).lower()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise UpstreamLockError(f"upstream.commit must be a full 40-character sha: {commit!r}")

    return UpstreamLock(
        repository_url=str(upstream["repository_url"]),
        commit=commit,
        branch=str(upstream["branch"]),
        license=str(upstream["license"]),
        inspected_at=str(raw.get("inspected_at", "")),
        source_path=lock_path,
    )


def _git(workdir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(workdir), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    if check and result.returncode != 0:
        raise UpstreamCheckError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result


def check_upstream(lock_path: str | Path) -> UpstreamReport:
    """Compare the pinned APS commit with APS `main` without changing anything."""

    lock = load_lock(lock_path)
    workdir = Path(tempfile.mkdtemp(prefix="graph-coder-upstream-"))
    try:
        return _inspect(lock, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _inspect(lock: UpstreamLock, workdir: Path) -> UpstreamReport:
    _git(workdir, "init", "--quiet")
    fetch = _git(
        workdir,
        "fetch",
        "--quiet",
        "--no-tags",
        lock.repository_url,
        "+refs/heads/*:refs/remotes/upstream/*",
        check=False,
    )
    if fetch.returncode != 0:
        raise UpstreamCheckError(
            f"could not reach {lock.repository_url}: {fetch.stderr.strip() or 'fetch failed'}"
        )

    branch_ref = f"refs/remotes/upstream/{lock.branch}"
    head = _git(workdir, "rev-parse", "--verify", "--quiet", branch_ref, check=False)
    remote_commit = head.stdout.strip()
    if not remote_commit:
        raise UpstreamCheckError(f"{lock.repository_url} has no branch {lock.branch!r}")

    known = _git(workdir, "cat-file", "-e", f"{lock.commit}^{{commit}}", check=False)
    if known.returncode != 0:
        # The pinned commit is not reachable from any upstream branch: history was
        # rewritten, or the commit never existed on a public branch.
        return UpstreamReport(
            status="diverged",
            pinned_commit=lock.commit,
            remote_commit=remote_commit,
            repository_url=lock.repository_url,
            branch=lock.branch,
        )

    if remote_commit == lock.commit:
        return UpstreamReport(
            status="current",
            pinned_commit=lock.commit,
            remote_commit=remote_commit,
            repository_url=lock.repository_url,
            branch=lock.branch,
        )

    pinned_precedes = (
        _git(
            workdir, "merge-base", "--is-ancestor", lock.commit, remote_commit, check=False
        ).returncode
        == 0
    )
    remote_precedes = (
        _git(
            workdir, "merge-base", "--is-ancestor", remote_commit, lock.commit, check=False
        ).returncode
        == 0
    )

    if pinned_precedes:
        status = "behind"
    elif remote_precedes:
        status = "ahead"
    else:
        status = "diverged"

    commits: list[dict[str, str]] = []
    changed: list[str] = []
    if status == "behind":
        log = _git(
            workdir,
            "log",
            "--format=%H%x1f%s",
            f"{lock.commit}..{remote_commit}",
        )
        for line in log.stdout.splitlines():
            if "\x1f" not in line:
                continue
            sha, subject = line.split("\x1f", 1)
            commits.append({"sha": sha, "subject": subject})
        diff = _git(workdir, "diff", "--name-only", lock.commit, remote_commit)
        changed = sorted(path for path in diff.stdout.splitlines() if path)

    return UpstreamReport(
        status=status,
        pinned_commit=lock.commit,
        remote_commit=remote_commit,
        repository_url=lock.repository_url,
        branch=lock.branch,
        commits=commits,
        changed_paths=changed,
        relevant_changed_paths=[path for path in changed if path.startswith(RELEVANT_PREFIXES)],
    )


def render(report: UpstreamReport) -> str:
    headline = {
        "current": "APS is unchanged since the pinned commit.",
        "behind": "APS has new commits since the pinned commit.",
        "ahead": "The pinned commit is not on APS `main` (main is behind it).",
        "diverged": "The pinned commit is unreachable from APS `main`.",
    }[report.status]

    lines = [
        "# APS upstream awareness",
        "",
        headline,
        "",
        f"- repository: `{report.repository_url}`",
        f"- branch: `{report.branch}`",
        f"- pinned commit: `{report.pinned_commit}`",
        f"- APS head: `{report.remote_commit}`",
        f"- status: **{report.status}**",
    ]
    if report.commits:
        lines += ["", f"## New APS commits ({len(report.commits)})", ""]
        lines += [f"- `{entry['sha'][:12]}` {entry['subject']}" for entry in report.commits]
    if report.relevant_changed_paths:
        lines += ["", "## Changed source paths worth reviewing", ""]
        lines += [f"- `{path}`" for path in report.relevant_changed_paths]
    other = [path for path in report.changed_paths if path not in report.relevant_changed_paths]
    if other:
        lines += ["", f"## Other changed paths ({len(other)})", ""]
        lines += [f"- `{path}`" for path in other]
    if report.status != "current":
        lines += [
            "",
            "No code was imported and the lock was not modified. Review the changes and, if you",
            "want them, port them deliberately and update `upstream/aps.lock.json` by hand.",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_aps_upstream",
        description="Report APS upstream drift without importing anything.",
    )
    parser.add_argument("--lock", default=str(DEFAULT_LOCK), help="path to upstream/aps.lock.json")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)

    try:
        report = check_upstream(args.lock)
    except (UpstreamLockError, UpstreamCheckError) as error:
        print(f"upstream check failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(report.to_dict(), indent=2) if args.json else render(report))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
