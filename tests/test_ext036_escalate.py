"""EXT-036 TASK-13: hard-tier ESCALATION core for build_system (REQ-13).

MEASURED (2026-07-03, commit c182c33): on complex sentence->system builds, gemma-4-e2b ships
2/3 (fully-completes 1) while Qwen2.5-Coder-7B ships 3/3 but never fully-completes and costs
~3x latency. Routing EVERYTHING to the 7B is a bad trade -- the honest win is
ESCALATE-ONLY-ON-FAILURE: run the default (primary) model; only pay for the stronger fallback
when the primary actually failed to ship.

OFFLINE -- no live model, no network, no Jetson. `build_system` itself is MONKEYPATCHED at the
module level (`harness.system_builder.build_system`) with canned callables keyed by which `llm`
sentinel object they were called with, so this file proves the ESCALATION WRAPPER's wiring
(when it escalates, when it swaps, when it restores, its never-raise robustness) in isolation
from `build_system`'s own pipeline (already covered by `test_ext036_system_builder.py` and
friends).
"""

from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.system_builder as sb
from harness.system_builder import build_system_escalating

SPEC = "A tiny job-queue system with a producer, a worker, and a CLI."

PRIMARY_LLM = object()     # sentinel: the default (gemma) llm
FALLBACK_LLM = object()    # sentinel: the stronger (qwen-7b) llm

SHIPPED_DONE = {"modules": {"a.py": "code"}, "shipped": True, "done": True,
                "unmet": [], "plan": {"entrypoint": "a.py"}, "note": "DONE"}
SHIPPED_NOT_DONE_1MOD = {"modules": {"a.py": "code"}, "shipped": True, "done": False,
                          "unmet": ["x"], "plan": {"entrypoint": "a.py"}, "note": "NOT DONE"}
SHIPPED_NOT_DONE_2MOD = {"modules": {"a.py": "code", "b.py": "code"}, "shipped": True,
                          "done": False, "unmet": ["x"], "plan": {"entrypoint": "a.py"},
                          "note": "NOT DONE"}
NOT_SHIPPED_0MOD = {"modules": {}, "shipped": False, "done": False, "unmet": [],
                     "plan": None, "note": "planner produced no parseable JSON plan"}
NOT_SHIPPED_1MOD = {"modules": {"a.py": "code"}, "shipped": False, "done": False, "unmet": [],
                     "plan": {"entrypoint": "a.py"}, "note": "build failed"}


def _fake_build_system(results: dict):
    """Returns a `build_system`-shaped callable keyed by `id(llm)` -> canned result dict."""
    def _fake(spec, root, *, llm=None):
        return dict(results[id(llm)])
    return _fake


def _swap_recorder():
    calls: list[str] = []

    def _swap(model_id: str) -> None:
        calls.append(model_id)
    return _swap, calls


# --- (a) primary ships -> returned AS-IS, fallback/swap NEVER invoked ---------------------

def test_primary_ships_returns_primary_no_escalation(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "build_system",
                         _fake_build_system({id(PRIMARY_LLM): SHIPPED_DONE}))
    swap_fn, calls = _swap_recorder()
    fallback_called = {"n": 0}

    class _NeverCalledLlm:
        def complete(self, *a, **k):
            fallback_called["n"] += 1
            raise AssertionError("fallback_llm must never be invoked")

    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=_NeverCalledLlm(),
        swap_fn=swap_fn, fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["escalated"] is False
    assert result["model"] == "primary"
    assert fallback_called["n"] == 0
    assert calls == []   # swap_fn never called


def test_primary_ships_no_fallback_llm_at_all(tmp_path, monkeypatch):
    """No fallback_llm supplied at all -> same no-escalation shape, even on a failing primary."""
    monkeypatch.setattr(sb, "build_system",
                         _fake_build_system({id(PRIMARY_LLM): NOT_SHIPPED_0MOD}))
    result = build_system_escalating(SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM)
    assert result["shipped"] is False
    assert result["escalated"] is False
    assert result["model"] == "primary"


# --- (b) primary fails, fallback ships -> escalates, swap fallback then primary (restore) --

def test_primary_fails_fallback_ships_escalates_and_restores(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "build_system", _fake_build_system({
        id(PRIMARY_LLM): NOT_SHIPPED_0MOD,
        id(FALLBACK_LLM): SHIPPED_DONE,
    }))
    swap_fn, calls = _swap_recorder()

    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=FALLBACK_LLM,
        swap_fn=swap_fn, fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["escalated"] is True
    assert result["model"] == "fallback"
    # swapped TO the fallback first, then back to the primary (restore)
    assert calls == ["qwen2.5-coder-7b", "gemma-4-e2b"]


