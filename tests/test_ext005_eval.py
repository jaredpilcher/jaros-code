"""EXT-005 eval-harness plumbing tests (no model calls)."""

from __future__ import annotations

from pathlib import Path

from harness.eval_runner import _tier_stats, load_tasks, setup_task
from harness.humaneval import problem_to_task


def test_tasks_load_with_required_fields():
    tasks = load_tasks()
    assert len(tasks) >= 5
    for t in tasks:
        assert t.id and t.instruction and t.target and t.test_cmd
        assert t.target in t.files  # the file to edit must be provided


def test_setup_materializes_isolated_files(tmp_path: Path):
    [task] = [t for t in load_tasks() if t.id == "add_sum"]
    target = setup_task(task, tmp_path)
    assert target.is_file()
    assert (tmp_path / "test_calc.py").is_file()
    assert target.read_text(encoding="utf-8") == task.files[task.target]


def test_suite_has_multiple_tiers():
    tiers = {t.tier for t in load_tasks()}
    assert max(tiers) >= 3  # the difficulty ratchet has real headroom


def test_tier_stats_frontier_is_lowest_unmastered():
    per = [{"tier": 1, "solved": True}, {"tier": 1, "solved": True},
           {"tier": 2, "solved": False}]
    per_tier, frontier, too_easy = _tier_stats(per)
    assert frontier == 2 and too_easy is False
    assert per_tier["1"]["passRate"] == 1.0


def test_tier_stats_flags_too_easy_when_all_mastered():
    per = [{"tier": 1, "solved": True}, {"tier": 2, "solved": True}]
    _per_tier, frontier, too_easy = _tier_stats(per)
    assert frontier is None and too_easy is True


def test_humaneval_problem_maps_to_pytest_task():
    p = {"task_id": "HumanEval/0", "prompt": 'def f(x):\n    """doc"""\n',
         "entry_point": "f", "test": "def check(c):\n    assert c(1) == 1\n"}
    t = problem_to_task(p)
    assert t.target == "solution.py" and t.tier == 4
    assert "    pass\n" in t.files["solution.py"]
    assert "def test_humaneval" in t.files["test_solution.py"]
    assert "from solution import f" in t.files["test_solution.py"]
