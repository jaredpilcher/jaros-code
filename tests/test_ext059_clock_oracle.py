"""EXT-059 REQ-10: offline tests for the deterministic injectable-clock oracle.

Every fixture here is a small, hand-written Python module written to a temp directory -- never a
live ``build_system``/gemma run (that is an explicit, separate manual smoke, not part of this
pytest suite). No external service, no network, no model call anywhere: stdlib only. These tests
are pure execution-plane verification of a deterministic module and must never reach the Jetson.

Run in isolation: ``python -m pytest tests/test_ext059_clock_oracle.py -q``.
"""

# #EXT-059-REQ-10 Start
# TASK-8
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from harness.clock_oracle import grade_clock, validate_spec

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Fixtures: a sliding-window rate limiter (SLA-timer/lockout-backoff shaped class).
# --------------------------------------------------------------------------------------------

# A correctly-implemented rate limiter: `allow()` consults the INJECTED clock, drops calls
# outside the window, and refuses once `limit` calls are active inside the window.
CORRECT_RATE_LIMITER = """
    class RateLimiter:
        def __init__(self, now_fn, limit, window):
            self._now_fn = now_fn
            self._limit = limit
            self._window = window
            self._calls = []

        def allow(self):
            now = self._now_fn()
            self._calls = [t for t in self._calls if now - t < self._window]
            if len(self._calls) >= self._limit:
                return False
            self._calls.append(now)
            return True
"""

# The flagship honesty bug: `now_fn` is accepted per the contract (so the constructor signature
# looks correct) but never actually consulted -- `allow()` secretly uses the REAL wall clock.
BROKEN_REAL_CLOCK_RATE_LIMITER = """
    import time

    class RateLimiter:
        def __init__(self, now_fn, limit, window):
            self._now_fn = now_fn  # accepted, but never called -- the bug
            self._limit = limit
            self._window = window
            self._calls = []

        def allow(self):
            now = time.time()  # BUG: real wall clock instead of the injected now_fn
            self._calls = [t for t in self._calls if now - t < self._window]
            if len(self._calls) >= self._limit:
                return False
            self._calls.append(now)
            return True
"""

# An off-by-one window-boundary bug: uses '<=' instead of '<', so a call exactly `window`
# seconds old is (incorrectly) still counted as active for one extra second.
BROKEN_OFF_BY_ONE_RATE_LIMITER = """
    class RateLimiter:
        def __init__(self, now_fn, limit, window):
            self._now_fn = now_fn
            self._limit = limit
            self._window = window
            self._calls = []

        def allow(self):
            now = self._now_fn()
            # BUG: '<=' keeps a call alive one extra second exactly at the window boundary.
            self._calls = [t for t in self._calls if now - t <= self._window]
            if len(self._calls) >= self._limit:
                return False
            self._calls.append(now)
            return True
"""

RATE_LIMITER_SPEC = {
    "clock_param": "now_fn",
    "construct_kwargs": {"limit": 3, "window": 3600},
    "timeline": [
        {"at": 1_000_000, "call": "allow", "expect": {"returns": True}},
        {"at": 1_000_000, "call": "allow", "expect": {"returns": True}},
        {"at": 1_000_000, "call": "allow", "expect": {"returns": True}},
        {"at": 1_000_000, "call": "allow", "expect": {"returns": False}},
        # The wall-clock-impossible jump: 3601 SIMULATED seconds later, executed in real
        # milliseconds -- only an entity that actually consults the injected clock can see the
        # window as expired here.
        {"at": 1_000_000 + 3601, "call": "allow", "expect": {"returns": True}},
    ],
}

# A dedicated boundary-exact spec (elapsed == window, not > window) to catch an off-by-one
# comparison bug that a clearly-past-the-window jump (RATE_LIMITER_SPEC above) would not expose.
BOUNDARY_SPEC = {
    "clock_param": "now_fn",
    "construct_kwargs": {"limit": 3, "window": 3600},
    "timeline": [
        {"at": 1000, "call": "allow", "expect": {"returns": True}},
        {"at": 1000, "call": "allow", "expect": {"returns": True}},
        {"at": 1000, "call": "allow", "expect": {"returns": True}},
        {"at": 1000, "call": "allow", "expect": {"returns": False}},
        {"at": 1000 + 3600, "call": "allow", "expect": {"returns": True}},
    ],
}


# --------------------------------------------------------------------------------------------
# Fixtures: a token/magic-link validity window.
# --------------------------------------------------------------------------------------------

# A correctly-implemented token validator: valid up to (and including) `ttl` seconds after
# issue, expired (raises) strictly beyond it.
CORRECT_TOKEN_VALIDATOR = """
    class TokenValidator:
        def __init__(self, now_fn, issued_at, ttl):
            self._now_fn = now_fn
            self._issued_at = issued_at
            self._ttl = ttl

        def check(self):
            now = self._now_fn()
            if now - self._issued_at > self._ttl:
                raise ValueError("token expired")
            return True
"""

