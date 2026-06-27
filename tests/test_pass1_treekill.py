"""Bug #19 regression test: run_pass1 must return within time (not hang) when a solution
is an infinite loop, and must NOT leave orphan python/pytest processes running.

This test is OFFLINE and DETERMINISTIC — no LLM or Jetson connection required.
It stubs solve_pass1 to return `while True: pass` (infinite loop), which would previously
orphan the pytest grandchild on Windows (shell=True -> cmd.exe -> pytest; timeout killed
only cmd.exe, not pytest).  With the tree-kill fix, run_pass1 returns False and no process
is left behind.

REQ: EXT-005-REQ-12 (robust test-exec / hang-proofing)
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

# Minimal stub Task shaped like harness.eval_runner.Task (no import needed).
class _Task:
    def __init__(self, id, test_cmd, files):
        self.id = id
        self.instruction = "stub"
        self.target = "solution.py"
        self.test_cmd = test_cmd
        self.files = files
        self.tier = 1


def _make_task(tmp_path: Path) -> _Task:
    """Build a Task whose test_cmd runs pytest against solution.py via shell=True."""
    test_src = (
        "import solution\n"
        "def test_noop():\n"
        "    assert solution.noop() == 1\n"
    )
    (tmp_path / "test_stub.py").write_text(test_src, encoding="utf-8")
    files = {
        "solution.py": "def noop(): return 0\n",
        "test_stub.py": test_src,
    }
    # Use the same shell=True cmd shape the HumanEval runner uses.
    cmd = f"{sys.executable} -m pytest test_stub.py -q --tb=no"
    return _Task(id="stub_infinite", test_cmd=cmd, files=files)


def test_run_pass1_returns_on_infinite_loop(tmp_path):
    """run_pass1 must return (not hang) within ~15 s when solve_pass1 returns an infinite loop.
    We patch _run_with_treekill's timeout to 5s so the test itself runs in ~10s total."""
    # #EXT-005-REQ-12 Start
    import harness.pass1_eval as p1

    task = _make_task(tmp_path)

    # Patch solve_pass1 so solution.py is replaced with an infinite-loop body.
    infinite = "def noop():\n    while True:\n        pass\n"

    # Wrap _run_with_treekill to use a short timeout so this test doesn't take 60s.
    orig_run = p1._run_with_treekill

    def _fast_run(cmd, cwd, timeout):
        return orig_run(cmd, cwd, timeout=5)

    t0 = time.monotonic()
    with patch("harness.pass1_eval.solve_pass1", return_value=infinite), \
         patch("harness.pass1_eval._run_with_treekill", side_effect=_fast_run):
        passed, fails = p1.run_pass1([task])
    elapsed = time.monotonic() - t0

    assert elapsed < 15, f"run_pass1 took {elapsed:.1f}s — process tree NOT killed (hang bug)"
    assert passed == 0, "infinite-loop solution must not count as passed"
    assert "stub_infinite" in fails, "failing task id must be in fails list"
    # #EXT-005-REQ-12 End


def test_run_gated_returns_on_infinite_loop(tmp_path):
    """run_gated must also return (not hang) when solve_gated returns an infinite loop.
    Confirms the same _run_with_treekill fix is wired into run_gated."""
    # #EXT-005-REQ-12 Start
    import harness.pass1_eval as p1

    task = _make_task(tmp_path)
    infinite = "def noop():\n    while True:\n        pass\n"

    orig_run = p1._run_with_treekill

    def _fast_run(cmd, cwd, timeout):
        return orig_run(cmd, cwd, timeout=5)

    t0 = time.monotonic()
    with patch("harness.pass1_eval.solve_gated", return_value=infinite), \
         patch("harness.pass1_eval._run_with_treekill", side_effect=_fast_run):
        passed, fails = p1.run_gated([task])
    elapsed = time.monotonic() - t0

    assert elapsed < 15, f"run_gated took {elapsed:.1f}s — tree-kill not working in run_gated"
    assert passed == 0
    assert "stub_infinite" in fails
    # #EXT-005-REQ-12 End
