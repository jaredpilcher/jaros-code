"""EXT-037 REQ-12: harness/spec_loop.py's `/agent`/`/plan`/`_nl_fix` writes are Jaros-native
(Tenet 1) -- FINAL SLICE (4) of the tracker #112 host-write sweep.

Mirrors the proven EXT-037 REQ-9/REQ-10/REQ-11 test pattern (see
tests/test_ext037_fixrepo_jaros_write.py): a fake recording runtime proves every write routes
through a real `code.write_file` Decision, a rejecting fake runtime proves a gate rejection
degrades to an honest error (never a crash), a real `harness.coding_loop.Runtime` +
`DecisionLog` spy proves the write genuinely lands through the gate + EXT-037 root-jail, and
`runtime=None` (the default) proves byte-identical behavior for every pre-existing eval/test
caller. Fully offline/deterministic -- `fix_loop` and the test-writer agent are monkeypatched to
deterministic fakes, exactly like tests/test_ext003_multifile.py and
tests/test_ext037_fixrepo_jaros_write.py.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# #EXT-037-REQ-12 Start
os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.coding_loop as cl
from harness.cli import JcodeCli
from harness.spec_loop import (
    _build_class, _build_per_function, _build_whole_file, spec_driven_loop,
)

_TEST_CMD = "python -m pytest -q"


class _FakeApplyRuntime:
    """Records every Decision passed to `.apply()`, proving the CALLER built a real
    `code.write_file` Decision (not a raw `Path.write_text`). Also performs the write for real
    (like `write_file_tool.execute()` would), since `spec_loop.py`'s BUILD-flow writers read a
    module back after writing it (e.g. the sanitize/hybrid-assembly steps) -- a purely
    in-memory recording fake would make those honest reads crash on a file that "succeeded" but
    was never actually created."""

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


class _R:
    def __init__(self, success):
        self.success, self.attempts = success, 1


class _FakeDecision:
    def __init__(self, dtype="noop"):
        self.type = dtype
        self.payload = {}


class _FakeWriterAgent:
    """Every `_build_*` function also calls `_load_agent('test_writer_agent.py', ...)` for an
    UNRELATED write (the generated test file) via its own internal (rootless) `Runtime()` -- not
    the `runtime` parameter under test here. Faked out so these tests never touch a real model or
    write a stray test file; `decide()` returning a "noop" Decision means `rt.apply(tw)` is never
    invoked (the code only applies when `tw.type == "code.write_file"`)."""

    def decide(self, ctx):
        return [_FakeDecision("noop")]


@pytest.fixture(autouse=True)
def _fake_writer_agent(monkeypatch):
    monkeypatch.setattr(cl, "_load_agent", lambda filename, llm: _FakeWriterAgent())


def _fake_fix_loop(writes: dict):
    """`writes`: {suffix: content} -- when `fix_loop`'s target path ends with `suffix`, write
    `content` and report success; any other target reports failure (mirrors
    tests/test_ext037_fixrepo_jaros_write.py's `fake_fix_loop` pattern)."""
    def _f(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
           keep_partial=False):
        for suf, content in writes.items():
            if str(target).endswith(suf):
                Path(target).write_text(content, encoding="utf-8", newline="\n")
                return _R(True)
        return _R(False)
    return _f


def _spy_decision_log(monkeypatch):
    """Install a spy on `DecisionLog.append_decision` and return the list of recorded
    (type, path) tuples it will accumulate -- the SAME pattern as
    tests/test_ext037_fixrepo_jaros_write.py."""
    from jaros.state import DecisionLog
    seen: list = []
    orig = DecisionLog.append_decision

    def _spy(self, record):
        seen.append((record.get("type"), (record.get("payload") or {}).get("path", "")))
        return orig(self, record)

    monkeypatch.setattr(DecisionLog, "append_decision", _spy)
    return seen


# --- _build_class: the OOP BUILD-flow strategy --------------------------------------------------

def test_build_class_runtime_routes_writes_through_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "fix_loop", _fake_fix_loop({
        "solution.py": "class Stack:\n    def __init__(self):\n        self.items = []\n"
                       "    def push(self, x):\n        self.items.append(x)\n",
    }))
    rt = _FakeApplyRuntime()

    r = _build_class("a Stack class with push(x)", str(tmp_path), "Stack", [("push", "x")],
                     runtime=rt)

    assert r["flow"] == "build-class"
    assert len(rt.applied) == 2   # the initial stub, and the final sanitized module
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(tmp_path)
        assert d.payload["path"] == str(tmp_path / "solution.py")
    # proves the write really went THROUGH `runtime` (the ONLY thing that put it on disk here)
    assert "class Stack" in (tmp_path / "solution.py").read_text(encoding="utf-8")