# The missing-expiry-check bug: `check()` never consults the clock at all, so an expired token
# is silently accepted forever.
BROKEN_NEVER_EXPIRES_TOKEN_VALIDATOR = """
    class TokenValidator:
        def __init__(self, now_fn, issued_at, ttl):
            self._now_fn = now_fn
            self._issued_at = issued_at
            self._ttl = ttl

        def check(self):
            # BUG: no expiry check at all -- always valid.
            return True
"""

TOKEN_SPEC = {
    "clock_param": "now_fn",
    "construct_kwargs": {"issued_at": 1000, "ttl": 3600},
    "timeline": [
        {"at": 1000, "call": "check", "expect": {"returns": True}},
        {"at": 1000 + 1800, "call": "check", "expect": {"returns": True}},
        # Both directions: valid well inside the window, then expired just past it.
        {"at": 1000 + 3601, "call": "check", "expect": {"raises": "ValueError"}},
    ],
}


# --------------------------------------------------------------------------------------------
# Fixtures: a trivial clock reader (for the allow_backward positive path) and garbage fixtures.
# --------------------------------------------------------------------------------------------

CLOCK_READER = """
    class ClockReader:
        def __init__(self, now_fn):
            self._now_fn = now_fn

        def read(self):
            return self._now_fn()
"""

BACKWARD_SPEC = {
    "clock_param": "now_fn",
    "timeline": [
        {"at": 1000, "call": "read", "expect": {"returns": 1000}},
        {"at": 500, "call": "read", "expect": {"returns": 500}, "allow_backward": True},
    ],
}

# A constructor requiring an extra positional argument the spec never supplies -- construction
# itself raises, before any timeline step is ever reached.
NEEDS_ARG_MODULE = """
    class NeedsArg:
        def __init__(self, now_fn, required_positional):
            pass

        def noop(self):
            return None
"""

NEEDS_ARG_SPEC = {
    "clock_param": "now_fn",
    "timeline": [
        {"at": 1, "call": "noop", "expect": {"returns": None}},
    ],
}

# A garbage fixture: raises at IMPORT time, before any entity could ever be constructed.
CRASHING_MODULE = """
    raise RuntimeError("boom -- this module is broken at import time")
"""


# --------------------------------------------------------------------------------------------
# validate_spec
# --------------------------------------------------------------------------------------------

def test_validate_spec_accepts_well_formed_spec():
    ok, note = validate_spec(RATE_LIMITER_SPEC)
    assert ok, note


def test_validate_spec_rejects_malformed_specs():
    ok, note = validate_spec({"clock_param": "now_fn"})  # missing timeline
    assert not ok
    assert note

    ok, note = validate_spec("not a dict")
    assert not ok

    bad = dict(RATE_LIMITER_SPEC)
    bad["clock_param"] = 123  # not a string
    ok, note = validate_spec(bad)
    assert not ok
    assert "clock_param" in note


def test_validate_spec_rejects_construct_kwargs_clashing_with_clock_param():
    bad = dict(RATE_LIMITER_SPEC)
    bad["construct_kwargs"] = {"now_fn": "should not be here", "limit": 3, "window": 3600}
    ok, note = validate_spec(bad)
    assert not ok
    assert "construct_kwargs" in note


def test_validate_spec_rejects_non_int_at():
    bad = dict(RATE_LIMITER_SPEC)
    bad["timeline"] = [{"at": 1.5, "call": "allow", "expect": {"returns": True}}]
    ok, note = validate_spec(bad)
    assert not ok
    assert "at" in note


def test_validate_spec_rejects_bad_expect_shape():
    bad = dict(RATE_LIMITER_SPEC)
    bad["timeline"] = [{"at": 1, "call": "allow", "expect": {"neither": True}}]
    ok, note = validate_spec(bad)
    assert not ok
    assert "expect" in note

    bad2 = dict(RATE_LIMITER_SPEC)
    bad2["timeline"] = [{"at": 1, "call": "allow", "expect": {"returns": True, "raises": "X"}}]
    ok, note = validate_spec(bad2)
    assert not ok


def test_validate_spec_rejects_backward_timeline_without_allow_backward():
    bad = dict(RATE_LIMITER_SPEC)
    bad["timeline"] = [
        {"at": 1000, "call": "allow", "expect": {"returns": True}},
        {"at": 500, "call": "allow", "expect": {"returns": True}},
    ]
    ok, note = validate_spec(bad)
    assert not ok
    assert "backward" in note.lower()


