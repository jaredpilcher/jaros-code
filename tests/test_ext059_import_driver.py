"""EXT-059 REQ-3: offline tests for the deterministic import-and-call acceptance oracle.

Every fixture here is a small, hand-written Python module written to a temp directory -- never a
live ``build_system``/gemma run (that is an explicit, separate manual smoke, not part of this
pytest suite). No external service, no network, no model call anywhere: stdlib only. These tests
are pure execution-plane verification of a deterministic module and must never reach the Jetson.
"""

# #EXT-059-REQ-3 Start
# TASK-3
from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

from harness.import_driver import ImportDriveResult, drive_import

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# A small "reusable library" module: plain functions, no stdin/stdout contract at all.
MATHLIB = """
    def add(a, b):
        return a + b

    def divide(a, b):
        if b == 0:
            raise ZeroDivisionError("cannot divide by zero")
        return a / b
"""

# The SAME contract, but the addition is wrong -- import-and-call still succeeds, only the
# returned VALUE is wrong (never observable from stdout, which is exactly the gap REQ-3 closes).
BROKEN_MATHLIB = """
    def add(a, b):
        return a - b  # wrong: subtracts instead of adding

    def divide(a, b):
        if b == 0:
            raise ZeroDivisionError("cannot divide by zero")
        return a / b
"""

# A retry-with-backoff library: calls an injected `fetch_fn` up to `attempts` times, sleeping
# `backoff` seconds between failures. Proves both `call_count` grading AND injected-clock
# determinism (a real implementation would otherwise burn real wall-clock time here).
RETRYLIB = """
    import time

    def fetch_with_retry(fetch_fn, attempts=5, backoff=1.0):
        last_exc = None
        for _ in range(attempts):
            try:
                return fetch_fn()
            except Exception as exc:
                last_exc = exc
                time.sleep(backoff)
        raise last_exc
"""

# A "broken" retry library that gives up after the FIRST failure instead of retrying --
# the call_count check on the spy should catch this even though nothing prints anything.
NO_RETRY_LIB = """
    def fetch_with_retry(fetch_fn, attempts=5, backoff=1.0):
        return fetch_fn()  # never retries at all
"""

HANG_LIB = """
    def spin():
        while True:
            pass
"""


# --------------------------------------------------------------------------------------------
# returns_equals -- pass and fail
# --------------------------------------------------------------------------------------------

def test_correct_library_passes_returns_equals(tmp_path):
    _write(tmp_path, "mathlib.py", MATHLIB)
    result = drive_import(
        tmp_path, "mathlib",
        [{"id": "r1", "target": "add", "args": [2, 3]}],
        [{"kind": "returns_equals", "call_id": "r1", "expected": 5}],
        python_exe=PY,
    )
    assert isinstance(result, ImportDriveResult)
    assert result.ok is True, result.note
    assert result.failures == []
    assert result.checks_passed == 1


def test_broken_library_fails_returns_equals_without_any_stdout_signal(tmp_path):
    _write(tmp_path, "mathlib.py", BROKEN_MATHLIB)
    result = drive_import(
        tmp_path, "mathlib",
        [{"id": "r1", "target": "add", "args": [2, 3]}],
        [{"kind": "returns_equals", "call_id": "r1", "expected": 5}],
        python_exe=PY,
    )
    assert result.ok is False
    assert "returns_equals" in " | ".join(result.failures).lower()
    assert "-1" in " | ".join(result.failures)  # 2 - 3 == -1, the wrong value, in the diagnostic


# --------------------------------------------------------------------------------------------
# raises -- pass and fail (wrong exception type, and "unexpectedly did not raise")
# --------------------------------------------------------------------------------------------

def test_raises_check_passes_on_matching_exception(tmp_path):
    _write(tmp_path, "mathlib.py", MATHLIB)
    result = drive_import(
        tmp_path, "mathlib",
        [{"id": "d1", "target": "divide", "args": [1, 0]}],
        [{"kind": "raises", "call_id": "d1", "exception": "ZeroDivisionError"}],
        python_exe=PY,
    )
    assert result.ok is True, result.note


def test_raises_check_fails_on_wrong_exception_type(tmp_path):
    _write(tmp_path, "mathlib.py", MATHLIB)
    result = drive_import(
        tmp_path, "mathlib",
        [{"id": "d1", "target": "divide", "args": [1, 0]}],
        [{"kind": "raises", "call_id": "d1", "exception": "ValueError"}],
        python_exe=PY,
    )
    assert result.ok is False
    assert "raised zerodivisionerror" in " | ".join(result.failures).lower()


def test_raises_check_fails_when_call_returns_normally(tmp_path):
    _write(tmp_path, "mathlib.py", MATHLIB)
    result = drive_import(
        tmp_path, "mathlib",
        [{"id": "d1", "target": "divide", "args": [4, 2]}],
        [{"kind": "raises", "call_id": "d1", "exception": "ZeroDivisionError"}],
        python_exe=PY,
    )
    assert result.ok is False
    assert "instead of raising" in " | ".join(result.failures).lower()


# --------------------------------------------------------------------------------------------
# call_count (injected spy) + injected clock determinism -- the core "retry/cache library" case
# --------------------------------------------------------------------------------------------

_RETRY_INJECTED = {
    "clock": True,
    "spies": {
        "fetch": {"return_value": "pong", "raise_exception": "ConnectionError", "raise_count": 2},
    },
}
_RETRY_API_CALLS = [
    {"id": "r1", "target": "fetch_with_retry",
     "args": [{"__jaros_ref__": "fetch"}], "kwargs": {"attempts": 5, "backoff": 5.0}},
]
_RETRY_CHECKS = [
    {"kind": "returns_equals", "call_id": "r1", "expected": "pong"},
    {"kind": "call_count", "spy": "fetch", "expected": 3},
]


