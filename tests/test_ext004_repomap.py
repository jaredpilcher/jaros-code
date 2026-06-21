"""EXT-004: deterministic repo map (symbol extraction + connectivity ranking)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.repo_map import _symbols, build_repo_map


def test_symbols_extracts_top_level_defs_classes():
    src = "import os\n\ndef foo():\n    pass\n\nclass Bar:\n    def method(self):\n        pass\n\nx = 1\n"
    syms = _symbols(src)
    assert syms == ["foo", "Bar"]  # top-level only; method/x excluded


def test_symbols_handles_syntax_error():
    assert _symbols("def broken(:\n") == []


def test_repo_map_ranks_referenced_files_first(tmp_path):
    # util.helper is referenced by two other files -> util should outrank the leaf consumers
    (tmp_path / "util.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "a.py").write_text("from util import helper\n\ndef ay():\n    return helper()\n")
    (tmp_path / "b.py").write_text("from util import helper\n\ndef be():\n    return helper()\n")
    out = build_repo_map(str(tmp_path))
    lines = out.splitlines()
    assert any(l.startswith("util.py:") for l in lines)
    assert lines[0].startswith("util.py:")  # most-referenced ranked first
