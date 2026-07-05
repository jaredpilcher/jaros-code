"""EXT-037 REQ-10: harness/multi_file.py's `/fixrepo` (and the SHARED `_restore` used by
`/undo`) writes are Jaros-native (Tenet 1).

Mirrors the proven EXT-037 REQ-9 test pattern (`tests/test_ext037_refactor_jaros_write.py`): a
fake recording runtime proves every revert write is routed through a real `code.write_file`
Decision, a rejecting fake runtime proves a gate rejection degrades to an honest error (never a
crash), a real `harness.coding_loop.Runtime` proves the write actually lands through the gate +
EXT-037 root-jail, and `runtime=None` (the default) proves byte-identical behavior for every
pre-existing eval/test/sandbox caller. Fully offline/deterministic (no live model) -- every
`fix_loop` call is monkeypatched to a deterministic fake, exactly like `tests/test_ext003_multifile.py`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli
from harness.multi_file import _minimize_edits, _restore, _run, _snapshot, multi_file_fix

_TEST_CMD = "python -m pytest -q"


class _FakeApplyRuntime:
    """Records every Decision passed to `.apply()` -- does NOT touch the filesystem itself, so a
    test using it proves the CALLER built a `code.write_file` Decision without depending on the
    real Jaros gate/executor plumbing."""

    def __init__(self) -> None:
        self.applied: list = []

    def apply(self, decision):
        self.applied.append(decision)
        return {"tool": "code.write_file", "path": decision.payload["path"], "applied": True}


class _RejectingRuntime:
    def apply(self, decision):
        raise RuntimeError("gate rejected code.write_file: refused path outside root")


class _R:
    def __init__(self, success):
        self.success, self.attempts = success, 1


# --- _restore: SHARED by /fixrepo's internal revert AND /undo -----------------------------------

def test_restore_runtime_builds_write_file_decisions(tmp_path):
    a = tmp_path / "a.py"
    a.write_text("NEW_A\n")
    b = tmp_path / "b.py"
    b.write_text("NEW_B\n")
    snap = {str(a): "ORIG_A\n", str(b): "ORIG_B\n"}
    rt = _FakeApplyRuntime()

    err = _restore(snap, runtime=rt, root=str(tmp_path))

    assert err is None
    assert len(rt.applied) == 2
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(tmp_path)
    contents = {d.payload["path"]: d.payload["content"] for d in rt.applied}
    assert contents[str(a)] == "ORIG_A\n"
    assert contents[str(b)] == "ORIG_B\n"
    # the FAKE runtime never wrote anything to disk -- proves the restore really goes THROUGH
    # `runtime`, not a raw Path.write_text alongside it.
    assert a.read_text() == "NEW_A\n"
    assert b.read_text() == "NEW_B\n"


def test_restore_runtime_gate_rejection_is_honest_not_a_crash(tmp_path):
    escaping = str(tmp_path.parent / "escape_multifile_restore.py")
    snap = {escaping: "pwned\n"}

    err = _restore(snap, runtime=_RejectingRuntime(), root=str(tmp_path))

    assert err is not None and "failed to write" in err
    assert not os.path.exists(escaping)


def test_restore_runtime_none_is_byte_identical(tmp_path):
    """No regression: every pre-existing caller/test that never passes `runtime` (eval harnesses,
    `harness/refactor.py`, `multi_file_fix`'s own default) keeps the exact direct-write
    behavior."""
    a = tmp_path / "a.py"
    a.write_text("NEW\n")
    err = _restore({str(a): "ORIG\n"})
    assert err is None
    assert a.read_text() == "ORIG\n"


def test_restore_real_runtime_writes_through_gate_and_pathjail(tmp_path):
    from harness.coding_loop import Runtime

    proj = tmp_path / "proj"
    proj.mkdir()
    a = proj / "a.py"
    a.write_text("NEW\n")
    rt = Runtime(data_dir=tmp_path / "state", root=str(proj))

    err = _restore({str(a): "ORIG\n"}, runtime=rt, root=str(proj))
    assert err is None
    assert a.read_text() == "ORIG\n"

    # path-jail still blocks an escape when fed through the SAME real Decision -> Runtime.apply
    # path this function now uses (EXT-037 REQ-1's root-jail, re-checked at the gate).
    escaping = str(tmp_path / "outside_restore.py")
    err2 = _restore({escaping: "pwned\n"}, runtime=rt, root=str(proj))
    assert err2 is not None
    assert not os.path.exists(escaping)


# --- _minimize_edits: the OTHER raw-write sites (~174, ~180) ------------------------------------

def test_minimize_edits_runtime_routes_probes_through_decisions_and_still_minimizes(tmp_path):
    core = tmp_path / "core.py"
    core.write_text("def add(a, b):\n    return a - b  # bug: should be a + b\n")
    helper = tmp_path / "helper.py"
    helper.write_text("from core import add\n\n\ndef combine(a, b):\n    return add(a, b)\n")
    test_file = tmp_path / "test_combine.py"
    test_file.write_text(
        "from helper import combine\n\n\n"
        "def test_combine():\n    assert combine(3, 4) == 7\n",
    )
    orig = _snapshot(str(tmp_path))

    # a redundant caller-side hunk kept early ...
    helper.write_text(
        "from core import add\n\n\ndef combine(a, b):\n    return add(a, b)\n\n\n"
        "def _unused_helper():\n    return None\n",
    )
    # ... then the real root-cause fix landed later. Both edits applied, suite green.
    core.write_text("def add(a, b):\n    return a + b\n")
    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok

    from harness.coding_loop import Runtime
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path))
    kept_paths = [str(helper), str(core)]
    kept_min, dropped = _minimize_edits(str(tmp_path), "pytest -q", orig, kept_paths, runtime=rt)

    assert dropped == ["helper.py"]
    assert [Path(p).name for p in kept_min] == ["core.py"]
    # helper.py was reverted to its ORIGINAL content THROUGH the real Decision/gate path.
    assert helper.read_text(encoding="utf-8") == orig[str(helper)]
    assert "a + b" in core.read_text(encoding="utf-8")

    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok  # still all-green after minimization


def test_minimize_edits_runtime_none_is_byte_identical(tmp_path):
    core = tmp_path / "core.py"
    core.write_text("def add(a, b):\n    return a - b  # bug\n")
    test_file = tmp_path / "test_core.py"
    test_file.write_text("from core import add\n\n\ndef test_add():\n    assert add(3, 4) == 7\n")
    orig = _snapshot(str(tmp_path))
    core.write_text("def add(a, b):\n    return a + b\n")
    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok

    kept_min, dropped = _minimize_edits(str(tmp_path), "pytest -q", orig, [str(core)])
    assert dropped == []
    assert kept_min == [str(core)]
    assert "a + b" in core.read_text(encoding="utf-8")


# --- multi_file_fix: end-to-end (fake fix_loop, per tests/test_ext003_multifile.py) -------------

def test_multi_file_fix_runtime_routes_revert_through_decision(tmp_path, monkeypatch):
    # ok.py is correct; buggy.py holds the fault. A "model" that MANGLES ok.py must be reverted
    # THROUGH a real code.write_file Decision, and the real fix on buggy.py must still land. A
    # REAL Runtime is required here (not the non-writing fake above) since the revert must
    # actually land on disk for the subsequent re-run of the real test suite to pass.
    (tmp_path / "ok.py").write_text("def g(x):\n    return x * 10\n")
    (tmp_path / "buggy.py").write_text("def f(x):\n    return x - 1\n")
    (tmp_path / "test_b.py").write_text(
        "from ok import g\nfrom buggy import f\n\n"
        "def test_f():\n    assert f(3) == 4\n    assert g(2) == 20\n",
    )
    import harness.coding_loop as cl

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

    from jaros.state import DecisionLog
    seen_types: list = []
    orig_append_decision = DecisionLog.append_decision

    def _spy_append_decision(self, record):
        seen_types.append(record.get("type"))
        return orig_append_decision(self, record)

    monkeypatch.setattr(DecisionLog, "append_decision", _spy_append_decision)

    from harness.coding_loop import Runtime
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path))
    r = multi_file_fix(str(tmp_path), "python -m pytest -q", "fix", str(tmp_path / "test_b.py"),
                        runtime=rt)

    assert r["solved"]
    # the harmful ok.py edit was genuinely reverted on disk, through a REAL code.write_file
    # Decision -- hash-chain logged, not a raw Path.write_text alongside it.
    assert "x * 10" in (tmp_path / "ok.py").read_text()
    assert "code.write_file" in seen_types


def test_multi_file_fix_runtime_none_is_byte_identical(tmp_path, monkeypatch):
    (tmp_path / "buggy.py").write_text("def f(x):\n    return x - 1\n")
    (tmp_path / "test_b.py").write_text(
        "from buggy import f\n\ndef test_f():\n    assert f(3) == 4\n")
    import harness.coding_loop as cl

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                       keep_partial=False):
        Path(target).write_text("def f(x):\n    return x + 1\n")
        return _R(True)

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    r = multi_file_fix(str(tmp_path), "python -m pytest -q", "fix", str(tmp_path / "test_b.py"))
    assert r["solved"] and Path(r["file"]).name == "buggy.py"


# --- CLI wiring: /fixrepo and /undo thread a root-anchored Runtime (EXT-037 REQ-10) -------------

def _stub_cli() -> JcodeCli:
    return JcodeCli()


def test_slash_fixrepo_routes_revert_through_real_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ok.py").write_text("def g(x):\n    return x * 10\n")
    (tmp_path / "buggy.py").write_text("def f(x):\n    return x - 1\n")
    (tmp_path / "test_b.py").write_text(
        "from ok import g\nfrom buggy import f\n\n"
        "def test_f():\n    assert f(3) == 4\n    assert g(2) == 20\n",
    )
    import harness.coding_loop as cl

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

    from jaros.state import DecisionLog
    seen_types: list = []
    orig_append_decision = DecisionLog.append_decision

    def _spy_append_decision(self, record):
        seen_types.append(record.get("type"))
        return orig_append_decision(self, record)

    monkeypatch.setattr(DecisionLog, "append_decision", _spy_append_decision)

    cli = _stub_cli()
    out = cli.dispatch("/fixrepo fix it :: python -m pytest -q :: test_b.py")

    assert "solved" in out.lower()
    # the harmful ok.py edit was genuinely reverted, on disk, through a real code.write_file
    # Decision -- hash-chain logged, not a raw Path.write_text.
    assert "x * 10" in (tmp_path / "ok.py").read_text()
    assert "code.write_file" in seen_types


def test_slash_undo_routes_through_real_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "x.py"
    f.write_text("original\n", encoding="utf-8")
    cli = _stub_cli()
    cli._agent_snapshot = _snapshot(".")
    f.write_text("MODIFIED\n", encoding="utf-8")

    from jaros.state import DecisionLog
    seen_types: list = []
    orig_append_decision = DecisionLog.append_decision

    def _spy_append_decision(self, record):
        seen_types.append(record.get("type"))
        return orig_append_decision(self, record)

    monkeypatch.setattr(DecisionLog, "append_decision", _spy_append_decision)

    out = cli.cmd_undo("")
    assert "restored" in out.lower()
    assert f.read_text(encoding="utf-8") == "original\n"
    assert "code.write_file" in seen_types  # a REAL Decision, hash-chain-logged
    assert "nothing to undo" in cli.cmd_undo("").lower()


def test_slash_undo_gate_rejection_is_honest_not_a_crash(tmp_path, monkeypatch):
    """A checkpoint snapshot whose path escapes the project root is refused by the SAME
    EXT-037 path-jail gate any other write Decision goes through -- honestly reported, never a
    crash, and the snapshot is preserved so /undo can be retried."""
    monkeypatch.chdir(tmp_path)
    cli = _stub_cli()
    escaping_path = str(tmp_path.parent / "escape_undo_target.py")
    cli._agent_snapshot = {escaping_path: "original\n"}

    out = cli.cmd_undo("")

    assert "failed" in out.lower()
    assert not os.path.exists(escaping_path)
    assert cli._agent_snapshot is not None  # not cleared -- can retry


def test_undo_still_works_for_a_plain_snapshot_dict(tmp_path, monkeypatch):
    """Regression (mirrors tests/test_agent_loop.py::test_agent_checkpoint_undo): /undo's
    existing behavior/output is unchanged for a normal in-root snapshot."""
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "x.py"
    f.write_text("original\n", encoding="utf-8")
    cli = _stub_cli()
    cli._agent_snapshot = _snapshot(".")
    f.write_text("MODIFIED\n", encoding="utf-8")
    out = cli.cmd_undo("")
    assert "restored" in out.lower()
    assert f.read_text(encoding="utf-8") == "original\n"
    assert "nothing to undo" in cli.cmd_undo("").lower()