def test_correct_retry_library_passes_call_count_and_returns_equals(tmp_path):
    _write(tmp_path, "retrylib.py", RETRYLIB)
    result = drive_import(tmp_path, "retrylib", _RETRY_API_CALLS, _RETRY_CHECKS,
                           injected=_RETRY_INJECTED, python_exe=PY, timeout=15)
    assert result.ok is True, result.note
    assert result.checks_passed == 2


def test_no_retry_library_fails_call_count(tmp_path):
    _write(tmp_path, "retrylib.py", NO_RETRY_LIB)
    result = drive_import(tmp_path, "retrylib", _RETRY_API_CALLS, _RETRY_CHECKS,
                           injected=_RETRY_INJECTED, python_exe=PY, timeout=15)
    assert result.ok is False
    joined = " | ".join(result.failures).lower()
    # it never retries, so fetch is called once and the first (raising) attempt propagates --
    # both post-conditions the correct library satisfies should be caught as failures here.
    assert "call_count" in joined or "returns_equals" in joined


def test_injected_clock_proves_no_real_wall_clock_sleep(tmp_path):
    """The retry library sleeps ``backoff=5.0`` seconds between each of 2 failed attempts -- a
    REAL sleep would take >= 10s wall-clock. With the clock injected, the whole drive must
    complete in a small fraction of that, and the driver's own reported sleep-call count must
    match the number of failed attempts exactly."""
    _write(tmp_path, "retrylib.py", RETRYLIB)
    started = time.perf_counter()
    result = drive_import(tmp_path, "retrylib", _RETRY_API_CALLS, _RETRY_CHECKS,
                           injected=_RETRY_INJECTED, python_exe=PY, timeout=15)
    elapsed = time.perf_counter() - started
    assert result.ok is True, result.note
    assert elapsed < 5.0, f"took {elapsed:.2f}s -- looks like a REAL sleep happened"
    assert result.sleep_call_count == 2  # exactly the two failed attempts before success


def test_no_clock_injected_leaves_sleep_call_count_none(tmp_path):
    _write(tmp_path, "mathlib.py", MATHLIB)
    result = drive_import(
        tmp_path, "mathlib",
        [{"id": "r1", "target": "add", "args": [1, 1]}],
        [{"kind": "returns_equals", "call_id": "r1", "expected": 2}],
        python_exe=PY,
    )
    assert result.ok is True, result.note
    assert result.sleep_call_count is None


# --------------------------------------------------------------------------------------------
# Honest failures: unimportable module, timeout/process-tree teardown, malformed input
# --------------------------------------------------------------------------------------------

def test_module_that_fails_to_import_is_an_honest_failure(tmp_path):
    # No file named this way exists under tmp_path at all.
    result = drive_import(
        tmp_path, "does_not_exist_module_xyz",
        [{"id": "r1", "target": "add", "args": [1, 1]}],
        [{"kind": "returns_equals", "call_id": "r1", "expected": 2}],
        python_exe=PY,
    )
    assert result.ok is False
    assert "failed to import" in result.note.lower()
    assert result.failures == []  # short-circuited before any check was even evaluated


def test_module_with_a_syntax_error_is_an_honest_failure(tmp_path):
    _write(tmp_path, "brokenmod.py", "def add(a, b:\n    return a + b\n")  # invalid syntax
    result = drive_import(
        tmp_path, "brokenmod",
        [{"id": "r1", "target": "add", "args": [1, 1]}],
        [{"kind": "returns_equals", "call_id": "r1", "expected": 2}],
        python_exe=PY,
    )
    assert result.ok is False
    assert "failed to import" in result.note.lower()


def test_drive_import_times_out_and_kills_the_process_tree(tmp_path):
    _write(tmp_path, "hanglib.py", HANG_LIB)
    result = drive_import(
        tmp_path, "hanglib",
        [{"id": "r1", "target": "spin", "args": []}],
        [{"kind": "returns_equals", "call_id": "r1", "expected": None}],
        timeout=0.5, python_exe=PY,
    )
    assert result.ok is False
    assert "timed out" in result.note.lower()


def test_drive_import_never_raises_on_malformed_input(tmp_path):
    assert drive_import(object(), "mathlib", [], [{"kind": "x"}]).ok is False
    assert drive_import(tmp_path, "", [], [{"kind": "x"}]).ok is False
    assert drive_import(tmp_path, "mathlib", "not-a-list", [{"kind": "x"}]).ok is False
    assert drive_import(tmp_path, "mathlib", [{"no_id_or_target": True}], [{"kind": "x"}]).ok is False
    assert drive_import(tmp_path, "mathlib", [{"id": "r1", "target": "add"}], []).ok is False
    dup = [{"id": "r1", "target": "add", "args": [1, 1]},
           {"id": "r1", "target": "add", "args": [2, 2]}]
    assert drive_import(tmp_path, "mathlib", dup, [{"kind": "x"}]).ok is False


def test_unknown_check_kind_is_reported_as_a_failure_not_a_pass(tmp_path):
    _write(tmp_path, "mathlib.py", MATHLIB)
    result = drive_import(
        tmp_path, "mathlib",
        [{"id": "r1", "target": "add", "args": [1, 1]}],
        [{"kind": "bogus", "call_id": "r1"}],
        python_exe=PY,
    )
    assert result.ok is False
    assert "unknown check kind" in " | ".join(result.failures).lower()
# #EXT-059-REQ-3 End
