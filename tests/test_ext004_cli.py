"""EXT-004 CLI dispatch tests (deterministic — no model, no interactive input).

Verifies the slash-command parser/dispatch and that read-only tool commands work end
to end through the Runtime (these also WIRE fs.list/fs.read/py.symbols into real use).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli


def test_unknown_and_nonslash():
    cli = JcodeCli()
    assert "unknown command" in cli.dispatch("/nope")
    assert "commands start with" in cli.dispatch("hello")
    assert cli.dispatch("") == ""


def test_help_and_agents_and_tools():
    cli = JcodeCli()
    assert "/find" in cli.dispatch("/help")
    assert "rewriter" in cli.dispatch("/agents")
    assert "shell_exec" in cli.dispatch("/tools")


def test_ls_and_read_and_symbols(tmp_path: Path):
    cli = JcodeCli()
    f = tmp_path / "m.py"
    f.write_text("def foo():\n    return 1\n", encoding="utf-8")
    assert "m.py" in cli.dispatch(f"/ls {tmp_path}")
    assert "def foo" in cli.dispatch(f"/read {f}")
    assert "foo" in cli.dispatch(f"/symbols {f}")


def test_grep(tmp_path: Path):
    cli = JcodeCli()
    (tmp_path / "x.py").write_text("alpha = 1\nbeta = 2\n", encoding="utf-8")
    out = cli.dispatch(f"/grep alpha {tmp_path}")
    assert "match" in out and "alpha" in out
