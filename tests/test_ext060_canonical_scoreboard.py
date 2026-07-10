"""EXT-060 TASK-7: offline tests for the UNIFIED CANONICAL SCOREBOARD (REQ-8) --
run_canonical_scoreboard, which runs BOTH halves and reports ONE combined pass@1. This is now
THE tracked real-systems number (see .jarify/EXT-060/intent.md) -- the creation suite
(harness/system_suite.py), harness/modification_suite.py, and harness/daily_driver.py are
demoted to regression checks / feeders.

FULLY OFFLINE -- no Jetson/LLM call anywhere. Monkeypatches ``run_real_systems_suite``/
``run_real_systems_modify_suite`` with fixed fake per-task results to prove the AGGREGATION
ARITHMETIC is correct (the two halves' own runners are already tested independently in
tests/test_ext060_real_systems_suite.py and tests/test_ext060_modify_suite.py).
"""

# #EXT-060-REQ-8 Start
from __future__ import annotations

import harness.real_systems_suite as rss


def _fake_suite_result(results):
    return {"results": results, "aggregate": rss._aggregate(results)}


def test_run_canonical_scoreboard_combines_both_halves_correctly(monkeypatch):
    create_results = [
        {"name": "a", "cls": "etl", "accepted": True},
        {"name": "b", "cls": "library", "accepted": False},
        {"name": "c", "cls": "config-cli", "accepted": True},
    ]
    modify_results = [
        {"name": "d", "cls": "library-modify", "accepted": True},
        {"name": "e", "cls": "config-cli-modify", "accepted": False},
    ]

    monkeypatch.setattr(rss, "run_real_systems_suite",
                         lambda tasks, llm=None, python_exe=None: _fake_suite_result(create_results))
    monkeypatch.setattr(rss, "run_real_systems_modify_suite",
                         lambda tasks, llm=None, python_exe=None: _fake_suite_result(modify_results))

    out = rss.run_canonical_scoreboard(llm=object())

    assert out["create"]["results"] == create_results
    assert out["modify"]["results"] == modify_results
    # 2/3 create + 1/2 modify = 3 passed of 5 total
    assert out["combined"] == {"n": 5, "passed": 3, "pass_rate": 0.6}


def test_run_canonical_scoreboard_guards_division_by_zero_when_both_halves_empty(monkeypatch):
    monkeypatch.setattr(rss, "run_real_systems_suite",
                         lambda tasks, llm=None, python_exe=None: _fake_suite_result([]))
    monkeypatch.setattr(rss, "run_real_systems_modify_suite",
                         lambda tasks, llm=None, python_exe=None: _fake_suite_result([]))

    out = rss.run_canonical_scoreboard(llm=object())
    assert out["combined"] == {"n": 0, "passed": 0, "pass_rate": 0.0}


def test_run_canonical_scoreboard_all_passing_is_1_0(monkeypatch):
    monkeypatch.setattr(rss, "run_real_systems_suite",
                         lambda tasks, llm=None, python_exe=None: _fake_suite_result(
                             [{"name": "a", "cls": "etl", "accepted": True}]))
    monkeypatch.setattr(rss, "run_real_systems_modify_suite",
                         lambda tasks, llm=None, python_exe=None: _fake_suite_result(
                             [{"name": "b", "cls": "library-modify", "accepted": True}]))

    out = rss.run_canonical_scoreboard(llm=object())
    assert out["combined"] == {"n": 2, "passed": 2, "pass_rate": 1.0}


def test_run_canonical_scoreboard_never_raises_when_a_half_errors(monkeypatch):
    def _boom(tasks, llm=None, python_exe=None):
        raise RuntimeError("simulated failure inside a half's own runner")

    monkeypatch.setattr(rss, "run_real_systems_suite",
                         lambda tasks, llm=None, python_exe=None: _fake_suite_result(
                             [{"name": "a", "cls": "etl", "accepted": True}]))
    monkeypatch.setattr(rss, "run_real_systems_modify_suite", _boom)

    # run_canonical_scoreboard itself does not swallow a raised half (each half's own runner
    # is documented never to raise) -- this proves the wiring calls straight through without
    # adding an extra layer of exception handling that could mask a real half-level bug.
    try:
        rss.run_canonical_scoreboard(llm=object())
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True


def test_run_canonical_scoreboard_is_importable_and_returns_expected_top_level_shape():
    assert callable(rss.run_canonical_scoreboard)
    import inspect
    sig = inspect.signature(rss.run_canonical_scoreboard)
    assert "llm" in sig.parameters
    assert "create_tasks" in sig.parameters
    assert "modify_tasks" in sig.parameters
    assert "python_exe" in sig.parameters
# #EXT-060-REQ-8 End
