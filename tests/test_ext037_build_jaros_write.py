"""EXT-037 REQ-13: harness/intent_loop.py's `build_in_dir` (the `/build` command's write path) is
Jaros-native (Tenet 1) -- the FINAL SLICE (5) of the tracker #112 host-write sweep.

Mirrors the proven EXT-037 REQ-9/REQ-10/REQ-11/REQ-12 test pattern (see
tests/test_ext037_fixrepo_jaros_write.py, tests/test_ext037_agent_plan_jaros_write.py): a fake
recording runtime proves every real-host write routes through a real `code.write_file` Decision, a
rejecting fake runtime proves a gate rejection degrades to an honest failed result (never a
crash), a real `harness.coding_loop.Runtime` proves the write genuinely lands through the gate +
EXT-037 root-jail, and `runtime=None` (the default) proves byte-identical behavior for every
pre-existing eval/test/sandbox caller. Fully offline/deterministic -- `harness.behavioral_solve.
behavioral_solve` and `harness.proc_treekill.run_with_treekill` are monkeypatched to deterministic
fakes so no live model call or real pytest subprocess is ever needed.
"""
from __future__ import annotations

# #EXT-037-REQ-13 Start

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.behavioral_solve as bsolve
import harness.proc_treekill as treekill
from harness.cli import JcodeCli
from harness.intent_loop import _run_oracle, build_from_intent, build_in_dir

_CODE = "def somefunc(x):\n    return x + 1\n"
_TESTS = "def test_somefunc():\n    from somefunc import somefunc\n    assert somefunc(1) == 2\n"


class _FakeApplyRuntime:
    """Records every Decision passed to `.apply()` and ALSO performs the write for real (like
    `write_file_tool.execute()` would) -- `build_in_dir`'s `run_tests` probe reads the just-written
    files back via `run_with_treekill` (faked below), so a purely in-memory recording fake would
    make that read see stale/missing content."""

    def __init__(self) -> None:
        self.applied: list = []

    def apply(self, decision):
        self.applied.append(decision)
        path = decision.payload["path"]
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(decision.payload["content"])
        return {"tool": "code.write_file", "path": path, "applied": True}


class _RejectingRuntime:
    def apply(self, decision):
        raise RuntimeError("gate rejected code.write_file: refused path outside root")


def _fake_behavioral_solve(intent, name, current_src, context, pkg, run_tests, max_fix=2):
    self_pass, _ = run_tests(_CODE, _TESTS)
    return {"code": _CODE, "gherkin": "", "tests": _TESTS, "self_pass": self_pass}


def _fake_run_with_treekill(cmd, cwd, timeout=60, capture=False):
    return True, "1 passed"


@pytest.fixture(autouse=True)
def _fake_solve_and_run(monkeypatch):
    monkeypatch.setattr(bsolve, "behavioral_solve", _fake_behavioral_solve)
    monkeypatch.setattr(treekill, "run_with_treekill", _fake_run_with_treekill)


# --- build_in_dir: Decision routing, gate rejection, runtime=None regression -------------------

def test_build_in_dir_runtime_routes_writes_through_decision(tmp_path):
    rt = _FakeApplyRuntime()

    r = build_in_dir(str(tmp_path), "add one to a number", "somefunc.py", "somefunc", runtime=rt)

    assert r["self_pass"] is True
    assert r["files"] == ["somefunc.py", "test_somefunc.py"]
    # 2 writes from the run_tests probe + 2 final writes -- mirrors _build_class's
    # "initial + final" count exactly (EXT-037 REQ-12 idiom).
    assert len(rt.applied) == 4
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(tmp_path)
    paths = {d.payload["path"] for d in rt.applied}
    assert str(tmp_path / "somefunc.py") in paths
    assert str(tmp_path / "test_somefunc.py") in paths
    assert "def somefunc" in (tmp_path / "somefunc.py").read_text(encoding="utf-8")
    assert "def test_somefunc" in (tmp_path / "test_somefunc.py").read_text(encoding="utf-8")


def test_build_in_dir_runtime_gate_rejection_is_honest_not_a_crash(tmp_path):
    r = build_in_dir(str(tmp_path), "add one to a number", "somefunc.py", "somefunc",
                     runtime=_RejectingRuntime())

    assert r["self_pass"] is False
    assert "failed to write" in r["note"]
    assert r["files"] == []
    assert not (tmp_path / "somefunc.py").exists()
    assert not (tmp_path / "test_somefunc.py").exists()


