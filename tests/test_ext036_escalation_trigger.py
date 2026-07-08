"""EXT-036 REQ-13 (task #142): the CREATION-path escalation trigger must fire on NOT-DONE, not
just NOT-SHIPPED.

MEASURED BUG (live Jetson, 2026-07-07): `build_system_escalating` escalated gemma -> the
Qwen2.5-Coder-7B fallback only when the primary FAILED TO SHIP (`not shipped`). A hard LRU build
measured `shipped=True, done=False` (gemma shipped a BROKEN system that failed the deterministic
acceptance floor) and escalation did NOT fire, because "shipped" alone does not mean the system
actually works. Since the primary almost always ships *something*, the 7B was barely ever
invoked. The meaningful success signal is `done` (passed acceptance), not `shipped`.

OFFLINE -- no live model, no network, no Jetson. `build_system` is MONKEYPATCHED at the module
level (`harness.system_builder.build_system`) with canned callables keyed by which `llm`
sentinel object they were called with, mirroring `test_ext036_escalate.py`'s proven pattern.
"""

from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.system_builder as sb
from harness.system_builder import build_system_escalating

SPEC = "A tiny LRU-cache system with a CLI (get/put/evict)."

PRIMARY_LLM = object()     # sentinel: the default (gemma) llm
FALLBACK_LLM = object()    # sentinel: the stronger (qwen-7b) llm

SHIPPED_DONE = {"modules": {"a.py": "code"}, "shipped": True, "done": True,
                "unmet": [], "plan": {"entrypoint": "a.py"}, "note": "DONE"}
# The measured bug shape: gemma SHIPPED a broken system -- shipped=True but done=False.
SHIPPED_NOT_DONE_1UNMET = {"modules": {"a.py": "code"}, "shipped": True, "done": False,
                           "unmet": ["evict wrong order"], "plan": {"entrypoint": "a.py"},
                           "note": "NOT DONE -- failed acceptance floor"}
SHIPPED_NOT_DONE_2UNMET = {"modules": {"a.py": "code", "b.py": "code"}, "shipped": True,
                           "done": False, "unmet": ["evict wrong order", "get missing key"],
                           "plan": {"entrypoint": "a.py"}, "note": "NOT DONE -- worse"}


def _fake_build_system(results: dict):
    """Returns a `build_system`-shaped callable keyed by `id(llm)` -> canned result dict.

    Accepts (and ignores) an optional `runtime` kwarg -- EXT-037 REQ-11 threads `runtime`
    straight through `build_system_escalating`'s own internal `build_system(...)` calls, so this
    fake must accept it like the real function does."""
    def _fake(spec, root, *, llm=None, runtime=None):
        return dict(results[id(llm)])
    return _fake


def _swap_recorder():
    calls: list[str] = []

    def _swap(model_id: str) -> None:
        calls.append(model_id)
    return _swap, calls


# --- (a) primary SHIPPED but NOT DONE -> escalation FIRES (was the measured bug) -----------

def test_shipped_but_not_done_escalates_to_fallback(tmp_path, monkeypatch):
    """The measured Jetson bug: primary ships a BROKEN system (shipped=True, done=False). Under
    the old `not shipped` trigger this would NOT have escalated -- it must now escalate and the
    done fallback must win."""
    monkeypatch.setattr(sb, "build_system", _fake_build_system({
        id(PRIMARY_LLM): SHIPPED_NOT_DONE_1UNMET,
        id(FALLBACK_LLM): SHIPPED_DONE,
    }))
    swap_fn, calls = _swap_recorder()

    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=FALLBACK_LLM,
        swap_fn=swap_fn, fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result["escalated"] is True
    assert result["model"] == "fallback"
    assert result["done"] is True
    assert result["shipped"] is True
    # swapped TO the fallback first, then back to the primary (restore)
    assert calls == ["qwen2.5-coder-7b", "gemma-4-e2b"]


# --- (b) primary DONE -> NO escalation (unchanged common case) -----------------------------

def test_primary_done_no_escalation(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "build_system",
                         _fake_build_system({id(PRIMARY_LLM): SHIPPED_DONE}))
    swap_fn, calls = _swap_recorder()
    fallback_called = {"n": 0}

    class _NeverCalledLlm:
        def complete(self, *a, **k):
            fallback_called["n"] += 1
            raise AssertionError("fallback_llm must never be invoked when primary is done")

    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=_NeverCalledLlm(),
        swap_fn=swap_fn, fallback_model_id="qwen2.5-coder-7b", primary_model_id="gemma-4-e2b")

    assert result["done"] is True
    assert result["escalated"] is False
    assert result["model"] == "primary"
    assert fallback_called["n"] == 0
    assert calls == []   # swap_fn never called


# --- (c) fallback_llm=None -> no-op, byte-identical primary result, even when not-done -----

def test_no_fallback_llm_configured_is_noop_even_when_primary_not_done(tmp_path, monkeypatch):
    """A primary that shipped-but-not-done must still be a pure no-op (escalated=False, primary
    result unchanged) when no fallback is configured -- never pay for/attempt a fallback that
    was not wired in."""
    monkeypatch.setattr(sb, "build_system",
                         _fake_build_system({id(PRIMARY_LLM): SHIPPED_NOT_DONE_1UNMET}))
    result = build_system_escalating(SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM)

    assert result["done"] is False
    assert result["shipped"] is True
    assert result["escalated"] is False
    assert result["model"] == "primary"
    # byte-identical to the primary result plus only the two metadata keys
    expected = dict(SHIPPED_NOT_DONE_1UNMET)
    expected["escalated"] = False
    expected["model"] = "primary"
    assert result == expected


# --- (d) never worse than primary: fallback also not-done but LESS done -> keep primary ----

def test_fallback_also_not_done_but_worse_keeps_primary(tmp_path, monkeypatch):
    """Both primary and fallback fail acceptance, but the primary has fewer unmet requirements
    (i.e. is "more done") -- the wrapper must never regress below the primary result."""
    monkeypatch.setattr(sb, "build_system", _fake_build_system({
        id(PRIMARY_LLM): SHIPPED_NOT_DONE_1UNMET,   # 1 unmet requirement
        id(FALLBACK_LLM): SHIPPED_NOT_DONE_2UNMET,  # 2 unmet requirements -- strictly worse
    }))
    result = build_system_escalating(
        SPEC, tmp_path / "built", primary_llm=PRIMARY_LLM, fallback_llm=FALLBACK_LLM)

    # escalation was attempted (primary was not done)...
    assert result["escalated"] is True
    # ...but the winner is still the primary, since the fallback was worse, not better.
    assert result["model"] == "primary"
    assert result["unmet"] == SHIPPED_NOT_DONE_1UNMET["unmet"]
