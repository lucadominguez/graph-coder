"""Safe command construction for optional Windows Terminal organization."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import CompatibilityError


@dataclass(frozen=True)
class TerminalLayout:
    """A deterministic set of Windows Terminal invocations."""

    commands: tuple[tuple[str, ...], ...]

    def as_lists(self) -> list[list[str]]:
        return [list(command) for command in self.commands]


def build_windows_terminal_layout(root: str | Path, graph_coder_command: str = "aps") -> TerminalLayout:
    project = str(Path(root).resolve())
    commands = (
        ("wt.exe", "new-tab", "--title", "Graph Coder Director", "-d", project),
        ("wt.exe", "new-tab", "--title", "Graph Coder Manager", "-d", project),
        (
            "wt.exe",
            "new-tab",
            "--title",
            "Graph Coder Status",
            "-d",
            project,
            "cmd",
            "/k",
            graph_coder_command,
            "--root",
            project,
            "run",
            "status",
        ),
    )
    return TerminalLayout(commands)


def open_windows_terminal(
    layout: TerminalLayout, *, execute: bool = False
) -> list[subprocess.Popen[bytes]]:
    """Return without side effects unless ``execute`` was explicitly requested."""

    if not execute:
        return []
    if os.name != "nt" or shutil.which("wt.exe") is None:
        raise CompatibilityError("wt.exe is unavailable; use the emitted dry-run commands")
    return [subprocess.Popen(command, shell=False) for command in layout.commands]
