"""EXT-036 REQ-38: hard-tier escalation for the FIX/EDIT path (gemma-4-e2b -> qwen2.5-coder-7b
on repair failure), mirroring `test_ext036_escalate.py`'s coverage of `build_system_escalating`
(REQ-13) but for `harness.coding_loop.fix_loop_escalating`.

OFFLINE -- no live model, no network, no Jetson. `fix_loop` itself is MONKEYPATCHED at the
module level (`harness.coding_loop.fix_loop`) with a canned callable driven by CALL ORDER
(fix_loop_escalating always calls the primary attempt first, then -- only on failure, only when
configured -- a second, fallback attempt), so this file proves the ESCALATION WRAPPER's wiring
(when it escalates, when it swaps, when it restores, its never-raise robustness) in isolation
from `fix_loop`'s own multi-strategy pipeline (already covered by the existing coding_loop
tests).
"""

from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.coding_loop as cl
from harness.coding_loop import LoopResult, fix_loop_escalating

TARGET = "some_module.py"
INSTRUCTION = "fix the off-by-one bug"
TEST_CMD = "python -m pytest -q"

PASS_RESULT = LoopResult(success=True, attempts=1, final_output="1 passed")
FAIL_RESULT = LoopResult(success=False, attempts=3, final_output="1 failed")
FAIL_RESULT_2 = LoopResult(success=False, attempts=3, final_output="still 1 failed")


def _sequenced_fix_loop(results: list):
    """A `fix_loop`-shaped callable that returns `results[call_index]` on each successive call
    (fix_loop_escalating's primary attempt is always call 0; a fallback attempt, if any, is
    call 1). Records every call's kwargs so tests can assert on max_iters/cwd/etc threading."""
    calls: list[dict] = []

    def _fake(target, instruction, test_cmd, *, max_iters=4, cwd=None,
              editor_agent="rewriter_agent.py", verbose=True, keep_partial=False):
        calls.append({"target": target, "instruction": instruction, "test_cmd": test_cmd,
                       "max_iters": max_iters, "cwd": cwd, "editor_agent": editor_agent,
                       "verbose": verbose, "keep_partial": keep_partial})
        return results[len(calls) - 1]
    return _fake, calls


def _swap_recorder():
    calls: list[str] = []

    def _swap(model_id: str) -> None:
        calls.append(model_id)
    return _swap, calls


# --- (a) escalation fires ONLY on primary failure -------------------------------------------