def test_build_class_runtime_none_is_byte_identical(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "fix_loop", _fake_fix_loop({
        "solution.py": "class Stack:\n    def __init__(self):\n        self.items = []\n",
    }))
    r = _build_class("a Stack class", str(tmp_path), "Stack", [], runtime=None)
    assert r["flow"] == "build-class"
    assert "class Stack" in (tmp_path / "solution.py").read_text(encoding="utf-8")


def test_build_class_rejecting_runtime_is_honest_not_a_crash(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("fix_loop must never run after a rejected stub write")
    monkeypatch.setattr(cl, "fix_loop", _boom)

    r = _build_class("a Stack class", str(tmp_path), "Stack", [], runtime=_RejectingRuntime())

    assert r["solved"] is False and r["flow"] == "build-class"
    assert "failed to write" in r["note"]
    assert not (tmp_path / "solution.py").exists()


# --- _build_whole_file: the *args-stub whole-file BUILD-flow fallback ---------------------------

def test_build_whole_file_runtime_routes_writes_through_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "fix_loop", _fake_fix_loop({
        "solution.py": "def is_even(n):\n    return n % 2 == 0\n",
    }))
    rt = _FakeApplyRuntime()

    _build_whole_file("a number module with is_even(n)", str(tmp_path), ["is_even"], runtime=rt)

    assert len(rt.applied) == 2   # the initial *args stub, and the final sanitized module
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(tmp_path)
        assert d.payload["path"] == str(tmp_path / "solution.py")
    assert "is_even" in (tmp_path / "solution.py").read_text(encoding="utf-8")


def test_build_whole_file_runtime_none_is_byte_identical(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "fix_loop", _fake_fix_loop({
        "solution.py": "def is_even(n):\n    return n % 2 == 0\n",
    }))
    _build_whole_file("a number module with is_even(n)", str(tmp_path), ["is_even"], runtime=None)
    assert "is_even" in (tmp_path / "solution.py").read_text(encoding="utf-8")


def test_build_whole_file_rejecting_runtime_returns_early_no_crash(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("fix_loop must never run after a rejected stub write")
    monkeypatch.setattr(cl, "fix_loop", _boom)

    _build_whole_file("a number module with is_even(n)", str(tmp_path), ["is_even"],
                      runtime=_RejectingRuntime())

    assert not (tmp_path / "solution.py").exists()


# --- _build_per_function: the per-function concrete-sig BUILD-flow strategy ---------------------

def test_build_per_function_runtime_routes_writes_through_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "fix_loop", _fake_fix_loop({
        "add.py": "def add(a, b):\n    return a + b\n",
        "subtract.py": "def subtract(a, b):\n    return a - b\n",
    }))
    rt = _FakeApplyRuntime()
    sigs = [("add", "a, b"), ("subtract", "a, b")]

    r = _build_per_function("add(a, b) and subtract(a, b)", str(tmp_path), sigs, runtime=rt)

    assert r["solved"] is True and r["flow"] == "build-per-function"
    # 2 per-function stubs + the combined solution.py assembly + the final sanitized write = 4
    assert len(rt.applied) == 4
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(tmp_path)
    # every write really went THROUGH `runtime` (the only thing that put these on disk)
    assert "def add" in (tmp_path / "solution.py").read_text(encoding="utf-8")
    assert "def add" in (tmp_path / "add.py").read_text(encoding="utf-8")


def test_build_per_function_runtime_none_is_byte_identical(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "fix_loop", _fake_fix_loop({
        "add.py": "def add(a, b):\n    return a + b\n",
    }))
    r = _build_per_function("add(a, b)", str(tmp_path), [("add", "a, b")], runtime=None)
    assert r["solved"] is True
    assert "def add" in (tmp_path / "solution.py").read_text(encoding="utf-8")


