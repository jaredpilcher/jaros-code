"""EXT-003 breadth: deterministic file-location for multi-file fixes (harness/multi_file.py).
The fix itself needs the model, but locating WHICH file to fix is parsing+graph (a tool), so
it is unit-testable without inference."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.multi_file import _imported_modules, candidate_files


def test_imported_modules():
    src = "from mathutils import scale\nimport os\nfrom pkg.sub import x\n"
    mods = _imported_modules(src)
    assert "mathutils" in mods and "os" in mods and "pkg" in mods


def test_candidate_files_walks_import_graph(tmp_path):
    (tmp_path / "mathutils.py").write_text("def scale(x):\n    return x + 2\n")
    (tmp_path / "main.py").write_text("from mathutils import scale\ndef apply(i):\n    return [scale(x) for x in i]\n")
    (tmp_path / "test_app.py").write_text("from main import apply\ndef test():\n    assert apply([1]) == [2]\n")
    names = [Path(c).name for c in candidate_files(str(tmp_path), "", str(tmp_path / "test_app.py"))]
    # both reachable modules are candidates; the test file itself is never a candidate
    assert "main.py" in names and "mathutils.py" in names
    assert "test_app.py" not in names


def test_candidate_files_ranks_traceback_first(tmp_path):
    (tmp_path / "mathutils.py").write_text("def scale(x):\n    return x\n")
    (tmp_path / "test_app.py").write_text("def test():\n    pass\n")
    out = f'File "{tmp_path / "mathutils.py"}", line 2, in scale'
    cands = candidate_files(str(tmp_path), out, str(tmp_path / "test_app.py"))
    assert cands and Path(cands[0]).name == "mathutils.py"  # the failure points here -> try first


# --- multi_file_fix ORCHESTRATION (deterministic: mock the model fix, run the REAL test) ---

class _R:
    def __init__(self, success):
        self.success, self.attempts = success, 1


def test_multi_file_fix_locates_and_solves(tmp_path, monkeypatch):
    (tmp_path / "buggy.py").write_text("def f(x):\n    return x - 1\n")  # fault
    (tmp_path / "test_b.py").write_text("from buggy import f\n\ndef test_f():\n    assert f(3) == 4\n")
    import harness.coding_loop as cl

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False):
        if str(target).endswith("buggy.py"):                 # "fix" only the faulty file
            Path(target).write_text("def f(x):\n    return x + 1\n")
            return _R(True)
        return _R(False)

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    from harness.multi_file import multi_file_fix
    r = multi_file_fix(str(tmp_path), "python -m pytest -q", "fix", str(tmp_path / "test_b.py"))
    assert r["solved"] and Path(r["file"]).name == "buggy.py"


def test_multi_file_fix_reverts_a_harmful_attempt(tmp_path, monkeypatch):
    # ok.py is correct; buggy.py holds the fault. A model that MANGLES ok.py must be reverted,
    # and the real fix on buggy.py must still land.
    (tmp_path / "ok.py").write_text("def g(x):\n    return x * 10\n")
    (tmp_path / "buggy.py").write_text("def f(x):\n    return x - 1\n")
    # import ok FIRST so the locator tries (and mangles) ok.py before buggy.py — exercising revert
    (tmp_path / "test_b.py").write_text(
        "from ok import g\nfrom buggy import f\n\ndef test_f():\n    assert f(3) == 4\n    assert g(2) == 20\n")
    import harness.coding_loop as cl

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False):
        if str(target).endswith("ok.py"):
            Path(target).write_text("def g(x):\n    return x  # MANGLED\n")  # breaks g
            return _R(False)
        if str(target).endswith("buggy.py"):
            Path(target).write_text("def f(x):\n    return x + 1\n")
            return _R(True)
        return _R(False)

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    from harness.multi_file import multi_file_fix
    r = multi_file_fix(str(tmp_path), "python -m pytest -q", "fix", str(tmp_path / "test_b.py"))
    assert r["solved"]
    assert "return x * 10" in (tmp_path / "ok.py").read_text()  # harmful edit was reverted
