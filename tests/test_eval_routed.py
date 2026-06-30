"""Offline tests for EXT-033 harness/eval_routed.py.

All tests run WITHOUT the Jetson (no LLM calls, no live benchmark datasets).
Mock route_fn / solve_fn replace all live I/O.  Stub ModelRegistry replaces the
real on-disk registry.  The HONEST GATE (_score_task) IS exercised in a real temp
dir — verifying it scores from actual test_cmd runs, not faked results.

Coverage
--------
(a) eval_routed routes each task via route_fn and records routed_model per task;
    per_task list carries task_id, routed_model, problem_class, passed for every task.
(b) On a stub where standalone-fn-gen routes to "model-qwen" and that model's mock
    solve passes more tasks than gemma's mock, routed_rate > single-gemma_rate —
    demonstrating the system-level lift claim.
(c) compare_routed_vs_single computes the delta + flags "no (CI overlap)" on
    Wilson95 CI overlap (n=3 always produces overlapping CIs — honest small-n
    behaviour matches EXT-031 / eval_strategy_easy convention).
(d) The honest gate scores pass@1 correctly from mock solves: actual test_cmd
    is executed in a real temp dir; correct code passes, wrong code fails.
(e) Syntax smoke: eval_routed.py parses without SyntaxError.
(f) Import smoke: public symbols importable without Jetson or LLM at import time.
(g) eval_routed result dict has all required keys (n, bar, routed_passed,
    routed_rate, wilson95, per_task).
(h) compare_routed_vs_single result dict has required keys including
    per_task_routing showing routed_model per task.
(i) eval_single result dict has required keys (n, bar, model, passed, pass_rate,
    wilson95, per_task).
(j) compare_routed_vs_single significant_lift=True when delta is large enough for
    CI separation — using a large n mock to force the CIs apart.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Stub Task (minimal shape — matches what eval_routed/_score_task reads)
# ---------------------------------------------------------------------------

_STUB_SRC = "def add(a, b):\n    pass\n"
_CORRECT_CODE = "def add(a, b):\n    return a + b\n"
_WRONG_CODE = "def add(a, b):\n    return -999\n"
_TEST_OK = (
    "from solution import add\n\n"
    "def test_add():\n"
    "    assert add(1, 2) == 3\n"
    "    assert add(0, 0) == 0\n"
)
_TEST_ALWAYS_FAIL = (
    "from solution import add\n\n"
    "def test_add():\n"
    "    assert add(1, 2) == 9999\n"  # impossible
)
_TEST_CMD = f"{sys.executable} -m pytest test_solution.py -q --tb=no"


class _StubTask:
    """Minimal Task-shaped object that eval_routed/_score_task actually read."""

    def __init__(self, task_id: str, passes: bool = True):
        self.id = task_id
        self.instruction = "implement add(a, b) to return a + b"
        self.target = "solution.py"
        self.test_cmd = _TEST_CMD
        self.tier = 4
        self.files = {
            "solution.py": _STUB_SRC,
            "test_solution.py": _TEST_OK if passes else _TEST_ALWAYS_FAIL,
        }


def _make_tasks(n: int, which_pass: set | None = None) -> list[_StubTask]:
    """Build n StubTasks; tasks with 0-based index in which_pass have passing tests."""
    if which_pass is None:
        which_pass = set(range(n))
    return [_StubTask(f"task_{i}", passes=(i in which_pass)) for i in range(n)]


# ---------------------------------------------------------------------------
# Stub ModelRegistry (in-memory; no disk access)
# ---------------------------------------------------------------------------

def _stub_registry(default_id: str = "model-gemma"):
    """Return a ModelRegistry with two models: model-gemma and model-qwen.

    model-qwen scores higher on standalone-fn-gen (92%) than model-gemma (82%),
    matching the real measured profiles for qwen2.5-coder-3b vs gemma-4-e2b.
    """
    from harness.model_registry import ModelRegistry, ModelProfile  # noqa: PLC0415

    gemma = ModelProfile(
        id="model-gemma",
        alias="gemma",
        classes=[{
            "name": "standalone-fn-gen",
            "score": "82%",
            "bar": "HumanEval",
            "date": "2026-06-01",
        }],
        adaptation={"prompts": "gherkin-decompose"},
    )
    qwen = ModelProfile(
        id="model-qwen",
        alias="qwen",
        classes=[{
            "name": "standalone-fn-gen",
            "score": "92%",
            "bar": "HumanEval",
            "date": "2026-06-01",
        }],
        adaptation={"prompts": "qwen-instruct-direct"},
    )
    return ModelRegistry(
        profiles=[gemma, qwen],
        default_id=default_id,
        roster_order=["model-qwen", "model-gemma"],
    )


# ---------------------------------------------------------------------------
# Stub route_fn helpers
# ---------------------------------------------------------------------------

def _always_qwen_route(problem_dict, registry):
    """Route every task to model-qwen / standalone-fn-gen."""
    return {
        "model_id": "model-qwen",
        "problem_class": "standalone-fn-gen",
        "confidence": 0.92,
        "rationale": "stub",
    }


def _always_gemma_route(problem_dict, registry):
    """Route every task to model-gemma / standalone-fn-gen."""
    return {
        "model_id": "model-gemma",
        "problem_class": "standalone-fn-gen",
        "confidence": 0.82,
        "rationale": "stub",
    }


# ---------------------------------------------------------------------------
# (e) Syntax smoke
# ---------------------------------------------------------------------------

def test_eval_routed_parses():
    """eval_routed.py must parse without SyntaxError."""
    src = (_REPO_ROOT / "harness" / "eval_routed.py").read_text(encoding="utf-8")
    ast.parse(src)


# ---------------------------------------------------------------------------
# (f) Import smoke
# ---------------------------------------------------------------------------

def test_eval_routed_imports():
    """Public symbols must be importable without Jetson or LLM at import time."""
    from harness.eval_routed import (  # noqa: F401
        eval_routed,
        eval_single,
        compare_routed_vs_single,
        _wilson95,
        _ci_overlap,
        _score_task,
        _load_tasks,
    )


# ---------------------------------------------------------------------------
# (g) eval_routed result dict keys
# ---------------------------------------------------------------------------

def test_eval_routed_result_keys():
    """eval_routed must return a dict with all required keys."""
    from harness.eval_routed import eval_routed

    registry = _stub_registry()
    tasks = _make_tasks(2, which_pass={0, 1})

    result = eval_routed(
        2, "humaneval", registry,
        route_fn=_always_qwen_route,
        solve_fn=lambda t, d: _CORRECT_CODE,
        _tasks=tasks,
    )

    required = ("n", "bar", "routed_passed", "routed_rate", "wilson95", "per_task")
    for key in required:
        assert key in result, f"Required key {key!r} missing from eval_routed result"

    lo, hi = result["wilson95"]
    assert 0.0 <= lo <= hi <= 1.0
    assert result["n"] == 2
    assert result["bar"] == "humaneval"
    assert len(result["per_task"]) == 2


# ---------------------------------------------------------------------------
# (a) eval_routed routes each task via route_fn and records routed_model per task
# ---------------------------------------------------------------------------

def test_eval_routed_records_routed_model_per_task():
    """eval_routed must call route_fn for each task and record routed_model in per_task."""
    from harness.eval_routed import eval_routed

    registry = _stub_registry()
    tasks = _make_tasks(4, which_pass={0, 1, 2, 3})

    result = eval_routed(
        4, "humaneval", registry,
        route_fn=_always_qwen_route,
        solve_fn=lambda t, d: _CORRECT_CODE,
        _tasks=tasks,
    )

    assert len(result["per_task"]) == 4
    for i, pt in enumerate(result["per_task"]):
        assert pt["task_id"] == f"task_{i}", (
            f"Expected task_id 'task_{i}', got {pt['task_id']!r}"
        )
        assert pt["routed_model"] == "model-qwen", (
            f"task_{i} should route to 'model-qwen'; got {pt['routed_model']!r}"
        )
        assert pt["problem_class"] == "standalone-fn-gen", (
            f"task_{i} problem_class should be 'standalone-fn-gen'; "
            f"got {pt['problem_class']!r}"
        )
        assert "passed" in pt


def test_eval_routed_per_task_has_all_required_keys():
    """Each per_task entry must have: task_id, routed_model, problem_class, passed."""
    from harness.eval_routed import eval_routed

    registry = _stub_registry()
    tasks = _make_tasks(3, which_pass={0, 1, 2})

    result = eval_routed(
        3, "humaneval", registry,
        route_fn=_always_qwen_route,
        solve_fn=lambda t, d: _CORRECT_CODE,
        _tasks=tasks,
    )

    required_per_task_keys = {"task_id", "routed_model", "problem_class", "passed"}
    for pt in result["per_task"]:
        missing = required_per_task_keys - set(pt.keys())
        assert not missing, f"per_task entry missing keys: {missing}"


# ---------------------------------------------------------------------------
# (d) Honest gate scores pass@1 correctly from mock solves
# ---------------------------------------------------------------------------

def test_eval_routed_honest_gate_mixed():
    """eval_routed must use the real test_cmd gate; correct code passes, wrong fails.

    Tasks 0 and 2 have tests that pass when correct code is supplied.
    Task 1 has a test that always fails (impossible assertion).
    Mock solve returns correct code for tasks 0 and 2, wrong code for task 1.
    Expected: routed_passed=2, routed_rate=2/3.
    """
    from harness.eval_routed import eval_routed

    registry = _stub_registry()
    tasks = _make_tasks(3, which_pass={0, 2})  # tasks 0,2 can pass; task 1 always fails

    def mock_solve(task, decision):
        idx = int(task.id.split("_")[1])
        return _CORRECT_CODE if idx in {0, 2} else _WRONG_CODE

    result = eval_routed(
        3, "humaneval", registry,
        route_fn=_always_qwen_route,
        solve_fn=mock_solve,
        _tasks=tasks,
    )

    assert result["routed_passed"] == 2, (
        f"Expected 2 tasks passed, got {result['routed_passed']}"
    )
    assert abs(result["routed_rate"] - 2 / 3) < 0.001, (
        f"Expected routed_rate ~0.667, got {result['routed_rate']}"
    )
    pt_passed = [pt["passed"] for pt in result["per_task"]]
    assert pt_passed == [True, False, True], (
        f"Expected [True, False, True]; got {pt_passed}"
    )


def test_eval_routed_all_pass():
    """All tasks pass -> routed_passed == n, routed_rate == 1.0."""
    from harness.eval_routed import eval_routed

    registry = _stub_registry()
    tasks = _make_tasks(4, which_pass={0, 1, 2, 3})

    result = eval_routed(
        4, "humaneval", registry,
        route_fn=_always_qwen_route,
        solve_fn=lambda t, d: _CORRECT_CODE,
        _tasks=tasks,
    )

    assert result["routed_passed"] == 4
    assert result["routed_rate"] == 1.0


def test_eval_routed_all_fail():
    """All tasks fail -> routed_passed == 0, routed_rate == 0.0."""
    from harness.eval_routed import eval_routed

    registry = _stub_registry()
    tasks = _make_tasks(3, which_pass={0, 1, 2})  # tests CAN pass ...

    result = eval_routed(
        3, "humaneval", registry,
        route_fn=_always_qwen_route,
        solve_fn=lambda t, d: _WRONG_CODE,  # ... but wrong code supplied
        _tasks=tasks,
    )

    assert result["routed_passed"] == 0
    assert result["routed_rate"] == 0.0


# ---------------------------------------------------------------------------
# (i) eval_single result dict keys
# ---------------------------------------------------------------------------

def test_eval_single_result_keys():
    """eval_single must return a dict with all required keys."""
    from harness.eval_routed import eval_single

    tasks = _make_tasks(2, which_pass={0, 1})

    result = eval_single(
        2, "humaneval", "model-gemma",
        solve_fn=lambda t: _CORRECT_CODE,
        _tasks=tasks,
    )

    required = ("n", "bar", "model", "passed", "pass_rate", "wilson95", "per_task")
    for key in required:
        assert key in result, f"Required key {key!r} missing from eval_single result"

    assert result["model"] == "model-gemma"
    assert result["n"] == 2
    assert result["passed"] == 2
    assert result["pass_rate"] == 1.0


def test_eval_single_honest_gate():
    """eval_single must score pass@1 via the honest gate."""
    from harness.eval_routed import eval_single

    tasks = _make_tasks(3, which_pass={0, 2})  # task 1 always fails

    def mock_solve(task):
        idx = int(task.id.split("_")[1])
        return _CORRECT_CODE if idx in {0, 2} else _WRONG_CODE

    result = eval_single(
        3, "humaneval", "model-gemma",
        solve_fn=mock_solve,
        _tasks=tasks,
    )

    assert result["passed"] == 2
    assert abs(result["pass_rate"] - 2 / 3) < 0.001


# ---------------------------------------------------------------------------
# (b) routed_rate > single-gemma_rate on stub
# ---------------------------------------------------------------------------

def test_routed_beats_single_on_stub():
    """When qwen's mock solve passes more tasks than gemma's mock, routed > single.

    5 tasks: 4 have passing tests (can succeed), 1 always fails.
    routed solve: correct code for all  -> 4/5 = 0.80 pass
    single solve: correct code for 1 only -> 1/5 = 0.20 pass
    routed_rate (0.80) MUST exceed single_rate (0.20).
    """
    from harness.eval_routed import eval_routed, eval_single

    registry = _stub_registry()
    tasks = _make_tasks(5, which_pass={0, 1, 2, 3})  # task 4 always fails

    # Routed: correct code for all (4/5 pass since task 4 always fails)
    def routed_solve(task, decision):
        return _CORRECT_CODE

    routed_result = eval_routed(
        5, "humaneval", registry,
        route_fn=_always_qwen_route,
        solve_fn=routed_solve,
        _tasks=tasks,
    )

    # Single-gemma: correct code for task 0 only (1/5 pass)
    def single_solve(task):
        return _CORRECT_CODE if task.id == "task_0" else _WRONG_CODE

    single_result = eval_single(
        5, "humaneval", "model-gemma",
        solve_fn=single_solve,
        _tasks=tasks,
    )

    assert routed_result["routed_rate"] > single_result["pass_rate"], (
        f"routed_rate ({routed_result['routed_rate']}) must exceed "
        f"single_rate ({single_result['pass_rate']})"
    )
    assert routed_result["routed_passed"] == 4
    assert single_result["passed"] == 1


# ---------------------------------------------------------------------------
# (h) compare_routed_vs_single result dict keys + per_task_routing
# ---------------------------------------------------------------------------

def test_compare_routed_vs_single_result_keys():
    """compare_routed_vs_single must return all required keys."""
    from harness.eval_routed import compare_routed_vs_single

    registry = _stub_registry()
    tasks = _make_tasks(2, which_pass={0, 1})

    result = compare_routed_vs_single(
        2, "humaneval",
        registry=registry,
        route_fn=_always_qwen_route,
        routed_solve_fn=lambda t, d: _CORRECT_CODE,
        single_solve_fn=lambda t: _CORRECT_CODE,
        _tasks=tasks,
    )

    required = (
        "bar", "n", "routed", "single", "delta",
        "significant_lift", "lift_tag", "per_task_routing",
    )
    for key in required:
        assert key in result, f"Required key {key!r} missing from compare result"

    assert result["bar"] == "humaneval"
    assert result["n"] == 2
    assert len(result["per_task_routing"]) == 2


def test_compare_per_task_routing_shows_routed_model():
    """per_task_routing must show routed_model and problem_class for each task."""
    from harness.eval_routed import compare_routed_vs_single

    registry = _stub_registry()
    tasks = _make_tasks(3, which_pass={0, 1, 2})

    result = compare_routed_vs_single(
        3, "humaneval",
        registry=registry,
        route_fn=_always_qwen_route,
        routed_solve_fn=lambda t, d: _CORRECT_CODE,
        single_solve_fn=lambda t: _CORRECT_CODE,
        _tasks=tasks,
    )

    for pt in result["per_task_routing"]:
        assert "task_id" in pt
        assert "routed_model" in pt
        assert "problem_class" in pt
        assert pt["routed_model"] == "model-qwen", (
            f"Expected 'model-qwen', got {pt['routed_model']!r}"
        )


# ---------------------------------------------------------------------------
# (c) compare_routed_vs_single flags "no (CI overlap)" on small n
# ---------------------------------------------------------------------------

def test_compare_no_significant_lift_ci_overlap_small_n():
    """compare_routed_vs_single must flag 'no (CI overlap)' when CIs overlap.

    With n=3, even 2/3 vs 1/3 produces heavily overlapping Wilson95 CIs.
    This IS the honest small-n behaviour — not a bug.
    """
    from harness.eval_routed import compare_routed_vs_single

    registry = _stub_registry()
    tasks = _make_tasks(3, which_pass={0, 1})  # tasks 0,1 can pass; task 2 always fails

    def routed_solve(task, decision):
        idx = int(task.id.split("_")[1])
        return _CORRECT_CODE if idx in {0, 1} else _WRONG_CODE  # 2/3 routed pass

    def single_solve(task):
        idx = int(task.id.split("_")[1])
        return _CORRECT_CODE if idx == 0 else _WRONG_CODE  # 1/3 single pass

    result = compare_routed_vs_single(
        3, "humaneval",
        registry=registry,
        route_fn=_always_qwen_route,
        routed_solve_fn=routed_solve,
        single_solve_fn=single_solve,
        _tasks=tasks,
    )

    assert not result["significant_lift"], (
        "With n=3, CI overlap is guaranteed; should NOT be flagged as significant lift"
    )
    assert "CI overlap" in result["lift_tag"], (
        f"Expected 'CI overlap' in lift_tag for small n; got {result['lift_tag']!r}"
    )
    # Delta is positive (routed does better) but CI overlap -> no significant lift
    assert result["delta"] > 0, "routed 2/3 > single 1/3 => positive delta"


def test_compare_delta_reflects_routed_minus_single():
    """compare_routed_vs_single delta must equal routed_rate - single_rate."""
    from harness.eval_routed import compare_routed_vs_single

    registry = _stub_registry()
    tasks = _make_tasks(4, which_pass={0, 1, 2, 3})

    result = compare_routed_vs_single(
        4, "humaneval",
        registry=registry,
        route_fn=_always_qwen_route,
        routed_solve_fn=lambda t, d: _CORRECT_CODE,   # 4/4 = 1.0
        single_solve_fn=lambda t: _WRONG_CODE,         # 0/4 = 0.0
        _tasks=tasks,
    )

    expected_delta = round(result["routed"]["routed_rate"] - result["single"]["pass_rate"], 4)
    assert abs(result["delta"] - expected_delta) < 1e-6, (
        f"delta {result['delta']} != routed_rate - single_rate = {expected_delta}"
    )


# ---------------------------------------------------------------------------
# (j) significant_lift=True when CI separates (large enough n mock)
# ---------------------------------------------------------------------------

def test_compare_significant_lift_when_ci_separates():
    """significant_lift=True only when the delta falls OUTSIDE the CI overlap.

    With many tasks and extreme rates (all-pass routed vs all-fail single),
    the CIs eventually separate -> significant_lift=True and lift_tag starts with 'yes'.
    """
    from harness.eval_routed import compare_routed_vs_single, _wilson95, _ci_overlap

    registry = _stub_registry()
    # Use a large n where the CIs actually separate: 30 tasks, routed all-pass, single all-fail
    # routed 30/30: Wilson95 approx [0.884, 1.000]
    # single  0/30: Wilson95 approx [0.000, 0.116]
    # These DO NOT overlap -> significant_lift
    n = 30
    tasks = _make_tasks(n, which_pass=set(range(n)))

    result = compare_routed_vs_single(
        n, "humaneval",
        registry=registry,
        route_fn=_always_qwen_route,
        routed_solve_fn=lambda t, d: _CORRECT_CODE,   # 30/30
        single_solve_fn=lambda t: _WRONG_CODE,         # 0/30
        _tasks=tasks,
    )

    # Double-check the math manually
    r_lo, r_hi = _wilson95(30, 30)
    s_lo, s_hi = _wilson95(0, 30)
    assert not _ci_overlap(s_lo, s_hi, r_lo, r_hi), (
        f"CIs SHOULD NOT overlap at 30/30 vs 0/30: [{r_lo:.3f},{r_hi:.3f}] vs "
        f"[{s_lo:.3f},{s_hi:.3f}]"
    )

    assert result["significant_lift"] is True, (
        f"Expected significant_lift=True at 30/30 vs 0/30; got {result['significant_lift']}"
    )
    assert result["lift_tag"].startswith("yes"), (
        f"Expected lift_tag starting with 'yes'; got {result['lift_tag']!r}"
    )


# ---------------------------------------------------------------------------
# Wilson95 and CI helpers (pure math — no I/O)
# ---------------------------------------------------------------------------

def test_wilson95_extremes():
    """Wilson95 must return valid intervals for k=0 and k=n."""
    from harness.eval_routed import _wilson95

    lo, hi = _wilson95(0, 10)
    assert lo >= 0.0 and hi <= 1.0 and lo <= hi

    lo, hi = _wilson95(10, 10)
    assert lo >= 0.0 and hi <= 1.0 and lo <= hi


def test_wilson95_zero_n():
    """Wilson95 with n=0 must return (0.0, 1.0)."""
    from harness.eval_routed import _wilson95

    lo, hi = _wilson95(0, 0)
    assert lo == 0.0 and hi == 1.0


def test_ci_overlap_overlapping():
    """CIs that share a region must return True."""
    from harness.eval_routed import _ci_overlap

    assert _ci_overlap(0.1, 0.6, 0.4, 0.9) is True
    assert _ci_overlap(0.0, 1.0, 0.5, 0.8) is True


def test_ci_overlap_non_overlapping():
    """Disjoint CIs must return False."""
    from harness.eval_routed import _ci_overlap

    assert _ci_overlap(0.0, 0.3, 0.5, 0.9) is False
    assert _ci_overlap(0.6, 0.9, 0.1, 0.4) is False