def test_build_per_function_rejecting_runtime_degrades_honestly_no_crash(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("fix_loop must never run after a rejected per-function stub")
    monkeypatch.setattr(cl, "fix_loop", _boom)

    r = _build_per_function("add(a, b)", str(tmp_path), [("add", "a, b")],
                            runtime=_RejectingRuntime())

    assert r["solved"] is False
    assert not (tmp_path / "add.py").exists()
    assert not (tmp_path / "solution.py").exists()


def test_build_per_function_hybrid_probe_stays_raw(tmp_path, monkeypatch):
    """boolchecks-style: `is_odd`'s per-function build "fails" (leaves a stub), triggering the
    TASK-10 hybrid probe -- a *args whole-file build into an ISOLATED `tempfile.mkdtemp()`
    subdirectory. That inner probe build must stay on `runtime=None` even though the OUTER call
    is given a real runtime; only the FINAL winner-assembly write (back onto the real root) is
    routed through it."""
    def _fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                  keep_partial=False):
        t = str(target)
        if t.endswith("is_even.py"):
            Path(target).write_text("def is_even(n):\n    return n % 2 == 0\n", encoding="utf-8")
            return _R(True)
        if t.endswith("is_odd.py"):
            return _R(False)          # per-function build "fails" for is_odd -> stub kept
        if t.endswith("solution.py"):
            # the hybrid probe's whole-file fix_loop call -- give it BOTH functions (fewer stubs
            # than the per-function build, which left is_odd unimplemented) so it wins the swap.
            Path(target).write_text(
                "def is_even(n):\n    return n % 2 == 0\n\n"
                "def is_odd(n):\n    return n % 2 != 0\n", encoding="utf-8")
            return _R(True)
        return _R(False)

    monkeypatch.setattr(cl, "fix_loop", _fix_loop)
    seen = _spy_decision_log(monkeypatch)

    from harness.coding_loop import Runtime
    proj = tmp_path / "proj"
    proj.mkdir()
    rt = Runtime(data_dir=tmp_path / "state", root=str(proj))
    sigs = [("is_even", "n"), ("is_odd", "n")]

    r = _build_per_function("is_even(n) and is_odd(n)", str(proj), sigs, runtime=rt)

    assert r["flow"] == "build-hybrid"
    assert "is_odd" in (proj / "solution.py").read_text(encoding="utf-8")   # hybrid winner swapped in
    write_events = [(t, p) for t, p in seen if t == "code.write_file"]
    assert write_events, "expected at least one code.write_file Decision"
    # EVERY recorded write Decision targets the REAL root -- none reference the throwaway
    # tempfile.mkdtemp() dir the hybrid probe built into internally.
    for _, path in write_events:
        assert path.startswith(str(proj)), f"unexpected non-root write recorded: {path}"


# --- spec_driven_loop: threads `runtime` to both the FIX flow and the BUILD flow ----------------

def test_spec_driven_loop_threads_runtime_to_fix_flow(tmp_path, monkeypatch):
    calls = {}

    def _spy_multi_file_fix(cwd, test_cmd, instruction, test_file, *, max_iters=3,
                            verbose=False, runtime=None):
        calls["runtime"] = runtime
        return {"solved": True, "note": "spy"}

    import harness.spec_loop as sl
    monkeypatch.setattr(sl, "multi_file_fix", _spy_multi_file_fix)
    (tmp_path / "m.py").write_text("def f():\n    return 0\n", encoding="utf-8")
    (tmp_path / "test_m.py").write_text(
        "from m import f\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8")

    sentinel = object()
    r = spec_driven_loop("fix it", str(tmp_path), runtime=sentinel)

    assert r["flow"] == "fix"
    assert calls["runtime"] is sentinel


def test_spec_driven_loop_threads_runtime_to_build_flow(tmp_path, monkeypatch):
    calls = {}

    def _spy_decompose_build(intent, cwd, *, max_iters=3, verbose=False, runtime=None):
        calls["runtime"] = runtime
        return {"solved": True, "flow": "build", "requirements": 0, "note": "spy"}

    import harness.spec_loop as sl
    monkeypatch.setattr(sl, "_decompose_build", _spy_decompose_build)

    sentinel = object()
    r = spec_driven_loop("build something", str(tmp_path), runtime=sentinel)

    assert r["flow"] == "build"
    assert calls["runtime"] is sentinel


# --- CLI wiring: /plan, /agent, and the plain _nl_fix fallback all pass a real runtime -----------

def _stub_cli() -> JcodeCli:
    return JcodeCli()


