"""EXT-005 REQ-5 external benchmark loaders: MBPP + MultiPL-E (JS).

Deterministic harness checks (no model): feed each loader's generated test harness the
KNOWN-CORRECT reference solution and confirm it passes — proving the plumbing is honest
before we trust gemma2:2b numbers on it. Skips gracefully when a dataset or toolchain is
absent (e.g. CI without the gitignored data), never a silent pass.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_mbpp_reference_solutions_pass_generated_harness():
    from harness import mbpp
    if not mbpp.DATASET.is_file():
        pytest.skip("MBPP dataset not present (gitignored)")
    probs = mbpp._read_problems()[:5]
    passed = 0
    for p in probs:
        task = mbpp.problem_to_task(p)
        if task is None:
            continue
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            (dp / "solution.py").write_text(p["code"], encoding="utf-8")
            (dp / "test_solution.py").write_text(task.files["test_solution.py"], encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=d,
                               capture_output=True, text=True)
            passed += r.returncode == 0
    assert passed == 5, "MBPP reference solutions must satisfy their own generated tests"


def test_multipl_e_js_known_solution_passes_runner():
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    from harness import multipl_e
    if not (multipl_e.BENCH / "humaneval-js.parquet").is_file():
        pytest.skip("MultiPL-E humaneval-js parquet not present (gitignored)")
    probs = multipl_e._read_problems("js")
    p = next(x for x in probs if x["name"].startswith("HumanEval_23_"))  # strlen
    task = multipl_e.problem_to_task(p, "js")
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        (dp / "solution.js").write_text(p["prompt"] + "\n  return string.length;\n}\n", encoding="utf-8")
        (dp / "tests.js").write_text(task.files["tests.js"], encoding="utf-8")
        (dp / "run.js").write_text(task.files["run.js"], encoding="utf-8")
        r = subprocess.run(["node", "run.js"], cwd=d, capture_output=True, text=True)
    assert r.returncode == 0, f"MultiPL-E JS harness rejected a correct solution: {r.stderr[:200]}"
