import subprocess

from graph_coder.context import compact_context, inspect_worktree, run_git


def init_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "a@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "A"], cwd=path, check=True)
    (path / "file.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, text=True
    )


def test_safe_non_interactive_git_inspection(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "changed.txt").write_text("y", encoding="utf-8")
    info = inspect_worktree(tmp_path)
    assert info["ok"] is True
    assert info["commit"]
    assert any("changed.txt" in line for line in info["status"])
    assert compact_context(tmp_path, limit=1)["status"]


def test_windows_path_string_and_no_shell_injection(tmp_path):
    init_repo(tmp_path)
    proc = run_git(str(tmp_path).replace("\\", "/"), ["status", "--porcelain"])
    assert proc.returncode == 0
    proc = run_git(tmp_path, ["status;echo hacked"])
    assert proc.returncode != 0
