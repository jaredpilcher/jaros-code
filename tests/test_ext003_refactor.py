"""EXT-003: test-gated rename refactoring. Fully deterministic (no model) — the rename is a
tool and the gate is the real suite, so these run in CI without the Jetson."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.refactor import rename_symbol

_TEST_CMD = "python -m pytest -q"


def test_rename_across_files_keeps_suite_green(tmp_path):
    (tmp_path / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "main.py").write_text("from util import add\n\ndef total(xs):\n    return add(xs[0], xs[1])\n")
    (tmp_path / "test_main.py").write_text("from main import total\n\ndef test_total():\n    assert total([2, 3]) == 5\n")
    r = rename_symbol(str(tmp_path), "add", "plus", _TEST_CMD)
    assert r["renamed"] and r["occurrences"] >= 3      # def + import + call
    assert "def plus(" in (tmp_path / "util.py").read_text()
    assert "add" not in (tmp_path / "main.py").read_text()


def test_rename_that_breaks_tests_is_reverted(tmp_path):
    # renaming foo->bar COLLIDES with the existing bar (two `def bar`; the second shadows),
    # so foo's behavior is lost and the suite goes red -> must revert.
    (tmp_path / "mod.py").write_text("def foo():\n    return 1\n\n\ndef bar():\n    return 2\n")
    (tmp_path / "test_mod.py").write_text(
        "from mod import foo, bar\n\ndef test_both():\n    assert foo() == 1\n    assert bar() == 2\n")
    before = (tmp_path / "mod.py").read_text()
    r = rename_symbol(str(tmp_path), "foo", "bar", _TEST_CMD)
    assert not r["renamed"] and "reverted" in r["note"]
    assert (tmp_path / "mod.py").read_text() == before    # fully restored


def test_rename_requires_green_suite_first(tmp_path):
    (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
    (tmp_path / "test_mod.py").write_text("from mod import f\n\ndef test_f():\n    assert f() == 2\n")  # fails
    r = rename_symbol(str(tmp_path), "f", "g", _TEST_CMD)
    assert not r["renamed"] and "not green" in r["note"]


def test_rename_rejects_non_identifiers(tmp_path):
    r = rename_symbol(str(tmp_path), "old", "2bad", _TEST_CMD)
    assert not r["renamed"] and "identifier" in r["note"]


def test_move_symbol_keeps_suite_green(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 42\n")
    (tmp_path / "b.py").write_text("# target module\n")
    (tmp_path / "test_a.py").write_text("from a import foo\n\ndef test_foo():\n    assert foo() == 42\n")
    from harness.refactor import move_symbol
    r = move_symbol(str(tmp_path), "foo", "a.py", "b.py", _TEST_CMD)
    assert r["moved"]
    assert "def foo" in (tmp_path / "b.py").read_text()
    assert "from b import foo" in (tmp_path / "a.py").read_text()   # re-export keeps importers working


def test_move_symbol_reverts_when_dependency_left_behind(tmp_path):
    # foo needs `import os` which stays in a.py; moved to b.py it NameErrors -> suite red -> revert
    (tmp_path / "a.py").write_text("import os\n\ndef foo():\n    return os.sep\n")
    (tmp_path / "b.py").write_text("# empty\n")
    (tmp_path / "test_a.py").write_text("from a import foo\nimport os\n\ndef test_foo():\n    assert foo() == os.sep\n")
    before = (tmp_path / "a.py").read_text()
    from harness.refactor import move_symbol
    r = move_symbol(str(tmp_path), "foo", "a.py", "b.py", _TEST_CMD)
    assert not r["moved"] and "reverted" in r["note"]
    assert (tmp_path / "a.py").read_text() == before    # fully restored