def test_build_in_dir_runtime_none_is_byte_identical(tmp_path):
    """No regression: every pre-existing eval/test caller that never passes `runtime` (e.g.
    `harness/agent_loop.py`'s eval-only `execute_step` 'build' action, `harness/build_eval.py`,
    `tests/test_ext008_intent.py`) keeps the exact direct-write behavior."""
    r = build_in_dir(str(tmp_path), "add one to a number", "somefunc.py", "somefunc")

    assert r["self_pass"] is True
    assert (tmp_path / "somefunc.py").read_text(encoding="utf-8") == _CODE
    assert (tmp_path / "test_somefunc.py").read_text(encoding="utf-8") == _TESTS


def test_build_in_dir_real_runtime_writes_through_gate_and_pathjail(tmp_path):
    from harness.coding_loop import Runtime
    from jaros.core import create_decision

    proj = tmp_path / "proj"
    proj.mkdir()
    rt = Runtime(data_dir=tmp_path / "state", root=str(proj))

    r = build_in_dir(str(proj), "add one to a number", "somefunc.py", "somefunc", runtime=rt)

    assert r["self_pass"] is True
    assert "def somefunc" in (proj / "somefunc.py").read_text(encoding="utf-8")

    # path-jail still blocks an escape when fed through the SAME real Decision -> Runtime.apply
    # path this function now uses (EXT-037 REQ-1's root-jail, re-checked at the gate).
    escaping = create_decision(
        id="escape-build-1", source="test", type="code.write_file",
        payload={"path": str(tmp_path / "etc" / "x.py"), "content": "pwned\n", "root": str(proj)})
    with pytest.raises(RuntimeError, match="root"):
        rt.apply(escaping)
    assert not (tmp_path / "etc" / "x.py").exists()


# --- CLI wiring: /build threads a root-anchored Runtime (EXT-037 REQ-13) ------------------------

def test_slash_build_routes_through_real_runtime_and_decision_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from jaros.state import DecisionLog
    seen: list = []
    orig = DecisionLog.append_decision

    def _spy(self, record):
        seen.append((record.get("type"), (record.get("payload") or {}).get("path", "")))
        return orig(self, record)

    monkeypatch.setattr(DecisionLog, "append_decision", _spy)

    cli = JcodeCli()
    out = cli.dispatch("/build somefunc add one to a number")

    assert "build" in out
    assert (tmp_path / "somefunc.py").exists()
    assert any(t == "code.write_file" and "somefunc.py" in p for t, p in seen)


def test_slash_build_usage_message_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.dispatch("/build").startswith("usage: /build")


# --- Honest scope: the oracle/eval-only writes this task did NOT touch stay raw -----------------

def test_run_oracle_and_build_from_intent_stay_raw_untouched(tmp_path):
    """`_run_oracle` (the HIDDEN-oracle scratch dir used only by the eval spine
    `build_from_intent`, never by `build_in_dir`/`/build`) and `build_from_intent` itself always
    build into a `tempfile.TemporaryDirectory()` they create themselves -- an internal
    scratch/eval concern, out of this task's scope (only `build_in_dir`, the `/build` command's
    write path). Confirmed by construction: neither function gained a `runtime` parameter."""
    assert "runtime" not in inspect.signature(_run_oracle).parameters
    assert "runtime" not in inspect.signature(build_from_intent).parameters


def test_agent_loop_build_action_stays_eval_only_unwired(tmp_path):
    """`harness/agent_loop.py`'s `execute_step` 'build' action calls `build_in_dir` without a
    `runtime` -- confirmed (not assumed) eval-only: `agent_loop.agent_loop`/`execute_step` is
    reached only by `harness/agentic_eval.py` and `tests/test_agent_loop.py`/
    `tests/test_ext037_root_enforcement.py`, never by any live CLI command (`harness/cli.py`'s
    `cmd_agent` calls `harness.spec_loop.spec_driven_loop`, a different function, instead)."""
    import harness.agent_loop as al
    src = inspect.getsource(al.execute_step)
    assert "build_in_dir(cwd, intent, f\"{func}.py\", func)" in src
# #EXT-037-REQ-13 End
