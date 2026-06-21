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
