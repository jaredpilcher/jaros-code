"""Offline tests for EXT-031 harness/eval_strategy_easy.py.

All tests run WITHOUT the Jetson (no LLM calls, no Docker, no live benchmark datasets).
Mock solve_fns replace all live I/O.  Minimal Task stubs are constructed in memory.

Coverage
--------
(a) eval_strategy_on_easy scores pass@1 correctly from a mock solve (some pass, some fail)
    using the HONEST gate — the actual test_cmd IS run in a real temp dir, confirming the
    gate is not faked in offline mode.
(b) STRATEGY_REGISTRY resolves names -> callables for bare / decomposition /
    experiment-to-understand without crashing (callables not invoked — avoids Jetson).
(c) compare() computes the delta + flags "no significant lift" when CIs overlap (n=3
    always produces overlapping CIs, so ANY two strategies with different rates still get
    "no (CI overlap)" — demonstrating the honest small-n behaviour).
(d) A strategy whose mock solve returns identical results to bare yields delta 0 / no-lift.
(e) Syntax smoke: eval_strategy_easy.py parses without SyntaxError.
(f) Import smoke: top-level public symbols importable without LLM or Jetson at import time.
(g) Unknown strategy name raises KeyError when solve_fn=None.
(h) eval_strategy_on_easy result dict has required keys (strategy, n, passed, pass_rate,
    wilson95, per_task).
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Minimal in-memory Task stub (no harness import needed for the stub itself)
# ---------------------------------------------------------------------------

_STUB_SRC = "def add(a, b):\n    pass\n"
_CORRECT_CODE = "def add(a, b):\n    return a + b\n"
_WRONG_CODE = "def add(a, b):\n    return -999\n"
_TEST_FILE_CONTENT = (
    "from solution import add\n\n"
    "def test_add():\n"
    "    assert add(1, 2) == 3\n"
    "    assert add(0, 0) == 0\n"
)
_TEST_CMD = f"{sys.executable} -m pytest test_solution.py -q --tb=no"


class _StubTask:
    """Minimal Task-shaped object for offline tests.

    Holds only the attributes that eval_strategy_on_easy / _score_task actually
    read: ``id``, ``instruction``, ``target``, ``test_cmd``, ``files``, ``tier``.
    """

    def __init__(self, task_id: str, passes: bool = True):
        self.id = task_id
        self.instruction = "implement add(a, b) to return a + b"
        self.target = "solution.py"
        self.test_cmd = _TEST_CMD
        self.tier = 4
        # Only the test_solution.py needs to be a valid file; the stub solution.py
        # is overwritten by eval_strategy_on_easy before the test runs.
        self.files = {
            "solution.py": _STUB_SRC,
            "test_solution.py": _TEST_FILE_CONTENT,
        }
        # When passes=False the stub has no test file that could pass.
        if not passes:
            # Inject a test that always fails
            self.files["test_solution.py"] = (
                "from solution import add\n\n"
                "def test_add():\n"
                "    assert add(1, 2) == 9999\n"  # impossible assertion
            )


def _make_tasks(n: int, which_pass: set | None = None) -> list[_StubTask]:
    """Build n StubTasks.  Tasks whose 0-based index is in *which_pass* use a
    test that passes when the correct code is supplied; others use a test that always
    fails regardless of code."""
    if which_pass is None:
        which_pass = set(range(n))
    return [_StubTask(f"stub_{i}", passes=(i in which_pass)) for i in range(n)]


# ---------------------------------------------------------------------------
# (e) Syntax smoke
# ---------------------------------------------------------------------------

def test_eval_strategy_easy_parses():
    """eval_strategy_easy.py must parse without SyntaxError."""
    src = (_REPO_ROOT / "harness" / "eval_strategy_easy.py").read_text(encoding="utf-8")
    ast.parse(src)


# ---------------------------------------------------------------------------
# (f) Import smoke
# ---------------------------------------------------------------------------

def test_eval_strategy_easy_imports():
    """Top-level public symbols are importable — no Jetson or LLM at import time."""
    from harness.eval_strategy_easy import (  # noqa: F401
        eval_strategy_on_easy,
        compare,
        STRATEGY_REGISTRY,
        _wilson95,
        _ci_overlap,
        _score_task,
    )


# ---------------------------------------------------------------------------
# (a) Honest-gate scoring — some tasks pass, some fail
# ---------------------------------------------------------------------------

def test_eval_strategy_on_easy_honest_gate_mixed():
    """eval_strategy_on_easy must score using the actual test_cmd (honest gate).

    We create 3 tasks: 0 and 2 have a test that passes when the correct add() is
    supplied; 1 has a test that always fails.  The mock solve_fn returns correct code
    for tasks 0 and 2, wrong code for task 1.  Expected: passed=2, pass_rate=2/3.
    """
    from harness.eval_strategy_easy import eval_strategy_on_easy

    tasks = _make_tasks(3, which_pass={0, 2})

    # Mock solve: correct code for passing tasks, wrong for failing task
    def mock_solve(task):
        idx = int(task.id.split("_")[1])
        return _CORRECT_CODE if idx in {0, 2} else _WRONG_CODE

    result = eval_strategy_on_easy(
        "bare", n=3, bar="humaneval",
        solve_fn=mock_solve, _tasks=tasks,
    )

    assert result["strategy"] == "bare"
    assert result["n"] == 3
    assert result["passed"] == 2, (
        f"Expected 2 tasks passed, got {result['passed']}"
    )
    assert abs(result["pass_rate"] - 2 / 3) < 0.001, (
        f"Expected pass_rate ~0.667, got {result['pass_rate']}"
    )
    assert len(result["per_task"]) == 3
    assert result["per_task"][0]["passed"] is True
    assert result["per_task"][1]["passed"] is False
    assert result["per_task"][2]["passed"] is True


def test_eval_strategy_on_easy_all_pass():
    """All tasks pass -> passed == n, pass_rate == 1.0."""
    from harness.eval_strategy_easy import eval_strategy_on_easy

    tasks = _make_tasks(4, which_pass={0, 1, 2, 3})

    result = eval_strategy_on_easy(
        "bare", n=4, bar="humaneval",
        solve_fn=lambda t: _CORRECT_CODE, _tasks=tasks,
    )

    assert result["passed"] == 4
    assert result["pass_rate"] == 1.0


def test_eval_strategy_on_easy_all_fail():
    """All tasks fail -> passed == 0, pass_rate == 0.0."""
    from harness.eval_strategy_easy import eval_strategy_on_easy

    tasks = _make_tasks(3, which_pass={0, 1, 2})  # tests CAN pass ...
    # ... but we supply wrong code so they fail

    result = eval_strategy_on_easy(
        "bare", n=3, bar="humaneval",
        solve_fn=lambda t: _WRONG_CODE, _tasks=tasks,
    )

    assert result["passed"] == 0
    assert result["pass_rate"] == 0.0


def test_eval_strategy_on_easy_result_keys():
    """Result dict must have all required keys."""
    from harness.eval_strategy_easy import eval_strategy_on_easy

    tasks = _make_tasks(2, which_pass={0, 1})
    result = eval_strategy_on_easy(
        "bare", n=2, bar="humaneval",
        solve_fn=lambda t: _CORRECT_CODE, _tasks=tasks,
    )

    for key in ("strategy", "n", "passed", "pass_rate", "wilson95", "per_task"):
        assert key in result, f"Required key {key!r} missing from result"

    lo, hi = result["wilson95"]
    assert 0.0 <= lo <= hi <= 1.0, "Wilson95 must be a valid [lo, hi] in [0, 1]"


# ---------------------------------------------------------------------------
# (b) Strategy registry resolves names -> callables
# ---------------------------------------------------------------------------

def test_strategy_registry_resolves():
    """STRATEGY_REGISTRY must have bare / decomposition / experiment-to-understand
    as callable entries (callables NOT invoked — avoids Jetson)."""
    from harness.eval_strategy_easy import STRATEGY_REGISTRY

    required = {"bare", "decomposition", "experiment-to-understand"}
    for name in required:
        assert name in STRATEGY_REGISTRY, (
            f"STRATEGY_REGISTRY must have {name!r}"
        )
        assert callable(STRATEGY_REGISTRY[name]), (
            f"STRATEGY_REGISTRY[{name!r}] must be callable"
        )


def test_strategy_registry_no_import_error():
    """Importing STRATEGY_REGISTRY must not raise (lazy imports guard Jetson calls)."""
    # If this import fails the test fails — that's the check.
    from harness.eval_strategy_easy import STRATEGY_REGISTRY  # noqa: F401
    assert len(STRATEGY_REGISTRY) >= 3


# ---------------------------------------------------------------------------
# (c) compare() CI overlap -> "no significant lift"
# ---------------------------------------------------------------------------

def test_compare_no_significant_lift_ci_overlap():
    """compare() must flag 'no (CI overlap)' when CIs overlap.

    With n=3, even 1/3 vs 2/3 produces heavily overlapping Wilson95 CIs — that IS
    the honest small-n behaviour.  Both strategies should be reported as no-lift.
    """
    from harness.eval_strategy_easy import compare

    # 3 tasks: task 0 can pass (test checks correct code), 1 and 2 always fail
    tasks = _make_tasks(3, which_pass={0})

    # bare: correct code for task 0 only -> 1/3
    def bare_fn(t):
        return _CORRECT_CODE if t.id == "stub_0" else _WRONG_CODE

    # decomposition: correct code for tasks 0 and 1... but task 1 always fails -> 1/3
    # (both strategies end up at 1/3 — but even 2/3 overlaps with 1/3 at n=3)
    # Use 2/3 for decomposition to check overlap explicitly:
    tasks_2pass = _make_tasks(3, which_pass={0, 1})

    def decomp_fn(t):
        idx = int(t.id.split("_")[1])
        return _CORRECT_CODE if idx in {0, 1} else _WRONG_CODE

    def exp_fn(t):
        # experiment-to-understand: same 2/3 pattern
        idx = int(t.id.split("_")[1])
        return _CORRECT_CODE if idx in {0, 1} else _WRONG_CODE

    result = compare(
        n=3, bar="humaneval",
        _tasks=tasks_2pass,  # tasks 0 and 1 can pass
        _solve_fns={
            "bare": bare_fn,
            "decomposition": decomp_fn,
            "experiment-to-understand": exp_fn,
        },
    )

    assert "summary" in result
    assert len(result["summary"]) >= 2, "summary must have at least 2 non-bare strategies"

    for entry in result["summary"]:
        # With n=3, CIs always overlap between 1/3 and 2/3 -> no significant lift
        assert not entry["significant_lift"], (
            f"With n=3, CI overlap is guaranteed; {entry['strategy']} must NOT be flagged "
            f"as significant lift (delta={entry['delta']}, CI might still overlap)"
        )
        assert "CI overlap" in entry["lift_tag"] or entry["lift_tag"] == "no (CI overlap)", (
            f"Expected 'no (CI overlap)' tag for {entry['strategy']}, "
            f"got {entry['lift_tag']!r}"
        )


def test_compare_result_structure():
    """compare() must return the required top-level keys."""
    from harness.eval_strategy_easy import compare

    tasks = _make_tasks(2, which_pass={0, 1})
    result = compare(
        n=2, bar="humaneval",
        _tasks=tasks,
        _solve_fns={
            "bare": lambda t: _CORRECT_CODE,
            "decomposition": lambda t: _CORRECT_CODE,
            "experiment-to-understand": lambda t: _CORRECT_CODE,
        },
    )

    for key in ("bar", "n", "bare_rate", "results", "summary"):
        assert key in result, f"Required key {key!r} missing from compare() result"

    assert result["bar"] == "humaneval"
    assert result["n"] == 2


# ---------------------------------------------------------------------------
# (d) Identical strategy vs bare -> delta 0 / no-lift
# ---------------------------------------------------------------------------

def test_compare_identical_strategy_delta_zero():
    """A strategy whose solve returns the SAME results as bare must produce delta=0
    and significant_lift=False."""
    from harness.eval_strategy_easy import compare

    tasks = _make_tasks(3, which_pass={0, 1, 2})

    # Both bare and all strategies always return correct code -> same rate -> delta=0
    all_correct = lambda t: _CORRECT_CODE  # noqa: E731

    result = compare(
        n=3, bar="humaneval",
        _tasks=tasks,
        _solve_fns={
            "bare": all_correct,
            "decomposition": all_correct,
            "experiment-to-understand": all_correct,
        },
    )

    for entry in result["summary"]:
        assert entry["delta"] == 0.0, (
            f"Identical solve to bare must yield delta=0; got {entry['delta']} "
            f"for {entry['strategy']!r}"
        )
        assert not entry["significant_lift"], (
            f"Identical solve must not be flagged as significant lift "
            f"for {entry['strategy']!r}"
        )


def test_compare_worse_strategy_delta_negative():
    """A strategy that performs strictly worse than bare must produce negative delta."""
    from harness.eval_strategy_easy import compare

    # tasks 0 and 1 can pass
    tasks = _make_tasks(2, which_pass={0, 1})

    result = compare(
        n=2, bar="humaneval",
        _tasks=tasks,
        _solve_fns={
            "bare": lambda t: _CORRECT_CODE,  # 2/2 = 1.0
            "decomposition": lambda t: _WRONG_CODE,  # 0/2 = 0.0
            "experiment-to-understand": lambda t: _WRONG_CODE,  # 0/2 = 0.0
        },
    )

    for entry in result["summary"]:
        assert entry["delta"] < 0, (
            f"Worse strategy must have negative delta; got {entry['delta']} "
            f"for {entry['strategy']!r}"
        )
        # significant_lift must be False (lift is negative or zero)
        assert not entry["significant_lift"], (
            f"Worse strategy must not be flagged as significant lift"
        )


# ---------------------------------------------------------------------------
# (g) Unknown strategy name raises KeyError
# ---------------------------------------------------------------------------

def test_unknown_strategy_raises():
    """eval_strategy_on_easy with an unknown strategy name and solve_fn=None must
    raise KeyError, not silently pass."""
    from harness.eval_strategy_easy import eval_strategy_on_easy

    tasks = _make_tasks(1, which_pass={0})
    with pytest.raises(KeyError):
        eval_strategy_on_easy(
            "nonexistent-strategy", n=1, bar="humaneval",
            solve_fn=None, _tasks=tasks,
        )


# ---------------------------------------------------------------------------
# Wilson95 helper tests (pure math — no I/O)
# ---------------------------------------------------------------------------

def test_wilson95_extremes():
    """Wilson95 must return valid intervals for k=0 and k=n."""
    from harness.eval_strategy_easy import _wilson95

    lo, hi = _wilson95(0, 10)
    assert lo >= 0.0 and hi <= 1.0 and lo <= hi

    lo, hi = _wilson95(10, 10)
    assert lo >= 0.0 and hi <= 1.0 and lo <= hi


def test_wilson95_zero_n():
    """Wilson95 with n=0 must return (0.0, 1.0) (full uncertainty)."""
    from harness.eval_strategy_easy import _wilson95

    lo, hi = _wilson95(0, 0)
    assert lo == 0.0 and hi == 1.0


def test_ci_overlap_overlapping():
    """CI intervals that share a region must return True."""
    from harness.eval_strategy_easy import _ci_overlap

    assert _ci_overlap(0.1, 0.6, 0.4, 0.9) is True  # overlap [0.4, 0.6]
    assert _ci_overlap(0.0, 1.0, 0.5, 0.8) is True   # fully contained


def test_ci_overlap_non_overlapping():
    """Disjoint CI intervals must return False."""
    from harness.eval_strategy_easy import _ci_overlap

    assert _ci_overlap(0.0, 0.3, 0.5, 0.9) is False  # gap [0.3, 0.5]
    assert _ci_overlap(0.6, 0.9, 0.1, 0.4) is False  # reversed order
