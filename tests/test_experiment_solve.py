"""Offline tests for EXT-030 harness/experiment_solve.py.

All tests run WITHOUT the Jetson (no LLM calls, no Docker, no git clones).
Mock callables replace all live I/O.

Acceptance criteria covered
----------------------------
(a) The loop runs exactly max_experiments experiments then calls solve_fn.
(b) Understanding accumulates the {experiment, observation} entries in order;
    propose_fn sees the growing scratchpad at each step.
(c) test_fn is the sole arbiter — mock 'claiming' success but test_fn=fail
    -> not solved.
(d) An experiment that raises is captured as an observation (defensive);
    the loop continues and solve_fn is still called.
(e) solve_fn receives the full accumulated understanding (all observations).

Additional coverage
-------------------
(f) Syntax smoke: experiment_solve.py parses without SyntaxError.
(g) Import smoke: top-level public symbols importable without LLM imports.
(h) solved=True when test_fn accepts the solve_fn output.
(i) solved=False when test_fn rejects even after max_experiments.
(j) max_experiments=0: solve_fn called immediately with empty understanding.
(k) experiments list in result has exactly max_experiments entries.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.experiment_solve import experiment_solve


# ---------------------------------------------------------------------------
# (f) Syntax smoke
# ---------------------------------------------------------------------------

def test_experiment_solve_parses():
    """experiment_solve.py must parse without SyntaxError."""
    src = (_REPO_ROOT / "harness" / "experiment_solve.py").read_text(encoding="utf-8")
    ast.parse(src)  # raises SyntaxError if the file is malformed


# ---------------------------------------------------------------------------
# (g) Import smoke
# ---------------------------------------------------------------------------

def test_experiment_solve_imports():
    """Top-level public symbols importable — no heavy LLM imports at module scope."""
    from harness.experiment_solve import (  # noqa: F401
        experiment_solve,
        _make_experiment_runner,
        _make_jetson_fns,
        _parse_experiment_decision,
        run_experiment_probe,
        E1, E2, E3,
    )


# ---------------------------------------------------------------------------
# Mock helper
# ---------------------------------------------------------------------------

def _make_mocks(
    *,
    propose_returns: list | None = None,
    run_returns: list | None = None,
    solve_code: str = "def f(): pass",
    test_passes: bool = True,
) -> dict:
    """Build injectable mock callables for parametrized scenarios.

    propose_returns: list of Decision dicts returned in order (cycles if short).
    run_returns: list of observation strings returned in order; use the sentinel
                 ``"__RAISE__"`` to simulate a run_experiment_fn raising RuntimeError.
    solve_code: the code string returned by solve_fn.
    test_passes: the ``passed`` value returned by test_fn (constant).
    """
    propose_returns = propose_returns or []
    run_returns = run_returns or []

    propose_calls: list = []
    run_calls: list = []
    solve_calls: list = []
    test_calls: list = []

    _propose_idx = [0]
    _run_idx = [0]

    def propose_fn(problem, understanding):
        propose_calls.append((problem, list(understanding)))  # snapshot
        if _propose_idx[0] < len(propose_returns):
            decision = propose_returns[_propose_idx[0]]
        else:
            decision = {"type": "E1", "params": {}}
        _propose_idx[0] += 1
        return decision

    def run_experiment_fn(problem, decision):
        run_calls.append((problem, decision))
        if _run_idx[0] < len(run_returns):
            obs = run_returns[_run_idx[0]]
        else:
            obs = f"observation_{_run_idx[0]}"
        _run_idx[0] += 1
        if obs == "__RAISE__":
            raise RuntimeError("simulated experiment error")
        return obs

    def solve_fn(problem, understanding):
        solve_calls.append((problem, list(understanding)))  # snapshot
        return solve_code

    def test_fn(problem, code):
        test_calls.append((problem, code))
        return {"passed": test_passes}

    return {
        "propose_fn": propose_fn,
        "run_experiment_fn": run_experiment_fn,
        "solve_fn": solve_fn,
        "test_fn": test_fn,
        "propose_calls": propose_calls,
        "run_calls": run_calls,
        "solve_calls": solve_calls,
        "test_calls": test_calls,
    }


# ---------------------------------------------------------------------------
# (a) Loop runs exactly max_experiments experiments then calls solve_fn
# ---------------------------------------------------------------------------

def test_loop_runs_max_experiments_then_solves():
    """propose_fn and run_experiment_fn are each called exactly max_experiments
    times; solve_fn is called exactly once after the last experiment."""
    mocks = _make_mocks(
        run_returns=["obs0", "obs1", "obs2"],
        solve_code="def f(): return 42",
        test_passes=True,
    )
    result = experiment_solve(
        {"name": "f"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=3,
    )

    assert len(mocks["propose_calls"]) == 3, (
        "propose_fn must be called exactly max_experiments=3 times"
    )
    assert len(mocks["run_calls"]) == 3, (
        "run_experiment_fn must be called exactly max_experiments=3 times"
    )
    assert len(mocks["solve_calls"]) == 1, (
        "solve_fn must be called exactly once (after all experiments)"
    )
    assert result["solved"] is True


# ---------------------------------------------------------------------------
# (b) Understanding accumulates in order; propose_fn sees growing scratchpad
# ---------------------------------------------------------------------------

def test_understanding_accumulates_in_order():
    """understanding list grows in experiment order; propose_fn sees the current
    scratchpad at each step; solve_fn sees all entries."""
    decisions = [
        {"type": "E1", "params": {}},
        {"type": "E3", "params": {"fn_name": "helper"}},
    ]
    observations = [
        "traceback: AssertionError at line 5",
        "def helper(): return None",
    ]
    mocks = _make_mocks(
        propose_returns=decisions,
        run_returns=observations,
        solve_code="def f(): return 1",
        test_passes=True,
    )

    result = experiment_solve(
        {"name": "f"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=2,
    )

    # Result understanding list has both entries in order
    assert len(result["understanding"]) == 2
    assert result["understanding"][0]["experiment"] == decisions[0]
    assert result["understanding"][0]["observation"] == observations[0]
    assert result["understanding"][1]["experiment"] == decisions[1]
    assert result["understanding"][1]["observation"] == observations[1]

    # propose_fn received growing scratchpad:
    # First call: empty understanding
    assert mocks["propose_calls"][0][1] == [], (
        "propose_fn first call must receive empty understanding"
    )
    # Second call: one entry (from first experiment)
    assert len(mocks["propose_calls"][1][1]) == 1, (
        "propose_fn second call must receive understanding with 1 entry"
    )
    assert mocks["propose_calls"][1][1][0]["observation"] == observations[0]

    # solve_fn received the full 2-entry understanding
    understanding_to_solve = mocks["solve_calls"][0][1]
    assert len(understanding_to_solve) == 2
    assert understanding_to_solve[0]["observation"] == observations[0]
    assert understanding_to_solve[1]["observation"] == observations[1]


# ---------------------------------------------------------------------------
# (c) test_fn is the sole arbiter
# ---------------------------------------------------------------------------

def test_test_fn_sole_arbiter():
    """solved must follow test_fn, not anything the model 'says'.

    solve_fn returns code that looks correct; test_fn always returns passed=False.
    The result must be solved=False — test_fn is the only gate.
    """
    mocks = _make_mocks(
        solve_code="def f(): return 42  # model is confident this is correct",
        test_passes=False,  # oracle always fails regardless
    )
    result = experiment_solve(
        {"name": "f"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=2,
    )

    assert result["solved"] is False, (
        "test_fn is the sole arbiter: solved must be False when test_fn returns "
        "passed=False, even if solve_fn produced 'correct-looking' code"
    )
    assert len(mocks["test_calls"]) == 1, (
        "test_fn must be called exactly once (after solve_fn)"
    )
    # solve_fn WAS called (the model tried), but the oracle gate overrides
    assert len(mocks["solve_calls"]) == 1


# ---------------------------------------------------------------------------
# (d) Experiment that errors -> captured as observation; loop continues
# ---------------------------------------------------------------------------

def test_experiment_error_captured_loop_continues():
    """When run_experiment_fn raises, the error is captured as an observation
    string and the loop continues; solve_fn is still called after all experiments."""
    mocks = _make_mocks(
        run_returns=["__RAISE__", "normal second observation"],
        solve_code="def f(): pass",
        test_passes=False,
    )
    result = experiment_solve(
        {"name": "f"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=2,
    )

    # Both experiment slots filled (loop did not abort on error)
    assert len(result["experiments"]) == 2, (
        "loop must run all max_experiments even when one raises"
    )

    # First observation is the captured error text (not blank, not re-raised)
    obs0 = result["understanding"][0]["observation"]
    assert ("error" in obs0.lower() or "RuntimeError" in obs0), (
        f"Captured error observation should mention the exception. Got: {obs0!r}"
    )

    # Second experiment ran normally
    assert result["understanding"][1]["observation"] == "normal second observation", (
        "second experiment must run normally even after first raised"
    )

    # solve_fn was called (after all experiments, including the errored one)
    assert len(mocks["solve_calls"]) == 1, (
        "solve_fn must be called once even when an experiment errored"
    )


# ---------------------------------------------------------------------------
# (e) solve_fn receives the full accumulated understanding
# ---------------------------------------------------------------------------

def test_solve_fn_receives_full_understanding():
    """solve_fn must receive understanding with one entry per experiment, in order."""
    obs_list = ["trace A", "return value B", "helper source C"]
    mocks = _make_mocks(
        run_returns=obs_list,
        solve_code="def f(): pass",
        test_passes=True,
    )
    experiment_solve(
        {"name": "f", "subject": "test task"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=3,
    )

    assert len(mocks["solve_calls"]) == 1
    understanding = mocks["solve_calls"][0][1]

    assert len(understanding) == 3, (
        f"solve_fn must see all 3 observations; got {len(understanding)}"
    )
    for i, expected_obs in enumerate(obs_list):
        assert understanding[i]["observation"] == expected_obs, (
            f"understanding[{i}].observation should be {expected_obs!r}, "
            f"got {understanding[i]['observation']!r}"
        )


# ---------------------------------------------------------------------------
# (h) solved=True when test_fn accepts
# ---------------------------------------------------------------------------

def test_solved_true_when_test_fn_accepts():
    """solved=True and code is set when test_fn returns passed=True."""
    GOOD = "def f(): return 99"
    mocks = _make_mocks(solve_code=GOOD, test_passes=True)
    result = experiment_solve(
        {"name": "f"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=1,
    )
    assert result["solved"] is True
    assert result["code"] == GOOD


# ---------------------------------------------------------------------------
# (i) solved=False when test_fn rejects
# ---------------------------------------------------------------------------

def test_solved_false_when_test_fn_rejects():
    """solved=False and code is still set when test_fn returns passed=False."""
    CODE = "def f(): pass"
    mocks = _make_mocks(solve_code=CODE, test_passes=False)
    result = experiment_solve(
        {"name": "f"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=2,
    )
    assert result["solved"] is False
    assert result["code"] == CODE


# ---------------------------------------------------------------------------
# (j) max_experiments=0: solve_fn called immediately with empty understanding
# ---------------------------------------------------------------------------

def test_max_experiments_zero_solves_immediately():
    """With max_experiments=0, propose_fn and run_experiment_fn are NOT called;
    solve_fn is called immediately with empty understanding."""
    mocks = _make_mocks(solve_code="def f(): return 0", test_passes=True)
    result = experiment_solve(
        {"name": "f"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=0,
    )

    assert len(mocks["propose_calls"]) == 0, (
        "propose_fn must NOT be called when max_experiments=0"
    )
    assert len(mocks["run_calls"]) == 0, (
        "run_experiment_fn must NOT be called when max_experiments=0"
    )
    assert len(mocks["solve_calls"]) == 1

    understanding_passed = mocks["solve_calls"][0][1]
    assert understanding_passed == [], (
        "understanding must be empty when max_experiments=0"
    )

    assert result["solved"] is True
    assert result["experiments"] == []
    assert result["understanding"] == []


# ---------------------------------------------------------------------------
# (k) experiments list has exactly max_experiments entries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("max_exp", [0, 1, 3, 5])
def test_experiments_list_length_matches_max(max_exp):
    """experiments list in result must have exactly max_experiments entries."""
    mocks = _make_mocks(solve_code="def f(): pass", test_passes=False)
    result = experiment_solve(
        {"name": "f"},
        propose_fn=mocks["propose_fn"],
        run_experiment_fn=mocks["run_experiment_fn"],
        solve_fn=mocks["solve_fn"],
        test_fn=mocks["test_fn"],
        max_experiments=max_exp,
    )
    assert len(result["experiments"]) == max_exp, (
        f"experiments must have {max_exp} entries for max_experiments={max_exp}, "
        f"got {len(result['experiments'])}"
    )
    # understanding mirrors experiments
    assert len(result["understanding"]) == max_exp