def test_slash_plan_fix_step_routes_through_real_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ok.py").write_text("def g(x):\n    return x * 10\n")
    (tmp_path / "buggy.py").write_text("def f(x):\n    return x - 1\n")
    (tmp_path / "test_b.py").write_text(
        "from ok import g\nfrom buggy import f\n\n"
        "def test_f():\n    assert f(3) == 4\n    assert g(2) == 20\n",
    )

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                      keep_partial=False):
        if str(target).endswith("ok.py"):
            Path(target).write_text("def g(x):\n    return x  # MANGLED\n")
            return _R(False)
        if str(target).endswith("buggy.py"):
            Path(target).write_text("def f(x):\n    return x + 1\n")
            return _R(True)
        return _R(False)

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    seen = _spy_decision_log(monkeypatch)

    class _FakePlanDecision:
        payload = {"plan": [{"action": "fix", "arg": "fix it"}]}

    class _FakePlanner:
        def decide(self, ctx):
            return [_FakePlanDecision()]

    cli = _stub_cli()
    cli._load_agent = lambda name, llm: _FakePlanner()
    out = cli.cmd_plan("fix it")

    assert "solved" in out.lower()
    # the harmful ok.py edit was genuinely reverted, on disk, through a real code.write_file
    # Decision -- hash-chain logged, not a raw Path.write_text.
    assert "x * 10" in (tmp_path / "ok.py").read_text()
    assert any(t == "code.write_file" for t, _ in seen)


def test_nl_fix_no_file_named_routes_through_real_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ok.py").write_text("def g(x):\n    return x * 10\n")
    (tmp_path / "buggy.py").write_text("def f(x):\n    return x - 1\n")
    (tmp_path / "test_b.py").write_text(
        "from ok import g\nfrom buggy import f\n\n"
        "def test_f():\n    assert f(3) == 4\n    assert g(2) == 20\n",
    )

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                      keep_partial=False):
        if str(target).endswith("ok.py"):
            Path(target).write_text("def g(x):\n    return x  # MANGLED\n")
            return _R(False)
        if str(target).endswith("buggy.py"):
            Path(target).write_text("def f(x):\n    return x + 1\n")
            return _R(True)
        return _R(False)

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    seen = _spy_decision_log(monkeypatch)

    cli = _stub_cli()
    out = cli._nl_fix("fix the failing tests", "fix the failing tests")

    assert "multi-file" in out.lower()
    assert "x * 10" in (tmp_path / "ok.py").read_text()
    assert any(t == "code.write_file" for t, _ in seen)


def test_slash_agent_fix_flow_routes_through_real_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ok.py").write_text("def g(x):\n    return x * 10\n")
    (tmp_path / "buggy.py").write_text("def f(x):\n    return x - 1\n")
    (tmp_path / "test_b.py").write_text(
        "from ok import g\nfrom buggy import f\n\n"
        "def test_f():\n    assert f(3) == 4\n    assert g(2) == 20\n",
    )

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                      keep_partial=False):
        if str(target).endswith("ok.py"):
            Path(target).write_text("def g(x):\n    return x  # MANGLED\n")
            return _R(False)
        if str(target).endswith("buggy.py"):
            Path(target).write_text("def f(x):\n    return x + 1\n")
            return _R(True)
        return _R(False)

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    seen = _spy_decision_log(monkeypatch)

    cli = _stub_cli()
    out = cli.dispatch("/agent fix it")

    assert "solved" in out.lower() or "fix" in out.lower()
    assert "x * 10" in (tmp_path / "ok.py").read_text()
    assert any(t == "code.write_file" for t, _ in seen)


def test_slash_agent_build_flow_routes_through_real_runtime(tmp_path, monkeypatch):
    """No failing test present -> BUILD flow -> `_build_class` (a class intent) writes
    `solution.py` directly onto the real host `cwd`, through a real code.write_file Decision."""
    monkeypatch.chdir(tmp_path)

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                      keep_partial=False):
        if str(target).endswith("solution.py"):
            Path(target).write_text(
                "class Stack:\n    def __init__(self):\n        self.items = []\n"
                "    def push(self, x):\n        self.items.append(x)\n", encoding="utf-8")
            return _R(True)
        return _R(False)

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    seen = _spy_decision_log(monkeypatch)

    cli = _stub_cli()
    out = cli.dispatch("/agent build a Stack class with push(x)")

    assert "build-class" in out
    assert "class Stack" in (tmp_path / "solution.py").read_text(encoding="utf-8")
    assert any(t == "code.write_file" for t, _ in seen)
# #EXT-037-REQ-12 End