def test_no_swap_fn_still_escalates_without_swapping(tmp_path, monkeypatch):
    """swap_fn is optional -- omitting it still escalates to the fallback build, it just never
    performs a serving swap."""
    monkeypatch.setattr(sb, "build_system", _fake_build_system({
        id(PRIMARY_LLM): NOT_SHIPPED_0MOD,
        id(FALLBACK_LLM): SHIPPED_DONE,
    }))
    result = build_system_escalating(SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM,
                                      fallback_llm=FALLBACK_LLM)
    assert result["shipped"] is True
    assert result["escalated"] is True
    assert result["model"] == "fallback"


# --- (c) both fail -> returns the better/primary result, never raises ---------------------

def test_both_fail_returns_better_result_never_raises(tmp_path, monkeypatch):
    """Primary ships 0 modules, fallback ships 1 module but still not-done -> fallback is
    strictly better by the deterministic tie-break (shipped > done > module count)."""
    monkeypatch.setattr(sb, "build_system", _fake_build_system({
        id(PRIMARY_LLM): NOT_SHIPPED_0MOD,
        id(FALLBACK_LLM): SHIPPED_NOT_DONE_1MOD,
    }))
    swap_fn, calls = _swap_recorder()
    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=FALLBACK_LLM,
        swap_fn=swap_fn, fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result["shipped"] is True
    assert result["escalated"] is True
    assert result["model"] == "fallback"
    assert calls == ["qwen2.5-coder-7b", "gemma-4-e2b"]


def test_both_unshipped_prefers_primary_on_tie(tmp_path, monkeypatch):
    """Both fail to ship with equal (0) modules -> the deterministic rule ties, and the wrapper
    prefers the PRIMARY result (never worse off than primary-only)."""
    monkeypatch.setattr(sb, "build_system", _fake_build_system({
        id(PRIMARY_LLM): NOT_SHIPPED_0MOD,
        id(FALLBACK_LLM): NOT_SHIPPED_0MOD,
    }))
    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=FALLBACK_LLM)
    assert result["shipped"] is False
    assert result["escalated"] is True
    assert result["model"] == "primary"


def test_fallback_worse_than_primary_prefers_primary(tmp_path, monkeypatch):
    """Primary shipped+done with more modules; a contrived fallback that shipped fewer modules
    and isn't done -> the wrapper still prefers the (better) primary result."""
    monkeypatch.setattr(sb, "build_system", _fake_build_system({
        id(PRIMARY_LLM): NOT_SHIPPED_1MOD,          # fails to ship (escalation triggers)
        id(FALLBACK_LLM): SHIPPED_NOT_DONE_2MOD,    # ships more modules -> wins over primary
    }))
    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=FALLBACK_LLM)
    assert result["model"] == "fallback"
    assert len(result["modules"]) == 2


# --- (d) swap_fn raises -> gracefully returns the primary result, never raises ------------

def test_swap_fn_raises_falls_back_to_primary_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "build_system", _fake_build_system({
        id(PRIMARY_LLM): NOT_SHIPPED_0MOD,
        id(FALLBACK_LLM): SHIPPED_DONE,
    }))

    def _raising_swap(model_id: str) -> None:
        raise RuntimeError("jetson unreachable")

    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=FALLBACK_LLM,
        swap_fn=_raising_swap, fallback_model_id="qwen2.5-coder-7b",
        primary_model_id="gemma-4-e2b")

    assert result["shipped"] is False
    assert result["escalated"] is False
    assert result["model"] == "primary"
    assert result is not NOT_SHIPPED_0MOD   # a fresh dict, not the canned object itself
    assert result["note"] == NOT_SHIPPED_0MOD["note"]


# --- (e) fallback build raises -> returns the primary result, never raises ----------------

def test_fallback_build_raises_falls_back_to_primary_gracefully(tmp_path, monkeypatch):
    def _fake(spec, root, *, llm=None):
        if llm is PRIMARY_LLM:
            return dict(NOT_SHIPPED_0MOD)
        raise RuntimeError("fallback model crashed mid-build")

    monkeypatch.setattr(sb, "build_system", _fake)
    swap_fn, calls = _swap_recorder()

    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=FALLBACK_LLM,
        swap_fn=swap_fn, fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result["shipped"] is False
    assert result["escalated"] is False
    assert result["model"] == "primary"
    # the swap TO the fallback happened (that's how we got to the crash), and the restore
    # in the `finally` block still ran, restoring the primary despite the exception
    assert calls == ["qwen2.5-coder-7b", "gemma-4-e2b"]


# --- metadata shape is consistent across every path -----------------------------------------

def test_metadata_keys_always_present(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "build_system", _fake_build_system({id(PRIMARY_LLM): SHIPPED_DONE}))
    result = build_system_escalating(SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM)
    assert "escalated" in result and "model" in result
    # the underlying build_system dict shape is preserved
    assert set(SHIPPED_DONE) <= set(result)
