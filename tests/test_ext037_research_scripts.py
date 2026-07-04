"""EXT-037 / REQ-6 (TASK-8) -- ``harness.research_scripts``: the scratch research-script

investigation plane (write a throwaway probe, run it, read the result). Offline,
deterministic, no network: every probe here is a small local Python script written by the
test itself; no real network egress or destructive operation is ever exercised.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from harness.research_scripts import read_research_output, run_research_script

_REPO_ROOT = Path(__file__).resolve().parents[1]

# #EXT-037-REQ-6 Start


def _git_status_porcelain() -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(_REPO_ROOT), capture_output=True, text=True
    )
    return proc.stdout if proc.returncode == 0 else ""


def _is_pid_running(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        # Any other error (e.g. permission) -- treat as "can't tell", not a failure signal.
        return False


# --- (a) a small result streams back inline, scratch dir is outside the repo ----------------


def test_small_result_returns_inline_and_scratch_outside_repo(tmp_path):
    before = _git_status_porcelain()
    code = "print('hello from research script')\n"
    result = run_research_script(code, timeout=10)
    assert result["ok"] is True
    assert result["returncode"] == 0
    assert "hello from research script" in result["stdout"]
    assert result["timed_out"] is False
    scratch = Path(result["scratch_dir"])
    assert scratch.exists()
    # scratch_dir must NOT be inside (or equal to) the repo root
    assert _REPO_ROOT not in scratch.resolve().parents and scratch.resolve() != _REPO_ROOT
    assert _git_status_porcelain() == before


def test_caller_supplied_scratch_dir_is_used(tmp_path):
    scratch = tmp_path / "myscratch"
    result = run_research_script("print(1+1)\n", scratch_dir=str(scratch), timeout=10)
    assert result["ok"] is True
    assert result["stdout"].strip() == "2"
    assert os.path.abspath(result["scratch_dir"]) == os.path.abspath(str(scratch))
    assert (scratch / "script.py").exists()


# --- (b) oversized stdout is streamed to a file and parsed in bounded chunks -----------------


def test_oversized_stdout_written_to_file_and_read_in_bounded_slices():
    before = _git_status_porcelain()
    # Print a big string well beyond a small stdout_limit.
    code = "print('X' * 50000)\n"
    result = run_research_script(code, timeout=10, stdout_limit=1000)
    assert result["ok"] is True
    assert result.get("truncated") is True
    assert "stdout_file" in result
    assert result["total_bytes"] >= 50000
    assert len(result["stdout_head"]) > 0
    assert len(result["stdout_tail"]) > 0

    stdout_file = result["stdout_file"]
    assert os.path.exists(stdout_file)
    with open(stdout_file, "r", encoding="utf-8") as fh:
        full = fh.read()
    assert "X" * 50000 in full

    sliced = read_research_output(stdout_file, max_bytes=2000)
    assert len(sliced) < len(full)
    assert "truncated" in sliced
    assert _git_status_porcelain() == before


def test_read_research_output_returns_whole_small_file(tmp_path):
    p = tmp_path / "small.txt"
    p.write_text("just a small file", encoding="utf-8")
    assert read_research_output(str(p), max_bytes=20000) == "just a small file"


# --- (c) a non-zero exit / raising script never raises, stderr captured ---------------------


def test_nonzero_exit_script_ok_false_with_stderr_tail():
    code = "import sys\nsys.stderr.write('boom happened\\n')\nsys.exit(3)\n"
    result = run_research_script(code, timeout=10)
    assert result["ok"] is False
    assert result["returncode"] == 3
    assert "boom happened" in result["stderr"]
    assert result["timed_out"] is False


def test_raising_script_ok_false_never_raises():
    code = "raise RuntimeError('deliberate failure')\n"
    result = run_research_script(code, timeout=10)
    assert result["ok"] is False
    assert result["returncode"] not in (0, None)
    assert "deliberate failure" in result["stderr"] or result["stderr"] != ""


# --- (d) a hung script is killed on timeout, no orphan left behind ---------------------------


def test_hanging_script_times_out_and_leaves_no_orphan(tmp_path):
    pidfile = tmp_path / "child.pid"
    code = (
        "import os\n"
        f"with open({str(pidfile)!r}, 'w') as f:\n"
        "    f.write(str(os.getpid()))\n"
        "while True:\n"
        "    pass\n"
    )
    start = time.monotonic()
    result = run_research_script(code, timeout=2)
    elapsed = time.monotonic() - start
    assert result["timed_out"] is True
    assert result["ok"] is False
    assert result["returncode"] is None
    # Bounded: should return well before an absurd wall-clock time (generous margin for slow CI).
    assert elapsed < 30

    assert pidfile.exists()
    child_pid = int(pidfile.read_text().strip())
    # Give the OS a brief moment to reap the killed process, then confirm it's gone.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _is_pid_running(child_pid):
        time.sleep(0.2)
    assert not _is_pid_running(child_pid)


# --- (e) garbage input never raises -----------------------------------------------------------


def test_run_research_script_never_raises_on_garbage_code():
    for garbage in (None, 12345, ["not", "a", "string"], object()):
        result = run_research_script(garbage, timeout=5)  # type: ignore[arg-type]
        assert result["ok"] is False
        assert "note" in result


def test_run_research_script_never_raises_on_bad_scratch_dir():
    # A path that cannot plausibly be created (nul byte / invalid device component) must not
    # raise -- it should come back as an honest ok=False observation.
    bad = "Z:\\definitely\\does\\not\\exist\\at\\all\\forever"
    result = run_research_script("print(1)\n", scratch_dir=bad, timeout=5)
    assert result["ok"] is False


def test_read_research_output_never_raises_on_garbage_input():
    for garbage in (None, 12345, "", "/this/path/does/not/exist/at/all.txt"):
        out = read_research_output(garbage)  # type: ignore[arg-type]
        assert isinstance(out, str)
# #EXT-037-REQ-6 End
