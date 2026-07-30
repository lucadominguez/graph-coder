from __future__ import annotations

from pathlib import Path

from graph_coder.terminal import build_windows_terminal_layout, open_windows_terminal


def test_layout_uses_wt_without_komorebi(tmp_path: Path) -> None:
    layout = build_windows_terminal_layout(tmp_path)
    flattened = " ".join(part for command in layout.commands for part in command)
    assert "wt.exe" in flattened
    assert "Komorebi" not in flattened
    assert str(tmp_path.resolve()) in flattened


def test_open_is_noop_without_explicit_execute(tmp_path: Path) -> None:
    layout = build_windows_terminal_layout(tmp_path)
    assert open_windows_terminal(layout) == []
