from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def run_git(
    root: str | Path, args: list[str], timeout: float = 5.0
) -> subprocess.CompletedProcess[str]:
    if not args or any(a.startswith("-") and a == "--upload-pack" for a in args):
        raise ValueError("unsafe git arguments")
    return subprocess.run(
        ["git", *args],
        cwd=str(Path(root)),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
    )


def inspect_worktree(root: str | Path) -> dict[str, Any]:
    status = run_git(root, ["status", "--porcelain=v1", "--branch"])
    branch = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    commit = run_git(root, ["rev-parse", "HEAD"])
    return {
        "root": str(Path(root)),
        "ok": status.returncode == 0,
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "status": status.stdout.splitlines(),
        "errors": [
            p.stderr.strip()
            for p in (status, branch, commit)
            if p.returncode != 0 and p.stderr.strip()
        ],
    }


def compact_context(root: str | Path, limit: int = 20) -> dict[str, Any]:
    info = inspect_worktree(root)
    info["status"] = info["status"][:limit]
    return info
