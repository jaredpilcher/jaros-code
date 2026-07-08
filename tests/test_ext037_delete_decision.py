"""EXT-037 REQ-14: gate host-repo file DELETIONS through a `code.delete_file` Decision
(Tenet 1).

Mirrors the proven REQ-11 test pattern (`tests/test_ext037_buildsystem_jaros_write.py`'s
`_jailed_write` coverage): a fake recording runtime proves every delete is routed through a
real `code.delete_file` Decision, the existing local `path_jail` pre-check is proven
unchanged regardless of `runtime`, a real `harness.coding_loop.Runtime` proves the delete
actually lands through the gate + hash-chain log (dispatched to the new
`.jaros-data/tools/delete_file_tool.py` custom tool), and `runtime=None` (the default) proves
byte-identical behavior for every pre-existing eval/test/suite caller. Fully offline --
no live-model / no Jetson call anywhere in this file.
"""
from __future__ import annotations

# #EXT-037-REQ-14 Start

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import _jailed_delete


class _FakeApplyRuntime:
    """Records every Decision passed to `.apply()` -- does NOT touch the filesystem itself, so
    a test using it proves the CALLER built a `code.delete_file` Decision without depending on
    the real Jaros gate/executor plumbing."""

    def __init__(self) -> None:
        self.applied: list = []

    def apply(self, decision):
        self.applied.append(decision)
        return {"tool": "code.delete_file", "path": decision.payload["path"], "applied": True}


class _RecordingDeletingRuntime:
    """Like `_FakeApplyRuntime`, but actually performs the delete -- proves the on-disk effect
    happens when the caller's runtime chooses to act on the recorded Decision."""

    def __init__(self) -> None:
        self.applied: list = []

    def apply(self, decision):
        self.applied.append(decision)
        path = decision.payload["path"]
        if os.path.isfile(path):
            os.remove(path)
        return {"tool": "code.delete_file", "path": path, "applied": True}


class _RejectingRuntime:
    def apply(self, decision):
        raise RuntimeError("gate rejected code.delete_file: refused path outside root")


# --- _jailed_delete: the single chokepoint -------------------------------------------------

def test_jailed_delete_runtime_builds_delete_file_decision(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text("print('hi')\n", encoding="utf-8")
    rt = _FakeApplyRuntime()

    err = _jailed_delete(tmp_path, "mod.py", rt)

    assert err is None
    assert len(rt.applied) == 1
    d = rt.applied[0]
    assert d.type == "code.delete_file"
    assert d.payload["root"] == str(tmp_path)
    assert d.payload["path"] == str(target)
    # the FAKE runtime never touched the filesystem -- proves the delete really goes THROUGH
    # `runtime`, not a raw Path.unlink() alongside it.
    assert target.exists()


def test_jailed_delete_runtime_that_executes_actually_removes_the_file(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text("print('hi')\n", encoding="utf-8")
    rt = _RecordingDeletingRuntime()

    err = _jailed_delete(tmp_path, "mod.py", rt)

    assert err is None
    assert len(rt.applied) == 1
    assert rt.applied[0].type == "code.delete_file"
    assert not target.exists()


def test_jailed_delete_runtime_gate_rejection_is_honest_not_a_crash(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text("print('hi')\n", encoding="utf-8")

    err = _jailed_delete(tmp_path, "mod.py", _RejectingRuntime())

    assert err is not None
    assert "failed to delete" in err
    # a gate rejection never has a partial/side effect -- the file is untouched.
    assert target.exists()


def test_jailed_delete_local_pathjail_rejection_unchanged_regardless_of_runtime(tmp_path):
    """The local `path_jail` pre-check (REQ-1) runs UNCONDITIONALLY first -- an escaping `name`
    is refused with the exact same rejection whether or not a `runtime` is supplied, and no
    Decision is ever built for it."""
    outside = tmp_path.parent / "evil.py"
    outside.write_text("pwned\n", encoding="utf-8")
    try:
        err_none = _jailed_delete(tmp_path, "../evil.py", None)
        assert err_none is not None
        assert outside.exists()  # never deleted

        rt = _FakeApplyRuntime()
        err_rt = _jailed_delete(tmp_path, "../evil.py", rt)
        assert err_rt is not None
        assert err_rt == err_none  # identical rejection reason regardless of runtime
        assert rt.applied == []  # never even built a Decision for a rejected path
        assert outside.exists()  # still never deleted
    finally:
        if outside.exists():
            outside.unlink()


def test_jailed_delete_runtime_none_is_byte_identical(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text("print('hi')\n", encoding="utf-8")

    err = _jailed_delete(tmp_path, "mod.py", None)

    assert err is None
    assert not target.exists()


def test_jailed_delete_missing_file_is_a_silent_noop_with_and_without_runtime(tmp_path):
    # runtime=None: raw path, no file present.
    assert _jailed_delete(tmp_path, "nope.py", None) is None

    # runtime supplied: the file still doesn't exist, so `os.path.isfile` in the delete tool
    # (once dispatched) is False and nothing is attempted -- a silent no-op success either way.
    rt = _FakeApplyRuntime()
    assert _jailed_delete(tmp_path, "nope.py", rt) is None
    assert len(rt.applied) == 1
    assert rt.applied[0].type == "code.delete_file"


# --- real Runtime + the new code.delete_file custom tool -----------------------------------

def test_real_runtime_records_delete_decision_on_hash_chain_and_removes_file(tmp_path):
    from harness.coding_loop import Runtime
    from jaros.state import DecisionLog

    seen_types: list = []
    orig_append_decision = DecisionLog.append_decision

    def _spy_append_decision(self, record):
        seen_types.append(record.get("type"))
        return orig_append_decision(self, record)

    root = tmp_path / "built"
    root.mkdir()
    target = root / "stale.py"
    target.write_text("print('stale')\n", encoding="utf-8")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(DecisionLog, "append_decision", _spy_append_decision)
        rt = Runtime(data_dir=tmp_path / "state", root=str(root))
        err = _jailed_delete(root, "stale.py", rt)

    assert err is None
    assert not target.exists()
    assert "code.delete_file" in seen_types


def test_real_runtime_delete_missing_file_is_a_silent_noop(tmp_path):
    from harness.coding_loop import Runtime

    root = tmp_path / "built"
    root.mkdir()
    rt = Runtime(data_dir=tmp_path / "state", root=str(root))

    err = _jailed_delete(root, "never_existed.py", rt)

    assert err is None
# #EXT-037-REQ-14 End
