"""EXT-038 REQ-3 / TASK-3: `run_task_list()` auto-locks research for its full duration.

Offline, no live model call: `harness.coding_loop.fix_loop` is monkeypatched to a stub that records
`research_guard.research_allowed()` from WITHIN a "running task", proving the lock is genuinely
active during execution and releases once `run_task_list()` returns (or a task raises).
"""

import harness.coding_loop as coding_loop
from harness.eval_runner import Task, run_task_list
from harness import research_guard

# #EXT-038-REQ-3 Start


def _stub_task(id_: str) -> Task:
    return Task(id=id_, instruction="noop", target="target.py", test_cmd="true", files={}, tier=1)


def test_research_locked_during_task_execution_and_released_after(monkeypatch):
    observed = {}

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False):
        observed["allowed_during"] = research_guard.research_allowed()
        return coding_loop.LoopResult(success=True, attempts=1, final_output="ok")

    monkeypatch.setattr(coding_loop, "fix_loop", fake_fix_loop)

    assert research_guard.research_allowed() is True  # sanity: unlocked before the run

    sc = run_task_list([_stub_task("t1")], max_iters=1, verbose=False)

    assert observed["allowed_during"] is False, "research must be LOCKED while a task is executing"
    assert research_guard.research_allowed() is True, "research must be UNLOCKED once run_task_list returns"
    assert sc["solved"] == 1 and sc["total"] == 1


def test_lock_releases_even_when_a_task_raises(monkeypatch):
    def raising_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False):
        raise RuntimeError("simulated task failure")

    monkeypatch.setattr(coding_loop, "fix_loop", raising_fix_loop)

    assert research_guard.research_allowed() is True

    # run_task_list catches per-task exceptions internally (never sinks the suite) -- must not raise.
    sc = run_task_list([_stub_task("t2")], max_iters=1, verbose=False)

    assert sc["solved"] == 0 and sc["total"] == 1  # the task failed, recorded as unsolved
    assert research_guard.research_allowed() is True, "lock must release even after a task exception"


def test_lock_releases_after_multiple_tasks(monkeypatch):
    calls = []

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False):
        calls.append(research_guard.research_allowed())
        return coding_loop.LoopResult(success=True, attempts=1, final_output="ok")

    monkeypatch.setattr(coding_loop, "fix_loop", fake_fix_loop)

    run_task_list([_stub_task("a"), _stub_task("b")], max_iters=1, verbose=False)

    assert calls == [False, False], "research must stay locked for every task in the run"
    assert research_guard.research_allowed() is True

# #EXT-038-REQ-3 End