def test_validate_spec_accepts_backward_timeline_with_allow_backward():
    ok, note = validate_spec(BACKWARD_SPEC)
    assert ok, note


# --------------------------------------------------------------------------------------------
# grade_clock: correct fixtures pass.
# --------------------------------------------------------------------------------------------

def test_correct_rate_limiter_passes(tmp_path):
    _write(tmp_path, "limiter.py", CORRECT_RATE_LIMITER)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="RateLimiter", spec=RATE_LIMITER_SPEC, python_exe=PY,
    )
    assert accepted, note
    assert "ok" in note.lower()


def test_correct_rate_limiter_passes_at_exact_window_boundary(tmp_path):
    _write(tmp_path, "limiter.py", CORRECT_RATE_LIMITER)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="RateLimiter", spec=BOUNDARY_SPEC, python_exe=PY,
    )
    assert accepted, note


def test_correct_token_validator_passes(tmp_path):
    _write(tmp_path, "token.py", CORRECT_TOKEN_VALIDATOR)

    accepted, note = grade_clock(
        tmp_path, module="token", entity="TokenValidator", spec=TOKEN_SPEC, python_exe=PY,
    )
    assert accepted, note


def test_backward_jump_executes_when_allowed(tmp_path):
    _write(tmp_path, "clock_reader.py", CLOCK_READER)

    accepted, note = grade_clock(
        tmp_path, module="clock_reader", entity="ClockReader", spec=BACKWARD_SPEC, python_exe=PY,
    )
    assert accepted, note


# --------------------------------------------------------------------------------------------
# grade_clock: the honesty core -- a real-clock or off-by-one bug must be CAUGHT.
# --------------------------------------------------------------------------------------------

def test_real_clock_bug_is_caught(tmp_path):
    """The flagship honesty test: a build that accepts the injected `now_fn` per the contract
    but secretly consults the REAL wall clock must be caught -- the 3601-simulated-second jump
    executes in real milliseconds, so a real-clock build cannot see the window as expired."""
    _write(tmp_path, "limiter.py", BROKEN_REAL_CLOCK_RATE_LIMITER)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="RateLimiter", spec=RATE_LIMITER_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_off_by_one_boundary_bug_is_caught(tmp_path):
    """A correct implementation passes `BOUNDARY_SPEC` (see above); an off-by-one '<=' bug that
    keeps a call alive exactly at the window boundary must be caught by the same spec."""
    _write(tmp_path, "limiter.py", BROKEN_OFF_BY_ONE_RATE_LIMITER)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="RateLimiter", spec=BOUNDARY_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_missing_expiry_check_bug_is_caught(tmp_path):
    """A token validator that never actually checks the injected clock (always valid) must be
    caught by a timeline that expects it to raise once past its declared ttl."""
    _write(tmp_path, "token.py", BROKEN_NEVER_EXPIRES_TOKEN_VALIDATOR)

    accepted, note = grade_clock(
        tmp_path, module="token", entity="TokenValidator", spec=TOKEN_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


# --------------------------------------------------------------------------------------------
# NEVER RAISES matrix.
# --------------------------------------------------------------------------------------------

def test_never_raises_on_crashing_module(tmp_path):
    _write(tmp_path, "limiter.py", CRASHING_MODULE)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="RateLimiter", spec=RATE_LIMITER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_missing_module(tmp_path):
    accepted, note = grade_clock(
        tmp_path, module="does_not_exist_at_all", entity="RateLimiter",
        spec=RATE_LIMITER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_missing_entity(tmp_path):
    _write(tmp_path, "limiter.py", CORRECT_RATE_LIMITER)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="NoSuchClass", spec=RATE_LIMITER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_construct_exception(tmp_path):
    """The constructor itself raises (a required argument the spec never supplies) before any
    timeline step is ever reached -- an honest failure, never an uncaught exception."""
    _write(tmp_path, "needs_arg.py", NEEDS_ARG_MODULE)

    accepted, note = grade_clock(
        tmp_path, module="needs_arg", entity="NeedsArg", spec=NEEDS_ARG_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_malformed_spec(tmp_path):
    _write(tmp_path, "limiter.py", CORRECT_RATE_LIMITER)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="RateLimiter", spec={"garbage": True}, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_garbage_spec_type(tmp_path):
    _write(tmp_path, "limiter.py", CORRECT_RATE_LIMITER)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="RateLimiter", spec=None, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_invalid_entity_identifier(tmp_path):
    _write(tmp_path, "limiter.py", CORRECT_RATE_LIMITER)

    accepted, note = grade_clock(
        tmp_path, module="limiter", entity="not an identifier", spec=RATE_LIMITER_SPEC,
        python_exe=PY,
    )
    assert accepted is False
    assert note
# #EXT-059-REQ-10 End
