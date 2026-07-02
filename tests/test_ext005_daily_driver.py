"""Tests for the daily-driver parity-suite runner (EXT-005 / REQ-13).

Fully offline: no Jetson / model is called. The only model-calling piece of the
runner (``answer_fn``) is a plain injected stub, and the pytest-oracle path's
``fix_loop`` is monkeypatched so no live model call happens in these tests either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.daily_driver import (
    CATEGORY_WEIGHTS,
    check_answer,
    check_state,
    load_daily_tasks,
    run_daily,
)

DAILY_ROOT = Path(__file__).resolve().parents[1] / "evals" / "daily_driver"

# #EXT-005-REQ-13 Start
# ---------------------------------------------------------------------------
# load_daily_tasks
# ---------------------------------------------------------------------------

def test_load_daily_tasks_loads_seed_dev_tasks():
    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    ids = {t["id"] for t in tasks}
    assert ids == {"nav_callers_of_load_config", "edit_clamp_bounds"}
    # sorted by (category, id): "edit" < "navigate" alphabetically
    assert [t["category"] for t in tasks] == ["edit", "navigate"]


def test_load_daily_tasks_default_root_loads_both_seed_tasks():
    tasks = load_daily_tasks()  # default root=evals/daily_driver, both splits
    ids = {t["id"] for t in tasks}
    assert {"nav_callers_of_load_config", "edit_clamp_bounds"} <= ids


def test_load_daily_tasks_tolerates_missing_holdout_dir(tmp_path):
    root = tmp_path / "daily"
    (root / "dev").mkdir(parents=True)
    (root / "dev" / "a.json").write_text(json.dumps({
        "id": "a", "category": "navigate", "split": "dev",
        "instruction": "x", "files": {},
        "oracle": {"type": "answer", "match": "exact", "expect": "ok"},
    }), encoding="utf-8")
    # no holdout/ dir at all — must not raise
    tasks = load_daily_tasks(root=root)
    assert len(tasks) == 1
    assert tasks[0]["id"] == "a"


def test_load_daily_tasks_can_restrict_to_a_single_split(tmp_path):
    root = tmp_path / "daily"
    (root / "dev").mkdir(parents=True)
    (root / "holdout").mkdir(parents=True)
    (root / "dev" / "a.json").write_text(json.dumps({
        "id": "a", "category": "navigate", "split": "dev", "instruction": "x",
        "files": {}, "oracle": {"type": "answer", "match": "exact", "expect": "ok"},
    }), encoding="utf-8")
    (root / "holdout" / "b.json").write_text(json.dumps({
        "id": "b", "category": "navigate", "split": "holdout", "instruction": "y",
        "files": {}, "oracle": {"type": "answer", "match": "exact", "expect": "ok"},
    }), encoding="utf-8")
    dev_only = load_daily_tasks(root=root, split="dev")
    assert [t["id"] for t in dev_only] == ["a"]


# ---------------------------------------------------------------------------
# check_answer — set-match oracle (the navigate seed task)
# ---------------------------------------------------------------------------

def _nav_oracle() -> dict:
    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    nav = next(t for t in tasks if t["category"] == "navigate")
    return nav["oracle"]


def test_check_answer_set_match_true_on_names_plus_connector_word():
    oracle = _nav_oracle()
    assert check_answer("start and reload", oracle) is True


def test_check_answer_set_match_false_when_a_name_is_missing():
    oracle = _nav_oracle()
    assert check_answer("start", oracle) is False


def test_check_answer_set_match_false_when_an_extra_name_is_present():
    oracle = _nav_oracle()
    assert check_answer("start reload helper", oracle) is False


def test_check_answer_exact_match_normalized():
    oracle = {"type": "answer", "match": "exact", "expect": "ok"}
    assert check_answer("  OK  ", oracle) is True
    assert check_answer("nope", oracle) is False


def test_check_answer_regex_match_requires_every_pattern():
    oracle = {"type": "answer", "match": "regex", "expect": [r"line\s*12", r"util\.py"]}
    assert check_answer("see util.py at line 12", oracle) is True
    assert check_answer("see util.py", oracle) is False


def test_check_answer_unknown_match_type_raises():
    with pytest.raises(ValueError):
        check_answer("x", {"type": "answer", "match": "fuzzy", "expect": "x"})


# ---------------------------------------------------------------------------
# check_state — deterministic state oracle (dispatch, no ops seed yet)
# ---------------------------------------------------------------------------

def test_check_state_file_exists(tmp_path):
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    assert check_state(tmp_path, {"check": "file_exists", "path": "marker.txt"}) is True
    assert check_state(tmp_path, {"check": "file_exists", "path": "missing.txt"}) is False


def test_check_state_file_contains(tmp_path):
    (tmp_path / "out.txt").write_text("hello world", encoding="utf-8")
    assert check_state(tmp_path, {"check": "file_contains", "path": "out.txt",
                                  "expect": "world"}) is True
    assert check_state(tmp_path, {"check": "file_contains", "path": "out.txt",
                                  "expect": "nope"}) is False


def test_check_state_unknown_check_type_raises(tmp_path):
    with pytest.raises(ValueError):
        check_state(tmp_path, {"check": "no_such_check"})


# ---------------------------------------------------------------------------
# routing: the edit seed is a pytest-oracle task
# ---------------------------------------------------------------------------

def test_edit_seed_routes_to_pytest_path():
    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    edit = next(t for t in tasks if t["category"] == "edit")
    assert edit.get("test_cmd")
    assert "oracle" not in edit


def test_navigate_seed_routes_to_answer_oracle():
    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    nav = next(t for t in tasks if t["category"] == "navigate")
    assert not nav.get("test_cmd")
    assert nav["oracle"]["type"] == "answer"


# ---------------------------------------------------------------------------
# run_daily — offline: fix_loop faked (no live model), answer_fn injected
# ---------------------------------------------------------------------------

def test_run_daily_scorecard_has_weighted_and_per_category_and_split_fields(monkeypatch):
    from harness.coding_loop import LoopResult

    def _fake_fix_loop(target, instruction, test_cmd, **kwargs):
        return LoopResult(success=True, attempts=1, final_output="faked")

    monkeypatch.setattr("harness.coding_loop.fix_loop", _fake_fix_loop)

    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")

    def _stub_answer(task: dict) -> str:
        return "start and reload"

    scorecard = run_daily(tasks, answer_fn=_stub_answer, max_iters=2)

    assert scorecard["total"] == 2
    assert scorecard["solved"] == 2
    assert set(scorecard["perCategory"]) == {"edit", "navigate"}
    for cat in ("edit", "navigate"):
        stats = scorecard["perCategory"][cat]
        assert stats == {"passed": 1, "total": 1, "rate": 1.0,
                         "wilson": stats["wilson"]}
        assert 0.0 <= stats["wilson"]["low"] <= stats["rate"] <= stats["wilson"]["high"] <= 1.0
    assert scorecard["weighted"] == pytest.approx(1.0)
    assert scorecard["bySplit"] == {"dev": {"passed": 2, "total": 2, "rate": 1.0}}
    assert CATEGORY_WEIGHTS["navigate"] == 20 and CATEGORY_WEIGHTS["edit"] == 20


def test_run_daily_default_answer_fn_is_an_offline_stub(monkeypatch):
    """No answer_fn given -> the default stub returns "" (no model/CLI call) and the
    navigate task is correctly scored unsolved."""
    from harness.coding_loop import LoopResult

    def _fake_fix_loop(target, instruction, test_cmd, **kwargs):
        return LoopResult(success=False, attempts=1, final_output="faked")

    monkeypatch.setattr("harness.coding_loop.fix_loop", _fake_fix_loop)

    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["perCategory"]["navigate"]["passed"] == 0
    assert scorecard["perCategory"]["edit"]["passed"] == 0
    assert scorecard["weighted"] == pytest.approx(0.0)
# #EXT-005-REQ-13 End
