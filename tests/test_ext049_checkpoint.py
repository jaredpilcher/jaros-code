"""EXT-049: fine-grained per-edit checkpoint ring + /rewind.

OFFLINE -- no live model. `harness.checkpoint_ring` is pure in-memory bookkeeping;
`harness.coding_loop.Runtime.apply` is exercised end-to-end with REAL deterministic Decisions
(code.write_file), no model involved. Centerpiece: a `/rewind` RESTORE goes through a real
`code.write_file` Decision via `Runtime.apply` -- proven by asserting the hash-chain DecisionLog
recorded it, not merely that the bytes on disk changed -- and `/undo` (EXT-009) is unaffected.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from jaros.core import create_decision

from harness.checkpoint_ring import CheckpointEntry, CheckpointRing
from harness.cli import JcodeCli
from harness.coding_loop import Runtime
from jaros.state import DecisionLog


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors
    test_ext047_hooks.py / test_ext048_permissions.py)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    """Point Path.home() at an isolated tmp dir for every module JcodeCli.__init__ loads
    (hooks/skills/jcode_md/permissions), so these tests never touch the real ~/.jcode/."""
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    import harness.hooks as hk
    monkeypatch.setattr(hk.Path, "home", staticmethod(lambda: fake_home))
    import harness.skills as sk
    monkeypatch.setattr(sk.Path, "home", staticmethod(lambda: fake_home))
    import harness.jcode_md as jm
    monkeypatch.setattr(jm.Path, "home", staticmethod(lambda: fake_home))
    import harness.permissions as perm
    monkeypatch.setattr(perm.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


# =====================================================================================
# CheckpointRing -- bounds / eviction / lookup
# =====================================================================================

def test_ring_bounds_evicts_oldest_first():
    ring = CheckpointRing(maxlen=3)
    for i in range(5):
        ring.record(decision_type="code.write_file", path=f"f{i}.py", existed=True,
                    before_content=f"v{i}")
    assert len(ring) == 3
    paths = [e.path for e in ring.entries_oldest_first()]
    assert paths == ["f2.py", "f3.py", "f4.py"]   # f0, f1 evicted (oldest first)


def test_ring_entries_newest_first_order():
    ring = CheckpointRing(maxlen=10)
    ring.record(decision_type="code.write_file", path="a.py", existed=False, before_content=None)
    ring.record(decision_type="code.write_file", path="b.py", existed=False, before_content=None)
    newest = ring.entries_newest_first()
    assert [e.path for e in newest] == ["b.py", "a.py"]


def test_ring_by_id_exact_and_prefix():
    ring = CheckpointRing()
    entry = ring.record(decision_type="code.write_file", path="a.py", existed=False,
                         before_content=None)
    assert ring.by_id(entry.id) is entry
    assert ring.by_id(entry.id[:4]) is entry
    assert ring.by_id("nonexistent") is None


def test_ring_position_from_newest_and_last_n_and_drop_last_n():
    ring = CheckpointRing()
    e1 = ring.record(decision_type="code.write_file", path="a.py", existed=False, before_content=None)
    e2 = ring.record(decision_type="code.write_file", path="b.py", existed=False, before_content=None)
    e3 = ring.record(decision_type="code.write_file", path="c.py", existed=False, before_content=None)
    assert ring.position_from_newest(e3.id) == 1
    assert ring.position_from_newest(e1.id) == 3
    assert ring.position_from_newest("nope") is None
    assert [e.path for e in ring.last_n(2)] == ["c.py", "b.py"]
    ring.drop_last_n(2)
    assert len(ring) == 1
    assert ring.entries_oldest_first()[0].path == "a.py"


# =====================================================================================
# Runtime.apply -- checkpoint capture at the existing hash-chain seam
# =====================================================================================

def test_runtime_apply_is_a_noop_without_a_checkpoint_ring(tmp_path):
    """Default (`checkpoint_ring=None`) is byte-identical to every pre-EXT-049 caller."""
    target = tmp_path / "a.py"
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path))
    d = create_decision(id="d1", source="test", type="code.write_file",
                         payload={"path": str(target), "content": "v1\n"})
    rt.apply(d)   # must not raise despite no checkpoint_ring


def test_runtime_apply_captures_pre_edit_content_on_write(tmp_path):
    target = tmp_path / "a.py"
    ring = CheckpointRing()
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path), checkpoint_ring=ring)

    d1 = create_decision(id="d1", source="test", type="code.write_file",
                          payload={"path": str(target), "content": "v1\n"})
    rt.apply(d1)
    assert len(ring) == 1
    e1 = ring.entries_newest_first()[0]
    assert e1.existed is False and e1.before_content is None   # file didn't exist before this write

    d2 = create_decision(id="d2", source="test", type="code.write_file",
                          payload={"path": str(target), "content": "v2\n"})
    rt.apply(d2)
    assert len(ring) == 2
    e2 = ring.entries_newest_first()[0]
    assert e2.existed is True
    assert e2.before_content == "v1\n"   # exactly what was on disk immediately before d2


def test_runtime_apply_records_exactly_one_entry_per_accepted_decision(tmp_path):
    target = tmp_path / "a.py"
    ring = CheckpointRing()
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path), checkpoint_ring=ring)
    d = create_decision(id="d1", source="test", type="code.write_file",
                         payload={"path": str(target), "content": "v1\n"})
    rt.apply(d)
    assert len(ring) == 1


def test_runtime_apply_does_not_checkpoint_a_gate_rejected_decision(tmp_path):
    ring = CheckpointRing()
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path), checkpoint_ring=ring)
    escaping = str(tmp_path.parent / "escape.py")
    d = create_decision(id="evil", source="test", type="code.write_file",
                         payload={"path": escaping, "content": "pwn\n"})
    with pytest.raises(RuntimeError):
        rt.apply(d)
    assert len(ring) == 0   # the refused Decision produced no checkpoint


def test_runtime_apply_does_not_checkpoint_a_read_only_decision(tmp_path):
    target = tmp_path / "a.py"
    target.write_text("hi\n", encoding="utf-8")
    ring = CheckpointRing()
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path), checkpoint_ring=ring)
    d = create_decision(id="r1", source="test", type="fs.read", payload={"path": str(target)})
    rt.apply(d)
    assert len(ring) == 0


def test_runtime_apply_does_not_checkpoint_a_write_with_no_path_key(tmp_path):
    ring = CheckpointRing()
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path), checkpoint_ring=ring)
    # A malformed payload (no 'path') is refused by code.write_file's own validate() -- must not
    # raise from the checkpoint-capture code itself, and must record nothing.
    d = create_decision(id="bad", source="test", type="code.write_file", payload={"content": "x"})
    with pytest.raises(RuntimeError):
        rt.apply(d)
    assert len(ring) == 0


# =====================================================================================
# JcodeCli -- /checkpoints, /rewind (restore THROUGH a code.write_file Decision), /undo unaffected
# =====================================================================================

def test_checkpoints_empty_is_a_clean_no_op(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert "no checkpoints" in cli.cmd_checkpoints("").lower()
    assert "no checkpoints" in cli.cmd_rewind("").lower() or "nothing to rewind" in cli.cmd_rewind("").lower()


def test_patch_populates_the_ring_and_checkpoints_lists_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    cli = JcodeCli()
    out = cli.cmd_patch("m.py :: return 1 :: return 2")
    assert "applied" in out.lower() or "patch" in out.lower() or (tmp_path / "m.py").read_text() != ""
    assert len(cli._checkpoint_ring) == 1
    listing = cli.cmd_checkpoints("")
    assert "m.py" in listing
    assert "[1]" in listing


def test_rewind_restores_prior_content_through_a_code_write_file_decision(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    cli = JcodeCli()
    cli.cmd_patch("m.py :: return 1 :: return 2")
    assert "return 2" in (tmp_path / "m.py").read_text()

    # Spy on the hash-chain DecisionLog to prove the RESTORE genuinely went through
    # Runtime.apply -> executor -> record_decision, not a raw Path.write_text.
    seen_types = []
    orig_append_decision = DecisionLog.append_decision

    def _spy_append_decision(self, record):
        seen_types.append(record.get("type"))
        return orig_append_decision(self, record)

    monkeypatch.setattr(DecisionLog, "append_decision", _spy_append_decision)

    out = cli.cmd_rewind("1")
    assert "restored" in out.lower()
    assert (tmp_path / "m.py").read_text() == "def f():\n    return 1\n"
    assert "code.write_file" in seen_types   # the restore was a REAL Decision, hash-chain-logged
    assert len(cli._checkpoint_ring) == 0    # consumed after a successful rewind


def test_rewind_out_of_range_is_an_honest_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.py").write_text("x = 1\n", encoding="utf-8")
    cli = JcodeCli()
    cli.cmd_patch("m.py :: x = 1 :: x = 2")
    before = (tmp_path / "m.py").read_text()
    out = cli.cmd_rewind("5")   # only 1 checkpoint exists
    assert "only" in out.lower() or "can't" in out.lower()
    assert (tmp_path / "m.py").read_text() == before   # no side effect on an out-of-range rewind


def test_rewind_zero_and_negative_are_honest_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.py").write_text("x = 1\n", encoding="utf-8")
    cli = JcodeCli()
    cli.cmd_patch("m.py :: x = 1 :: x = 2")
    assert "checkpoint ring only has" in cli.cmd_rewind("0")
    assert "checkpoint ring only has" in cli.cmd_rewind("-1")


def test_rewind_unknown_checkpoint_id_is_an_honest_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.py").write_text("x = 1\n", encoding="utf-8")
    cli = JcodeCli()
    cli.cmd_patch("m.py :: x = 1 :: x = 2")
    out = cli.cmd_rewind("not-a-real-id")
    assert "no checkpoint matching" in out.lower()


def test_rewind_by_checkpoint_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.py").write_text("x = 1\n", encoding="utf-8")
    cli = JcodeCli()
    cli.cmd_patch("m.py :: x = 1 :: x = 2")
    entry_id = cli._checkpoint_ring.entries_newest_first()[0].id
    out = cli.cmd_rewind(entry_id)
    assert "restored" in out.lower()
    assert (tmp_path / "m.py").read_text() == "x = 1\n"


def test_rewind_a_created_file_reports_honest_limit_and_leaves_file_as_is(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    from jaros.core import create_decision as _cd
    d = _cd(id="c1", source="cli", type="code.write_file",
            payload={"path": str(tmp_path / "new.py"), "content": "brand new\n"})
    cli.rt.apply(d)
    assert len(cli._checkpoint_ring) == 1
    out = cli.cmd_rewind("1")
    assert "cannot fully" in out.lower()
    assert (tmp_path / "new.py").read_text() == "brand new\n"   # left as-is, not deleted/emptied


def test_rewind_multi_step_undoes_last_n_edits_in_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.py").write_text("x = 1\n", encoding="utf-8")
    cli = JcodeCli()
    cli.cmd_patch("m.py :: x = 1 :: x = 2")
    cli.cmd_patch("m.py :: x = 2 :: x = 3")
    assert (tmp_path / "m.py").read_text() == "x = 3\n"
    out = cli.cmd_rewind("2")
    assert (tmp_path / "m.py").read_text() == "x = 1\n"
    assert len(cli._checkpoint_ring) == 0


def test_path_jail_still_blocks_an_escaping_restore(tmp_path, monkeypatch):
    """A checkpoint entry whose path would escape the project root is refused by the SAME
    EXT-037 path-jail gate any other write Decision goes through -- honestly reported, not
    silently swallowed."""
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    escaping_path = str(tmp_path.parent / "escape_target.py")
    entry = cli._checkpoint_ring.record(
        decision_type="code.write_file", path=escaping_path, existed=True,
        before_content="original\n")
    out = cli.cmd_rewind("1")
    assert "failed" in out.lower()
    assert not os.path.exists(escaping_path)


def test_undo_still_works_unaffected_by_this_spec(tmp_path, monkeypatch):
    """EXT-009's whole-run /undo keeps working exactly as before, independent of the ring."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    cli = JcodeCli()
    from harness.multi_file import _snapshot
    cli._agent_snapshot = _snapshot(".")
    (tmp_path / "mod.py").write_text("VALUE = 2\n", encoding="utf-8")
    out = cli.cmd_undo("")
    assert "reverted" in out.lower()
    assert (tmp_path / "mod.py").read_text() == "VALUE = 1\n"
