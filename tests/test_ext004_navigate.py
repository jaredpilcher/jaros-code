"""EXT-004: AST-based find-usages — precise (ignores strings/comments)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.navigate import find_usages, find_dead_code, find_definition, find_callers


def test_find_usages_finds_def_and_refs(tmp_path):
    (tmp_path / "util.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "main.py").write_text("from util import helper\n\ndef run():\n    return helper() + helper()\n")
    us = find_usages(str(tmp_path), "helper")
    kinds = {(u["file"], u["kind"]) for u in us}
    assert ("util.py", "def") in kinds
    assert sum(1 for u in us if u["kind"] == "ref") == 2   # two helper() calls


def test_find_usages_is_ast_precise(tmp_path):
    (tmp_path / "util.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "main.py").write_text('MSG = "please helper now"   # comment mentions helper\n\ndef run():\n    return helper()\n')
    us = find_usages(str(tmp_path), "helper")
    # the string literal and the comment must NOT be counted (grep would match both)
    assert all("MSG" not in u["text"] for u in us)
    assert any(u["kind"] == "ref" and u["file"] == "main.py" for u in us)


def test_find_dead_code(tmp_path):
    (tmp_path / "lib.py").write_text("def used():\n    return 1\n\n\ndef orphan():\n    return 2\n")
    (tmp_path / "main.py").write_text("from lib import used\n\ndef run():\n    return used()\n")
    (tmp_path / "test_main.py").write_text("from main import run\n\ndef test_run():\n    assert run() == 1\n")
    dead = {d["symbol"] for d in find_dead_code(str(tmp_path))}
    assert "orphan" in dead        # referenced nowhere
    assert "used" not in dead      # called by run()
    assert "run" not in dead       # referenced by the test
    assert "test_run" not in dead  # test-file def excluded (pytest entry point)


def test_find_definition(tmp_path):
    (tmp_path / "m.py").write_text(
        "def target():\n    return 1\n\nclass Thing:\n    pass\n\nx = target()\n")
    defs = find_definition(str(tmp_path), "target")
    assert len(defs) == 1 and defs[0]["kind"] == "def" and defs[0]["line"] == 1
    cdefs = find_definition(str(tmp_path), "Thing")
    assert len(cdefs) == 1 and cdefs[0]["kind"] == "class"
    assert find_definition(str(tmp_path), "nonexistent") == []


def test_find_callers(tmp_path):
    (tmp_path / "m.py").write_text(
        "def target():\n    return 1\n\ndef outer():\n    return target()\n\nz = target()\n")
    cs = find_callers(str(tmp_path), "target")
    assert sorted(c["caller"] for c in cs) == ["<module>", "outer"]
    assert all(c["file"] == "m.py" for c in cs)
    assert find_callers(str(tmp_path), "nonexistent") == []
