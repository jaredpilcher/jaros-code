"""EXT-010 REQ-5 regression: candidate_files must seed its import-closure BFS with the test
file resolved against the target `root`, not the bare `test_file` name read relative to the
PROCESS cwd. Every isolated eval/SWE-bench/daily-driver run has process cwd != target root, so
the bare-seed version raised OSError on the seed read, never walked the import closure, and
returned [] for a cross-file assertion fault -- silently mislabeling a fixable fault as unsolved
WITHOUT ever calling the model. This test is offline/no-model: candidate_files only parses the
traceback text + walks imports, it never runs pytest itself."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.multi_file import candidate_files


def test_candidate_files_localizes_cross_file_fault_from_a_different_process_cwd(tmp_path):
    # 3-file scenario: geometry.py has the bug, shapes.py imports+uses it, test_shapes.py
    # asserts the end value (an assertion failure whose traceback names ONLY the test file --
    # the common case where the import closure is the SOLE path to the culprit).
    (tmp_path / "geometry.py").write_text(
        "def area(w, h):\n    return w + h  # bug: should be w * h\n"
    )
    (tmp_path / "shapes.py").write_text(
        "from geometry import area\n\n\ndef rectangle_area(w, h):\n    return area(w, h)\n"
    )
    (tmp_path / "test_shapes.py").write_text(
        "from shapes import rectangle_area\n\n\n"
        "def test_rectangle_area():\n    assert rectangle_area(3, 4) == 12\n"
    )

    # A realistic pytest assertion-failure output naming only the test file (line 4) --
    # geometry.py/shapes.py are NOT mentioned anywhere in the traceback text, so the ONLY way
    # to find them is the import-closure walk seeded from test_shapes.py.
    test_output = (
        "============================= test session starts ==============================\n"
        "collected 1 item\n\n"
        "test_shapes.py F                                                            [100%]\n\n"
        "=================================== FAILURES ===================================\n"
        "____________________________ test_rectangle_area _______________________________\n\n"
        "    def test_rectangle_area():\n"
        ">       assert rectangle_area(3, 4) == 12\n"
        "E       assert 7 == 12\n"
        "E        +  where 7 = rectangle_area(3, 4)\n\n"
        "test_shapes.py:4: AssertionError\n"
        "=========================== short test summary info ============================\n"
        "FAILED test_shapes.py::test_rectangle_area - assert 7 == 12\n"
        "========================= 1 failed in 0.02s =====================================\n"
    )

    # The process cwd here is the repo root (this test file's parents[1]) -- NOT tmp_path. The
    # pre-fix bare-seed BFS would `Path("test_shapes.py").read_text()`, which reads relative to
    # THIS process cwd (or raises OSError since no such file exists here), so the import closure
    # was never walked and candidate_files returned [].
    assert Path.cwd() != tmp_path  # sanity: we are NOT running from inside tmp_path

    cands = candidate_files(str(tmp_path), test_output, "test_shapes.py")
    names = [Path(c).name for c in cands]

    assert "shapes.py" in names
    assert "geometry.py" in names
    assert "test_shapes.py" not in names
    # guard: the pre-fix bug returned [] for this exact scenario
    assert cands != []
