"""Offline test for the SHARED tree-kill helper (harness/proc_treekill.py, EXT-005/REQ-12).

Spawns (via shell=True) a long-lived child process, gives run_with_treekill a short timeout,
and asserts BOTH that the call returns promptly/falsey AND that the spawned child process is
actually dead afterward -- proving the WHOLE process tree was killed (not just the immediate
shell), the same guarantee `harness/pass1_eval.py::_run_with_treekill` already gives the
eval-harness sites. No LLM / network required.

REQ: EXT-005-REQ-12 (shared tree-kill helper for the remaining local pytest-timeout sites)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from harness.proc_treekill import run_with_treekill


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check, guarded per-OS (os.name)."""
    if os.name == "nt":
        out = subprocess.run(
            f'tasklist /FI "PID eq {pid}"', shell=True,
            capture_output=True, text=True,
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_pidfile(pidfile: Path, timeout: float = 5.0) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pidfile.exists():
            try:
                return int(pidfile.read_text(encoding="utf-8").strip())
            except ValueError:
                pass
        time.sleep(0.2)
    return None


def test_run_with_treekill_kills_the_whole_tree(tmp_path):
    """A timed-out shell=True command returns falsey promptly AND the grandchild it spawned
    is actually dead afterward (not just the immediate shell)."""
    # #EXT-005-REQ-12 Start
    pidfile = tmp_path / "child.pid"
    script = tmp_path / "child.py"
    script.write_text(
        "import os, sys, time\n"
        "open(sys.argv[1], 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n",
        encoding="utf-8", newline="\n",
    )
    cmd = f'"{sys.executable}" "{script}" "{pidfile}"'

    t0 = time.monotonic()
    ok = run_with_treekill(cmd, str(tmp_path), timeout=2)
    elapsed = time.monotonic() - t0

    assert ok is False, "a timed-out command must report failure"
    assert elapsed < 10, f"run_with_treekill took {elapsed:.1f}s -- did not return promptly"

    child_pid = _wait_for_pidfile(pidfile)
    assert child_pid is not None, "child never started -- test setup broken"

    time.sleep(0.5)  # let the OS finish tearing the killed process down
    assert not _pid_alive(child_pid), f"child pid {child_pid} still alive -- tree not fully killed"
    # #EXT-005-REQ-12 End


def test_run_with_treekill_capture_returns_output_on_success(tmp_path):
    """capture=True returns (ok, output) with the command's real stdout on a clean exit."""
    # #EXT-005-REQ-12 Start
    ok, out = run_with_treekill(f'"{sys.executable}" -c "print(1+1)"', str(tmp_path),
                                timeout=15, capture=True)
    assert ok is True
    assert "2" in out
    # #EXT-005-REQ-12 End


def test_run_with_treekill_capture_timeout_is_falsey(tmp_path):
    """capture=True still reports False on a timeout (shape callers can rely on)."""
    # #EXT-005-REQ-12 Start
    script = tmp_path / "sleeper.py"
    script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8", newline="\n")
    cmd = f'"{sys.executable}" "{script}"'

    ok, out = run_with_treekill(cmd, str(tmp_path), timeout=2, capture=True)
    assert ok is False
    assert isinstance(out, str)
    # #EXT-005-REQ-12 End
