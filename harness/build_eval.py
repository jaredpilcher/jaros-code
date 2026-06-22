"""Multi-requirement BUILD eval (EXT-009 / REQ-6, build variant): measure the jarify-flow's
decomposition on MULTI-FUNCTION builds — where free-form / single-function generation can't reach.

Each scenario is a high-level intent naming several functions. `spec_driven_loop` decomposes it
into requirements, writes a test per requirement, implements, and verifies. We then score against
a HIDDEN ORACLE (a held-out test the system never saw) exercising ALL functions — the un-gameable
"did it meet intent" measure (the EXT-008 pattern). Records suite="build" to the trend history.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from harness.eval_runner import MODEL, _persist
from harness.report import census

# #EXT-009-REQ-6 Start
SCENARIOS = [
    {
        "name": "calculator",
        "intent": "a math module with a function add(a, b) that adds, subtract(a, b) that "
                  "subtracts the second from the first, and multiply(a, b) that multiplies",
        "oracle": ("from solution import add, subtract, multiply\n\n"
                   "def test_all():\n"
                   "    assert add(2, 3) == 5\n"
                   "    assert subtract(5, 2) == 3\n"
                   "    assert multiply(4, 6) == 24\n"),
    },
    {
        "name": "stringops",
        "intent": "a string module with reverse(s) that reverses a string, shout(s) that returns "
                  "it uppercased, and vowel_count(s) that counts the vowels",
        "oracle": ("from solution import reverse, shout, vowel_count\n\n"
                   "def test_all():\n"
                   "    assert reverse('abc') == 'cba'\n"
                   "    assert shout('hi') == 'HI'\n"
                   "    assert vowel_count('hello') == 2\n"),
    },
    {
        "name": "listops",
        "intent": "a list module with largest(xs) returning the max, smallest(xs) returning the "
                  "min, and total(xs) returning the sum",
        "oracle": ("from solution import largest, smallest, total\n\n"
                   "def test_all():\n"
                   "    assert largest([1, 5, 2]) == 5\n"
                   "    assert smallest([3, 1, 2]) == 1\n"
                   "    assert total([1, 2, 3]) == 6\n"),
    },
    {
        "name": "boolchecks",
        "intent": "a number module with is_even(n) returning True when n is even, is_odd(n) "
                  "returning True when n is odd, and is_positive(n) returning True when n > 0",
        "oracle": ("from solution import is_even, is_odd, is_positive\n\n"
                   "def test_all():\n"
                   "    assert is_even(4) is True and is_even(3) is False\n"
                   "    assert is_odd(3) is True and is_odd(4) is False\n"
                   "    assert is_positive(5) is True and is_positive(-1) is False\n"),
    },
    {
        "name": "tempconvert",
        "intent": "a temperature module with c_to_f(c) converting Celsius to Fahrenheit, and "
                  "f_to_c(f) converting Fahrenheit to Celsius",
        "oracle": ("from solution import c_to_f, f_to_c\n\n"
                   "def test_all():\n"
                   "    assert c_to_f(0) == 32\n"
                   "    assert c_to_f(100) == 212\n"
                   "    assert f_to_c(32) == 0\n"),
    },
    {
        "name": "textstats",
        "intent": "a text module with word_count(s) returning the number of words, char_count(s) "
                  "returning the number of characters, and shout(s) returning s uppercased",
        "oracle": ("from solution import word_count, char_count, shout\n\n"
                   "def test_all():\n"
                   "    assert word_count('a b c') == 3\n"
                   "    assert char_count('abc') == 3\n"
                   "    assert shout('hi') == 'HI'\n"),
    },
    {
        "name": "minmax",
        "intent": "a module with maximum(xs) returning the largest item in a list and minimum(xs) "
                  "returning the smallest item in a list",
        "oracle": ("from solution import maximum, minimum\n\n"
                   "def test_all():\n"
                   "    assert maximum([1, 5, 2]) == 5\n"
                   "    assert minimum([3, 1, 2]) == 1\n"),
    },
]


def _oracle_pass(solution_code: str, oracle_test: str) -> bool:
    """Score in a FRESH dir (the system never saw the oracle) — un-gameable intent check."""
    if not solution_code.strip():
        return False
    with tempfile.TemporaryDirectory() as od:
        (Path(od) / "solution.py").write_text(solution_code, encoding="utf-8", newline="\n")
        (Path(od) / "test_oracle.py").write_text(oracle_test, encoding="utf-8", newline="\n")
        try:
            return subprocess.run("python -m pytest -q test_oracle.py", cwd=od, shell=True,
                                  capture_output=True, text=True, timeout=60).returncode == 0
        except Exception:
            return False


def run_build_eval(verbose: bool = False, persist: bool = True) -> dict:
    """Run the decompose BUILD flow on each multi-function intent; score against the hidden oracle."""
    from harness.spec_loop import spec_driven_loop
    started = time.time()
    results = []
    for sc in SCENARIOS:
        with tempfile.TemporaryDirectory() as d:
            spec_driven_loop(sc["intent"], d, verbose=verbose)
            sol = Path(d) / "solution.py"
            ok = _oracle_pass(sol.read_text(encoding="utf-8") if sol.is_file() else "", sc["oracle"])
            results.append({"name": sc["name"], "solved": ok})
            print(f"  {'PASS' if ok else 'FAIL'} {sc['name']}", flush=True)
    solved, total = sum(1 for r in results if r["solved"]), len(results)
    print(f"\n=== build eval (oracle-scored): {solved}/{total} = {solved / total * 100:.0f}% ===")
    scorecard = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "suite": "build", "model": MODEL,
        "passRate": round(solved / total, 4) if total else 0.0,
        "solved": solved, "total": total, "elapsedSec": round(time.time() - started, 1),
        "census": census(), "perTask": results,
    }
    if persist:
        _persist(scorecard)
    return scorecard
# #EXT-009-REQ-6 End


if __name__ == "__main__":
    run_build_eval(verbose=True)
