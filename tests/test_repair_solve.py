"""Offline tests for harness.repair_solve (EXT-032 REQ-1).

All gen_fn / test_fn callables are mocks — no Jetson, no Docker, no filesystem I/O.
"""
import pytest
from harness.repair_solve import repair_solve, make_r1_gen_fn


# ---------------------------------------------------------------------------
# (a) First attempt passes -> retries 0, gen_fn called exactly once
# ---------------------------------------------------------------------------

def test_first_attempt_passes_no_retries():
    gen_calls = []

    def gen_fn(spec, name, context):
        gen_calls.append(context)
        return "def foo(): return 1"

    def test_fn(code):
        return {"passed": True, "failure_text": ""}

    result = repair_solve("spec", "foo", "initial_ctx", gen_fn=gen_fn, test_fn=test_fn)

    assert result["solved"] is True
    assert result["retries"] == 0
    assert result["code"] == "def foo(): return 1"
    assert len(gen_calls) == 1
    assert len(result["attempts"]) == 1


# ---------------------------------------------------------------------------
# (b) First attempt fails, first retry passes -> solved=True, retries=1,
#     and the 2nd gen_fn call's context MUST contain the failure text
# ---------------------------------------------------------------------------

def test_retry_passes_failure_text_in_context():
    gen_calls = []
    call_count = [0]

    def gen_fn(spec, name, context):
        gen_calls.append(context)
        return f"def foo(): pass  # attempt {len(gen_calls)}"

    def test_fn(code):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"passed": False, "failure_text": "AssertionError: expected 42, got None"}
        return {"passed": True, "failure_text": ""}

    result = repair_solve(
        "my spec", "foo", "initial_context",
        gen_fn=gen_fn, test_fn=test_fn,
    )

    assert result["solved"] is True
    assert result["retries"] == 1
    assert len(gen_calls) == 2
    assert len(result["attempts"]) == 2
    # The SECOND gen_fn call must have received the failure text in its context.
    assert "AssertionError: expected 42, got None" in gen_calls[1], (
        "failure_text must be fed into the 2nd gen_fn call's context"
    )
    # The repair context must also reference the previous attempt.
    assert "Your previous attempt" in gen_calls[1]
    assert "The test FAILED with" in gen_calls[1]


# ---------------------------------------------------------------------------
# (c) All attempts fail -> solved:False, max_retries respected
# ---------------------------------------------------------------------------

def test_all_attempts_fail_max_retries_respected():
    gen_calls = []

    def gen_fn(spec, name, context):
        gen_calls.append(context)
        return "def foo(): return 0"

    def test_fn(code):
        return {"passed": False, "failure_text": "always fails"}

    result = repair_solve(
        "spec", "foo", "ctx",
        gen_fn=gen_fn, test_fn=test_fn, max_retries=2,
    )

    assert result["solved"] is False
    assert result["retries"] == 2
    # 1 initial attempt + 2 retries = 3 total gen_fn calls.
    assert len(gen_calls) == 3
    assert len(result["attempts"]) == 3


def test_max_retries_zero_means_one_attempt():
    gen_calls = []

    def gen_fn(spec, name, context):
        gen_calls.append(context)
        return "def foo(): return 0"

    def test_fn(code):
        return {"passed": False, "failure_text": "nope"}

    result = repair_solve(
        "spec", "foo", "ctx",
        gen_fn=gen_fn, test_fn=test_fn, max_retries=0,
    )

    assert result["solved"] is False
    assert result["retries"] == 0
    assert len(gen_calls) == 1
    assert len(result["attempts"]) == 1


# ---------------------------------------------------------------------------
# (d) test_fn is the SOLE arbiter: gen_fn emits "correct-looking" code,
#     but test_fn always returns failed -> result must be solved=False
# ---------------------------------------------------------------------------

def test_test_fn_sole_arbiter_overrides_gen():
    gen_calls = []

    def gen_fn(spec, name, context):
        gen_calls.append(context)
        # Code looks superficially correct and "claims success" by its content.
        return "def foo(): return 42  # correct!"

    def test_fn(code):
        # No matter what gen_fn returns, test_fn is authoritative: FAIL.
        return {"passed": False, "failure_text": "test_fn says no"}

    result = repair_solve(
        "spec", "foo", "ctx",
        gen_fn=gen_fn, test_fn=test_fn, max_retries=1,
    )

    # test_fn is sole arbiter — even though the code "looks correct", it's not solved.
    assert result["solved"] is False
    # 1 initial + 1 retry = 2 calls.
    assert len(gen_calls) == 2


# ---------------------------------------------------------------------------
# Additional: attempts list captures all generated code in order
# ---------------------------------------------------------------------------

def test_attempts_list_in_order():
    codes = ["def foo(): return 1", "def foo(): return 2", "def foo(): return 3"]
    idx = [0]

    def gen_fn(spec, name, context):
        code = codes[idx[0]]
        idx[0] += 1
        return code

    def test_fn(code):
        # Only the third attempt passes.
        return {"passed": code == "def foo(): return 3", "failure_text": "not yet"}

    result = repair_solve("spec", "foo", "ctx", gen_fn=gen_fn, test_fn=test_fn, max_retries=2)

    assert result["solved"] is True
    assert result["retries"] == 2
    assert result["attempts"] == codes
    assert result["code"] == "def foo(): return 3"


# ---------------------------------------------------------------------------
# make_r1_gen_fn: factory is importable offline and returns a callable
# ---------------------------------------------------------------------------

def test_make_r1_gen_fn_returns_callable(monkeypatch):
    """make_r1_gen_fn() must return a callable without connecting to the Jetson."""
    # Patch r1_adapt.r1_code so the Jetson is never called.
    import harness.r1_adapt as r1_mod
    monkeypatch.setattr(r1_mod, "r1_code", lambda spec, name, ctx="": "def foo(): pass")

    gen_fn = make_r1_gen_fn()
    assert callable(gen_fn)
    # Verify it delegates correctly (monkeypatched version returns the stub).
    code = gen_fn("spec", "foo", "ctx")
    assert "def foo" in code


# ---------------------------------------------------------------------------
# Syntax / import smoke
# ---------------------------------------------------------------------------

def test_import_repair_solve_clean():
    """harness.repair_solve must import without errors."""
    import importlib
    import harness.repair_solve as m
    importlib.reload(m)
    assert hasattr(m, "repair_solve")
    assert hasattr(m, "make_r1_gen_fn")


def test_repair_solve_return_keys():
    """Return dict always contains the four required keys."""
    def gen_fn(spec, name, ctx):
        return "def foo(): pass"
    def test_fn(code):
        return {"passed": False, "failure_text": ""}

    result = repair_solve("s", "foo", "c", gen_fn=gen_fn, test_fn=test_fn, max_retries=0)
    assert {"solved", "code", "retries", "attempts"} <= set(result.keys())
