"""EXT-037 REQ-9: harness/refactor.py's `/rename`/`/move` writes are Jaros-native (Tenet 1).

Mirrors the proven EXT-042 REQ-5 test pattern (`tests/test_ext042_jcode_md.py`): a fake
recording runtime proves every write is routed through a real `code.write_file` Decision, a
rejecting fake runtime proves a gate rejection degrades to an honest error (never a crash), a
real `harness.coding_loop.Runtime` proves the write actually lands through the gate + EXT-037
root-jail, and `runtime=None` (the default) proves byte-identical behavior for every pre-existing
eval/test caller. Fully offline/deterministic (no live model).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli
from harness.refactor import move_symbol, rename_symbol

_TEST_CMD = "python -m pytest -q"


class _FakeApplyRuntime:
    """Records every Decision passed to `.apply()` — does NOT touch the filesystem itself, so a
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


# --- rename_symbol: Decision routing, gate rejection, runtime=None regression ------------------

def test_rename_symbol_runtime_builds_write_file_decisions(tmp_path):
    (tmp_path / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "test_util.py").write_text(
        "from util import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    rt = _FakeApplyRuntime()
    r = rename_symbol(str(tmp_path), "add", "plus", _TEST_CMD, runtime=rt)
    assert len(rt.applied) >= 1
    d = rt.applied[0]
    assert d.type == "code.write_file"
    assert d.payload["root"] == str(tmp_path)
    assert "plus" in d.payload["content"]
    # the FAKE runtime never wrote anything to disk -- proves the write really goes THROUGH
    # `runtime`, not a raw Path.write_text alongside it.
    assert "def plus(" not in (tmp_path / "util.py").read_text()
    assert r["occurrences"] >= 1


def test_rename_symbol_runtime_gate_rejection_is_honest_not_a_crash(tmp_path):
    (tmp_path / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "test_util.py").write_text(
        "from util import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    before = (tmp_path / "util.py").read_text()
    r = rename_symbol(str(tmp_path), "add", "plus", _TEST_CMD, runtime=_RejectingRuntime())
    assert r["renamed"] is False
    assert "failed to write" in r["note"]
    # never a crash, and the snapshot/restore leaves the repo genuinely unchanged
    assert (tmp_path / "util.py").read_text() == before


def test_rename_symbol_runtime_none_is_byte_identical(tmp_path):
    """No regression: every pre-existing caller/test that never passes `runtime` (eval harnesses,
    tests/test_ext003_refactor.py) keeps the exact direct-write behavior."""
    (tmp_path / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "main.py").write_text(
        "from util import add\n\ndef total(xs):\n    return add(xs[0], xs[1])\n")
    (tmp_path / "test_main.py").write_text(
        "from main import total\n\ndef test_total():\n    assert total([2, 3]) == 5\n")
    r = rename_symbol(str(tmp_path), "add", "plus", _TEST_CMD)
    assert r["renamed"] and r["occurrences"] >= 3
    assert "def plus(" in (tmp_path / "util.py").read_text()


def test_rename_symbol_real_runtime_writes_through_gate_and_pathjail(tmp_path):
    from harness.coding_loop import Runtime

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (proj / "test_util.py").write_text(
        "from util import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    rt = Runtime(data_dir=tmp_path / "state", root=str(proj))
    r = rename_symbol(str(proj), "add", "plus", _TEST_CMD, runtime=rt)
    assert r["renamed"] is True
    assert "def plus(" in (proj / "util.py").read_text()

    # path-jail still blocks an escape when fed through the SAME real Decision -> Runtime.apply
    # path this function now uses (EXT-037 REQ-1's root-jail, re-checked at the gate).
    from jaros.core import create_decision
    escaping = create_decision(
        id="escape-rename-1", source="test", type="code.write_file",
        payload={"path": str(tmp_path / "etc" / "x"), "content": "pwned\n", "root": str(proj)})
    with pytest.raises(RuntimeError, match="root"):
        rt.apply(escaping)
    assert not (tmp_path / "etc" / "x").exists()


# --- move_symbol: Decision routing, gate rejection, runtime=None regression --------------------

def test_move_symbol_runtime_builds_write_file_decisions(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 42\n")
    (tmp_path / "b.py").write_text("# target module\n")
    (tmp_path / "test_a.py").write_text(
        "from a import foo\n\ndef test_foo():\n    assert foo() == 42\n")
    rt = _FakeApplyRuntime()
    move_symbol(str(tmp_path), "foo", "a.py", "b.py", _TEST_CMD, runtime=rt)
    assert len(rt.applied) == 2
    paths = {d.payload["path"] for d in rt.applied}
    assert any(p.endswith("a.py") for p in paths)
    assert any(p.endswith("b.py") for p in paths)
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(tmp_path)
    # the FAKE runtime never wrote anything to disk
    assert "def foo" not in (tmp_path / "b.py").read_text()


def test_move_symbol_runtime_gate_rejection_is_honest_not_a_crash(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 42\n")
    (tmp_path / "b.py").write_text("# target module\n")
    (tmp_path / "test_a.py").write_text(
        "from a import foo\n\ndef test_foo():\n    assert foo() == 42\n")
    before_a = (tmp_path / "a.py").read_text()
    before_b = (tmp_path / "b.py").read_text()
    r = move_symbol(str(tmp_path), "foo", "a.py", "b.py", _TEST_CMD, runtime=_RejectingRuntime())
    assert r["moved"] is False
    assert "failed to write" in r["note"]
    assert (tmp_path / "a.py").read_text() == before_a
    assert (tmp_path / "b.py").read_text() == before_b


def test_move_symbol_runtime_none_is_byte_identical(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 42\n")
    (tmp_path / "b.py").write_text("# target module\n")
    (tmp_path / "test_a.py").write_text(
        "from a import foo\n\ndef test_foo():\n    assert foo() == 42\n")
    r = move_symbol(str(tmp_path), "foo", "a.py", "b.py", _TEST_CMD)
    assert r["moved"]
    assert "def foo" in (tmp_path / "b.py").read_text()
    assert "from b import foo" in (tmp_path / "a.py").read_text()


def test_move_symbol_real_runtime_writes_through_gate_and_pathjail(tmp_path):
    from harness.coding_loop import Runtime

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def foo():\n    return 42\n")
    (proj / "b.py").write_text("# target module\n")
    (proj / "test_a.py").write_text(
        "from a import foo\n\ndef test_foo():\n    assert foo() == 42\n")
    rt = Runtime(data_dir=tmp_path / "state", root=str(proj))
    r = move_symbol(str(proj), "foo", "a.py", "b.py", _TEST_CMD, runtime=rt)
    assert r["moved"] is True
    assert "def foo" in (proj / "b.py").read_text()
    assert "from b import foo" in (proj / "a.py").read_text()


# --- CLI wiring: /rename and /move thread a root-anchored Runtime (EXT-037 REQ-9) --------------

def _stub_cli() -> JcodeCli:
    return JcodeCli()


def test_slash_rename_routes_through_real_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "test_util.py").write_text(
        "from util import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    cli = _stub_cli()
    out = cli.dispatch("/rename add plus")
    assert "renamed" in out
    assert "def plus(" in (tmp_path / "util.py").read_text()


def test_slash_move_routes_through_real_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("def foo():\n    return 42\n")
    (tmp_path / "b.py").write_text("# target module\n")
    (tmp_path / "test_a.py").write_text(
        "from a import foo\n\ndef test_foo():\n    assert foo() == 42\n")
    cli = _stub_cli()
    out = cli.dispatch("/move foo a.py b.py")
    assert "moved" in out
    assert "def foo" in (tmp_path / "b.py").read_text()
    assert "from b import foo" in (tmp_path / "a.py").read_text()
