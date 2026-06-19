"""EXT-003 boundary-mutation repair: the honest, model-free decomposition.

Every *model-side* slice (locate line / fix line / quote snippet) bottomed out on a
judgement gemma2:2b cannot make (`<` vs `<=`). So the fix moved into the deterministic
plane: try each single-operator boundary mutation, keep the one that passes the suite.
These tests need NO model — they are fully deterministic and reproducible (Tenet 3).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import boundary_repair_candidates, mutation_repair_loop  # noqa: E402

BSEARCH_BUG = (
    "def search(arr, target):\n"
    "    lo, hi = 0, len(arr) - 1\n"
    "    while lo < hi:\n"
    "        mid = (lo + hi) // 2\n"
    "        if arr[mid] == target:\n"
    "            return mid\n"
    "        elif arr[mid] < target:\n"
    "            lo = mid + 1\n"
    "        else:\n"
    "            hi = mid - 1\n"
    "    return -1\n"
)
BSEARCH_TEST = (
    "from bsearch import search\n\n\n"
    "def test_search():\n"
    "    assert search([1, 3, 5, 7, 9], 7) == 3\n"
    "    assert search([1, 3, 5, 7, 9], 1) == 0\n"
    "    assert search([1, 3, 5, 7, 9], 9) == 4\n"
    "    assert search([1, 3, 5, 7, 9], 4) == -1\n"
)


def test_candidates_are_pure_and_single_edit():
    cands = boundary_repair_candidates(BSEARCH_BUG)
    # Every candidate differs from the source and from each other (de-duplicated).
    assert all(c != BSEARCH_BUG for c in cands)
    assert len(cands) == len(set(cands))
    # The fix we need — `while lo < hi:` -> `while lo <= hi:` — must be in the space.
    assert any("while lo <= hi:" in c and c.count("<=") == 1 for c in cands)


def test_candidates_deterministic():
    assert boundary_repair_candidates(BSEARCH_BUG) == boundary_repair_candidates(BSEARCH_BUG)


def test_mutation_repair_cracks_binary_search():
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        (dp / "bsearch.py").write_text(BSEARCH_BUG, encoding="utf-8", newline="\n")
        (dp / "test_bsearch.py").write_text(BSEARCH_TEST, encoding="utf-8", newline="\n")
        res = mutation_repair_loop(str(dp / "bsearch.py"), "python -m pytest -q", cwd=str(dp))
        assert res.success is True
        fixed = (dp / "bsearch.py").read_text(encoding="utf-8")
        assert "while lo <= hi:" in fixed


def test_mutation_repair_restores_on_failure():
    # A bug NOT in the boundary class: repair fails and must leave the file untouched.
    src = "def f():\n    return 1 / 0\n"
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        (dp / "m.py").write_text(src, encoding="utf-8", newline="\n")
        (dp / "test_m.py").write_text("from m import f\n\n\ndef test_f():\n    assert f() == 0\n",
                                      encoding="utf-8", newline="\n")
        res = mutation_repair_loop(str(dp / "m.py"), "python -m pytest -q", cwd=str(dp))
        assert res.success is False
        assert (dp / "m.py").read_text(encoding="utf-8") == src  # original restored
