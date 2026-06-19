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


def test_files_and_patch_wire_those_tools(tmp_path: Path):
    cli = JcodeCli()
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert "a.py" in cli.dispatch(f"/files *.py {tmp_path}")
    f = tmp_path / "a.py"
    out = cli.dispatch(f"/patch {f} :: x = 1 :: x = 2")
    assert "applied" in out
    assert f.read_text(encoding="utf-8") == "x = 2\n"


# --- orchestrator routing (NL -> which agent/tool) -------------------------

import importlib.util

from jaros.llm import LlmResponse

ROOT = Path(__file__).resolve().parents[1]


def _load_orch():
    p = ROOT / ".jaros-data" / "agents" / "orchestrator_agent.py"
    spec = importlib.util.spec_from_file_location("orch", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakeLlm:
    def __init__(self, text):
        self._t = text

    def complete(self, req):
        return LlmResponse(text=self._t, model="fake")


def test_orchestrator_parses_action_and_arg():
    mod = _load_orch()
    assert mod.parse_route("ACTION: find\nARG: login") == ("find", "login")
    assert mod.parse_route("ACTION: fix\nARG: calc.py") == ("fix", "calc.py")
    action, _ = mod.parse_route("nonsense")
    assert action == "help"  # safe default


def test_orchestrator_emits_route_decision():
    mod = _load_orch()
    agent = mod.build(FakeLlm("ACTION: run\nARG: pytest -q"))
    [d] = agent.decide({"request": "please run the tests"})
    assert d.payload["action"] == "run" and d.payload["arg"] == "pytest -q"
