"""Long-term project memory (EXT-009 / REQ-3) — deterministic read/write round-trip.

EXT-042 REQ-5 (Tenet 1): `append_memory`'s optional `runtime` parameter routes the
`.jcode/memory.md` write through a real `code.write_file` Decision instead of a raw
`Path.write_text` — see the "(REQ-5)" section below.
"""
from harness.project_memory import read_memory, append_memory


def test_memory_roundtrip(tmp_path):
    assert read_memory(str(tmp_path)) == ""                     # graceful when absent
    append_memory(str(tmp_path), "prefer type hints on public functions")
    m = read_memory(str(tmp_path))
    assert "jcode project memory" in m
    assert "prefer type hints on public functions" in m
    append_memory(str(tmp_path), "tests live in tests/")
    m2 = read_memory(str(tmp_path))
    assert "prefer type hints" in m2 and "tests live in tests/" in m2   # appends, doesn't clobber
    assert m2.count("# jcode project memory") == 1                       # single header


def test_append_empty_is_noop(tmp_path):
    assert append_memory(str(tmp_path), "   ") == ""
    assert read_memory(str(tmp_path)) == ""


# --- (REQ-5) append_memory routes through a real code.write_file Decision when given a runtime -

class _FakeApplyRuntime:
    def __init__(self) -> None:
        self.applied: list = []

    def apply(self, decision):
        self.applied.append(decision)
        return {"tool": "code.write_file", "path": decision.payload["path"], "applied": True}


def test_append_memory_runtime_builds_write_file_decision(tmp_path):
    rt = _FakeApplyRuntime()
    path = append_memory(str(tmp_path), "use pathlib everywhere", runtime=rt)
    assert path
    assert len(rt.applied) == 1
    d = rt.applied[0]
    assert d.type == "code.write_file"
    assert d.payload["path"].endswith("memory.md")
    assert "use pathlib everywhere" in d.payload["content"]
    # the fake runtime never actually wrote anything to disk -- proves the write really goes
    # THROUGH `runtime`, not a raw Path.write_text alongside it.
    assert read_memory(str(tmp_path)) == ""


def test_append_memory_runtime_none_is_unchanged(tmp_path):
    """No regression: every pre-existing caller/test that never passes `runtime` keeps the
    direct-write behavior exactly as before."""
    path = append_memory(str(tmp_path), "note without a runtime")
    assert path
    assert "note without a runtime" in read_memory(str(tmp_path))


def test_append_memory_runtime_gate_rejection_is_honest_not_a_crash(tmp_path):
    class _RejectingRuntime:
        def apply(self, decision):
            raise RuntimeError("gate rejected code.write_file: refused path outside root")

    result = append_memory(str(tmp_path), "a note", runtime=_RejectingRuntime())
    assert result == ""
    assert read_memory(str(tmp_path)) == ""


def test_append_memory_real_runtime_writes_through_gate(tmp_path):
    """End-to-end through the REAL Jaros gate/executor (no CLI needed)."""
    from harness.coding_loop import Runtime

    proj = tmp_path / "proj"
    proj.mkdir()
    rt = Runtime(data_dir=tmp_path / "state", root=str(proj))
    path = append_memory(str(proj), "a real durable note", runtime=rt)
    assert path
    assert "a real durable note" in read_memory(str(proj))
