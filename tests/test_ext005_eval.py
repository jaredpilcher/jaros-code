"""EXT-005 eval-harness plumbing tests (no model calls)."""

from __future__ import annotations

from pathlib import Path

from harness.eval_runner import load_tasks, setup_task


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