def test_primary_passes_returns_primary_no_escalation(monkeypatch):
    fake, calls = _sequenced_fix_loop([PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)
    fallback_called = {"n": 0}

    def _never_swap(model_id: str) -> None:
        fallback_called["n"] += 1
        raise AssertionError("swap_fn must never be invoked when the primary already passes")

    result = fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=3,
        fallback_llm=object(), swap_fn=_never_swap,
        fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result.success is True
    assert result.escalated is False
    assert result.model == "primary"
    assert len(calls) == 1   # fallback fix_loop call NEVER made
    assert fallback_called["n"] == 0


def test_primary_fails_fallback_configured_escalates(monkeypatch):
    fake, calls = _sequenced_fix_loop([FAIL_RESULT, PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)
    swap_fn, swap_calls = _swap_recorder()

    result = fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=3,
        fallback_llm=object(), swap_fn=swap_fn,
        fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result.success is True
    assert result.escalated is True
    assert result.model == "fallback"
    assert len(calls) == 2   # primary attempt, then fallback attempt
    # swapped TO the fallback first, then back to the primary (restore)
    assert swap_calls == ["qwen2.5-coder-7b", "gemma-4-e2b"]


def test_primary_fails_no_fallback_llm_no_escalation(monkeypatch):
    """No fallback_llm supplied at all (the default) -> escalation never fires, even though
    the primary failed -- this is the "unconfigured" gate."""
    fake, calls = _sequenced_fix_loop([FAIL_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)

    result = fix_loop_escalating(TARGET, INSTRUCTION, TEST_CMD, max_iters=3)

    assert result.success is False
    assert result.escalated is False
    assert result.model == "primary"
    assert len(calls) == 1


# --- (b) escalated=False + byte-identical result when unconfigured (fallback=None) ----------

def test_unconfigured_result_is_byte_identical_to_plain_fix_loop(monkeypatch):
    """fallback_llm=None (the default, every existing caller) -> the returned LoopResult's
    success/attempts/final_output are EXACTLY what plain fix_loop would have returned, with
    only the escalated/model metadata fields added on top."""
    fake, calls = _sequenced_fix_loop([FAIL_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)

    result = fix_loop_escalating(TARGET, INSTRUCTION, TEST_CMD, max_iters=3)

    assert result.success == FAIL_RESULT.success
    assert result.attempts == FAIL_RESULT.attempts
    assert result.final_output == FAIL_RESULT.final_output
    assert result.escalated is False
    assert result.model == "primary"
    # the primary fix_loop call received exactly the caller's arguments, unmodified
    assert calls[0]["target"] == TARGET
    assert calls[0]["instruction"] == INSTRUCTION
    assert calls[0]["test_cmd"] == TEST_CMD
    assert calls[0]["max_iters"] == 3


def test_unconfigured_passing_result_also_byte_identical(monkeypatch):
    fake, calls = _sequenced_fix_loop([PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)

    result = fix_loop_escalating(TARGET, INSTRUCTION, TEST_CMD, max_iters=3)

    assert result.success == PASS_RESULT.success
    assert result.attempts == PASS_RESULT.attempts
    assert result.final_output == PASS_RESULT.final_output
    assert len(calls) == 1


# --- (c) never worse than primary-only -------------------------------------------------------

def test_both_fail_returns_primary_never_raises(monkeypatch):
    fake, calls = _sequenced_fix_loop([FAIL_RESULT, FAIL_RESULT_2])
    monkeypatch.setattr(cl, "fix_loop", fake)
    swap_fn, swap_calls = _swap_recorder()

    result = fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=3,
        fallback_llm=object(), swap_fn=swap_fn,
        fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result.success is False
    assert result.escalated is True     # a fallback attempt WAS made
    assert result.model == "primary"    # but neither passed -> prefer the primary result
    assert result.final_output == FAIL_RESULT.final_output
    assert swap_calls == ["qwen2.5-coder-7b", "gemma-4-e2b"]


def test_no_swap_fn_still_escalates_without_swapping(monkeypatch):
    """swap_fn is optional -- omitting it still escalates to the fallback fix_loop call, it
    just never performs a serving swap."""
    fake, calls = _sequenced_fix_loop([FAIL_RESULT, PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)

    result = fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=3,
        fallback_llm=object(), fallback_model_id="qwen2.5-coder-7b",
        primary_model_id="gemma-4-e2b")

    assert result.success is True
    assert result.escalated is True
    assert result.model == "fallback"
    assert len(calls) == 2


def test_swap_fn_raises_falls_back_to_primary_gracefully(monkeypatch):
    fake, calls = _sequenced_fix_loop([FAIL_RESULT, PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)

    def _raising_swap(model_id: str) -> None:
        raise RuntimeError("jetson unreachable")

    result = fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=3,
        fallback_llm=object(), swap_fn=_raising_swap,
        fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result.success is False
    assert result.escalated is False
    assert result.model == "primary"
    assert result.final_output == FAIL_RESULT.final_output
    assert len(calls) == 1   # the fallback fix_loop call never even ran


def test_fallback_fix_loop_raises_falls_back_to_primary_gracefully(monkeypatch):
    call_n = {"n": 0}

    def _raising_fake(target, instruction, test_cmd, *, max_iters=4, cwd=None,
                       editor_agent="rewriter_agent.py", verbose=True, keep_partial=False):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return FAIL_RESULT
        raise RuntimeError("fallback model crashed mid-repair")

    monkeypatch.setattr(cl, "fix_loop", _raising_fake)
    swap_fn, swap_calls = _swap_recorder()

    result = fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=3,
        fallback_llm=object(), swap_fn=swap_fn,
        fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result.success is False
    assert result.escalated is False
    assert result.model == "primary"
    assert result.final_output == FAIL_RESULT.final_output
    # the swap TO the fallback happened (that's how we got to the crash), and the restore
    # in the `finally` block still ran, restoring the primary despite the exception
    assert swap_calls == ["qwen2.5-coder-7b", "gemma-4-e2b"]


# --- (d) restore-to-gemma is invoked ----------------------------------------------------------

def test_restore_invoked_on_success(monkeypatch):
    fake, calls = _sequenced_fix_loop([FAIL_RESULT, PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)
    swap_fn, swap_calls = _swap_recorder()

    fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=3,
        fallback_llm=object(), swap_fn=swap_fn,
        fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert "gemma-4-e2b" in swap_calls
    # restore is the LAST call -- never left serving on the 7B
    assert swap_calls[-1] == "gemma-4-e2b"


def test_restore_skipped_when_never_swapped_to_fallback(monkeypatch):
    """No escalation ever triggered (primary passed) -> no swap calls at all, restore included
    -- there is nothing to restore FROM."""
    fake, calls = _sequenced_fix_loop([PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)
    swap_fn, swap_calls = _swap_recorder()

    fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=3,
        fallback_llm=object(), swap_fn=swap_fn,
        fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert swap_calls == []


# --- metadata shape + argument threading are consistent across every path -------------------

def test_metadata_fields_always_present(monkeypatch):
    fake, calls = _sequenced_fix_loop([PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)

    result = fix_loop_escalating(TARGET, INSTRUCTION, TEST_CMD)

    assert hasattr(result, "escalated")
    assert hasattr(result, "model")
    assert isinstance(result, LoopResult)


def test_kwargs_threaded_identically_into_both_attempts(monkeypatch):
    fake, calls = _sequenced_fix_loop([FAIL_RESULT, PASS_RESULT])
    monkeypatch.setattr(cl, "fix_loop", fake)
    swap_fn, _ = _swap_recorder()

    fix_loop_escalating(
        TARGET, INSTRUCTION, TEST_CMD, max_iters=5, cwd="/some/dir",
        editor_agent="editor_agent.py", verbose=False, keep_partial=True,
        fallback_llm=object(), swap_fn=swap_fn,
        fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert len(calls) == 2
    for c in calls:
        assert c["max_iters"] == 5
        assert c["cwd"] == "/some/dir"
        assert c["editor_agent"] == "editor_agent.py"
        assert c["verbose"] is False
        assert c["keep_partial"] is True
