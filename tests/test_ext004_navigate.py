"""EXT-004: AST-based find-usages — precise (ignores strings/comments)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.navigate import find_usages


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
