"""Long-term project memory (EXT-009 / REQ-3) — deterministic read/write round-trip."""
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
