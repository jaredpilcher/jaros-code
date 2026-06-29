"""OFFLINE live-path tests for the real jetson-fn implementations.

Root cause closed: existing offline tests inject the ENTIRE propose_fn /
draft_fn / solve_fn as mocks, so the REAL implementations (prompt-building,
variable references, parsing) are NEVER exercised.  This lets NameErrors,
undefined-variable refs, and bad fence-stripping ship silently — confirmed by
three live-path bugs: passk dropped-imports, qwen dropped-imports, and the
EXT-030 propose_fn NameError that crashed on every task.

Fix: call the REAL functions built by _make_jetson_fns, injecting ONLY a mock
llm_fn (and a no-op swap_fn) so the network call is stubbed while all real
prompt-building, variable-reference, and parsing code runs.

Coverage
--------
- EXT-030 REQ-2: experiment_solve._make_jetson_fns -> propose_fn / solve_fn
- EXT-029 REQ-2: collaborative_solve._make_jetson_fns -> critique_fn
  (draft_fn / revise_fn use qwen_code directly, not llm_fn; monkeypatched at
  the harness.qwen_adapt.qwen_code seam — the lowest injectable point)

All tests are OFFLINE: no Jetson, no network, no Docker.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# #EXT-030-REQ-2 Start
from harness.experiment_solve import _make_jetson_fns as exp_make_fns, E1, E2, E3
# #EXT-030-REQ-2 End

# #EXT-029-REQ-2 Start
from harness.collaborative_solve import _make_jetson_fns as collab_make_fns
# #EXT-029-REQ-2 End

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

REALISTIC_PROBLEM = {
    "subject": "Fix sum_list to correctly accumulate list elements",
    "name": "sum_list",
    "parent_src": "def sum_list(lst):\n    return 0\n",
    "context": "# utilities.py\n\ndef helper(): pass\n",
}

COLLAB_PROBLEM = {
    "subject": "Fix sum_list to accumulate list elements",
    "name": "sum_list",
    "context": "# utilities.py\n",
}

CANNED_CODE = "def sum_list(lst):\n    return sum(lst)\n"
CANNED_CRITIQUE = "The function returns 0 instead of computing the actual sum."

_NOOP_SWAP = lambda m: None  # noqa: E731


# ===========================================================================
# EXT-030: experiment_solve — REAL propose_fn / solve_fn via _make_jetson_fns
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 1: propose_fn with empty understanding (the exact call that triggered
#          the NameError before the fix — NameErrors surface here, not in
#          the existing mocked tests)
# ---------------------------------------------------------------------------

# #EXT-030-REQ-2 Start
def test_propose_fn_empty_understanding_no_error():
    """REAL propose_fn must not raise with empty understanding.

    This test reproduces the exact call shape that previously triggered a
    NameError (`fn_name` referenced before assignment).  The existing mocked
    tests cannot catch this class of bug because they never run the real code.
    """
    mock_llm = lambda prompt: (  # noqa: E731
        '{"type": "E2", "params": {"fn_name": "sum_list", "args_repr": "([1, 2, 3],)"}}'
    )
    propose_fn, solve_fn = exp_make_fns(
        "qwen2.5-coder-3b", "http://x",
        llm_fn=mock_llm, swap_fn=_NOOP_SWAP,
    )
    decision = propose_fn(REALISTIC_PROBLEM, [])
    assert isinstance(decision, dict), "propose_fn must return a dict"
    assert decision.get("type") in (E1, E2, E3), (
        f"type must be one of E1/E2/E3, got {decision.get('type')!r}"
    )
    assert isinstance(decision.get("params"), dict), "params must be a dict"


# ---------------------------------------------------------------------------
# Test 2: propose_fn with non-empty understanding — exercises the
#          observations-block code path in the real prompt builder
# ---------------------------------------------------------------------------

def test_propose_fn_nonempty_understanding_exercises_obs_block():
    """REAL propose_fn must handle accumulated observations without error.

    The observations-block branch (building obs_block from understanding list)
    is only exercised when understanding is non-empty.  This test covers it.
    """
    mock_llm = lambda prompt: '{"type": "E3", "params": {"fn_name": "helper"}}'  # noqa: E731
    propose_fn, _ = exp_make_fns(
        "qwen2.5-coder-3b", "http://x",
        llm_fn=mock_llm, swap_fn=_NOOP_SWAP,
    )
    understanding = [
        {
            "experiment": {"type": "E1", "params": {}},
            "observation": "AssertionError: expected 6 got 0",
        },
    ]
    decision = propose_fn(REALISTIC_PROBLEM, understanding)
    assert decision.get("type") in (E1, E2, E3)
    assert isinstance(decision.get("params"), dict)


# ---------------------------------------------------------------------------
# Test 3: solve_fn with non-empty understanding — exercises the observations-
#          block + fence-stripping + def-search code paths
# ---------------------------------------------------------------------------

def test_solve_fn_with_understanding_returns_str():
    """REAL solve_fn must return a string and not raise with non-empty understanding."""
    mock_llm = lambda prompt: "```python\ndef sum_list(lst):\n    return sum(lst)\n```"  # noqa: E731
    _, solve_fn = exp_make_fns(
        "qwen2.5-coder-3b", "http://x",
        llm_fn=mock_llm, swap_fn=_NOOP_SWAP,
    )
    understanding = [
        {
            "experiment": {"type": "E1", "params": {}},
            "observation": "AssertionError: expected 6 got 0",
        },
        {
            "experiment": {
                "type": "E2",
                "params": {"fn_name": "sum_list", "args_repr": "([1, 2],)"},
            },
            "observation": "RESULT: 0",
        },
    ]
    code = solve_fn(REALISTIC_PROBLEM, understanding)
    assert isinstance(code, str), "solve_fn must return a string"
    # Fence-stripping should have removed the ```python wrapper
    assert "```" not in code, f"solve_fn must strip markdown fences; got: {code!r}"


# ---------------------------------------------------------------------------
# Test 4: propose_fn — parametrized defensive-parsing suite
#
#   Valid JSON E1/E2/E3    -> parsed and returned verbatim
#   Malformed JSON         -> falls back to E1 (never raises)
#   Empty string           -> falls back to E1 (never raises)
#   Unknown type field E9  -> falls back to E1 (never raises)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw_output", [
    # Valid JSON — all three experiment types
    '{"type": "E1", "params": {}}',
    '{"type": "E2", "params": {"fn_name": "sum_list", "args_repr": "([1, 2],)"}}',
    '{"type": "E3", "params": {"fn_name": "helper"}}',
    # Defensive fallback cases — must default to E1, never raise
    "not json at all",
    "",
    '{"type": "E9", "params": {}}',
])
def test_propose_fn_defensive_parsing_never_raises(raw_output):
    """REAL propose_fn must always return a valid bounded decision and never raise.

    Locks in the defensive-parsing contract: on ANY raw LLM output (valid JSON,
    malformed, empty, unknown type) propose_fn must return a dict with type in
    (E1, E2, E3) and a params dict.  This parametrize suite would have caught
    an ``except``-free hard crash on bad JSON.
    """
    mock_llm = lambda prompt: raw_output  # noqa: E731
    propose_fn, _ = exp_make_fns(
        "qwen2.5-coder-3b", "http://x",
        llm_fn=mock_llm, swap_fn=_NOOP_SWAP,
    )
    decision = propose_fn(REALISTIC_PROBLEM, [])

    assert isinstance(decision, dict), (
        f"propose_fn must return a dict for output {raw_output!r}"
    )
    assert decision.get("type") in (E1, E2, E3), (
        f"type must be E1/E2/E3, got {decision.get('type')!r} for output {raw_output!r}"
    )
    assert isinstance(decision.get("params"), dict), (
        f"params must be a dict, got {type(decision.get('params'))!r} "
        f"for output {raw_output!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: propose_fn malformed JSON -> E1 fallback (explicit assertion)
# ---------------------------------------------------------------------------

def test_propose_fn_malformed_json_falls_back_to_e1():
    """Malformed JSON with no E2/E3 keywords -> E1 fallback (never raises)."""
    mock_llm = lambda prompt: "GARBAGE NOT JSON"  # noqa: E731
    propose_fn, _ = exp_make_fns(
        "qwen2.5-coder-3b", "http://x",
        llm_fn=mock_llm, swap_fn=_NOOP_SWAP,
    )
    decision = propose_fn(REALISTIC_PROBLEM, [])
    assert decision["type"] == E1, (
        f"expected E1 fallback on malformed JSON, got {decision['type']!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: propose_fn keyword-scan fallback — E2 keyword triggers E2 path
# ---------------------------------------------------------------------------

def test_propose_fn_keyword_scan_e2():
    """When JSON fails but 'E2' appears in output, keyword scan returns E2."""
    raw = 'No JSON here but E2 is the choice. "fn_name": "sum_list".'
    mock_llm = lambda prompt: raw  # noqa: E731
    propose_fn, _ = exp_make_fns(
        "qwen2.5-coder-3b", "http://x",
        llm_fn=mock_llm, swap_fn=_NOOP_SWAP,
    )
    decision = propose_fn(REALISTIC_PROBLEM, [])
    assert decision["type"] == E2, (
        f"expected E2 from keyword scan, got {decision['type']!r}"
    )


# ---------------------------------------------------------------------------
# Test 7: propose_fn keyword-scan fallback — E3 keyword triggers E3 path
# ---------------------------------------------------------------------------

def test_propose_fn_keyword_scan_e3():
    """When JSON fails but 'E3' appears in output, keyword scan returns E3."""
    raw = 'No JSON. E3 is what I want. "fn_name": "helper".'
    mock_llm = lambda prompt: raw  # noqa: E731
    propose_fn, _ = exp_make_fns(
        "qwen2.5-coder-3b", "http://x",
        llm_fn=mock_llm, swap_fn=_NOOP_SWAP,
    )
    decision = propose_fn(REALISTIC_PROBLEM, [])
    assert decision["type"] == E3, (
        f"expected E3 from keyword scan, got {decision['type']!r}"
    )

# #EXT-030-REQ-2 End


# ===========================================================================
# EXT-029: collaborative_solve — REAL critique_fn / draft_fn / revise_fn
#           via _make_jetson_fns
#
# NOTE: critique_fn routes through _get_llm_text which checks llm_fn first ->
#       injectable via llm_fn parameter.
#       draft_fn and revise_fn call harness.qwen_adapt.qwen_code directly (not
#       through llm_fn) -> monkeypatched at harness.qwen_adapt.qwen_code, the
#       lowest injectable seam available without modifying production code.
# ===========================================================================

# #EXT-029-REQ-2 Start

# ---------------------------------------------------------------------------
# Test 8: critique_fn — exercises the real prompt builder + llm_fn injection
# ---------------------------------------------------------------------------

def test_critique_fn_real_prompt_building():
    """REAL critique_fn must build its prompt and return the llm_fn result.

    critique_fn goes through _get_llm_text which checks llm_fn first, so
    llm_fn injection works here.  The test confirms the REAL prompt-builder
    (_build_critique_prompt) runs and passes key fields to the mock.
    """
    received_prompts: list[str] = []

    def mock_llm(prompt: str) -> str:
        received_prompts.append(prompt)
        return CANNED_CRITIQUE

    _, critique_fn, _ = collab_make_fns(
        "qwen2.5-coder-3b", "gemma-4-e2b", "qwen2.5-coder-3b",
        "http://x",
        llm_fn=mock_llm,
        swap_fn=_NOOP_SWAP,
    )

    result = critique_fn(COLLAB_PROBLEM, CANNED_CODE, {"passed": False})

    assert isinstance(result, str), "critique_fn must return a string"
    assert result == CANNED_CRITIQUE, "critique_fn must return exactly what llm_fn returned"
    assert received_prompts, "llm_fn must have been called (prompt-building ran)"
    # The real prompt builder embeds the function name
    assert "sum_list" in received_prompts[0], (
        "REAL prompt builder must embed the function name; "
        f"prompt does not contain 'sum_list': {received_prompts[0][:200]!r}"
    )
    # The real prompt builder embeds the failing code
    assert CANNED_CODE in received_prompts[0], (
        "REAL prompt builder must embed the failing code in the prompt"
    )


# ---------------------------------------------------------------------------
# Test 9: draft_fn — monkeypatched at qwen_code seam
# ---------------------------------------------------------------------------

def test_draft_fn_real_path(monkeypatch):
    """REAL draft_fn must call qwen_code with correct args without error.

    draft_fn delegates directly to harness.qwen_adapt.qwen_code (not through
    llm_fn), so monkeypatch.setattr on harness.qwen_adapt.qwen_code is the
    injection seam.  This catches undefined-variable refs and wrong arg ordering
    in the real draft_fn body.
    """
    import harness.qwen_adapt as qa

    calls: list[tuple] = []

    def mock_qwen_code(task_or_spec: str, name: str, context: str = "") -> str:
        calls.append((task_or_spec, name, context))
        return CANNED_CODE

    monkeypatch.setattr(qa, "qwen_code", mock_qwen_code)

    draft_fn, _, _ = collab_make_fns(
        "qwen2.5-coder-3b", "gemma-4-e2b", "qwen2.5-coder-3b",
        "http://x",
        llm_fn=lambda p: CANNED_CRITIQUE,
        swap_fn=_NOOP_SWAP,
    )

    result = draft_fn(COLLAB_PROBLEM)

    assert isinstance(result, str), "draft_fn must return a string"
    assert len(calls) == 1, (
        f"draft_fn must call qwen_code exactly once, called {len(calls)} times"
    )
    assert calls[0][1] == "sum_list", (
        f"draft_fn must pass function name as 2nd arg to qwen_code, "
        f"got {calls[0][1]!r}"
    )


# ---------------------------------------------------------------------------
# Test 10: revise_fn — monkeypatched at qwen_code seam; critique embedded in ctx
# ---------------------------------------------------------------------------

def test_revise_fn_embeds_critique_in_context(monkeypatch):
    """REAL revise_fn must embed the critique in the context passed to qwen_code.

    revise_fn also delegates to qwen_code directly.  The test additionally
    confirms that the critique is embedded in the rich_context argument —
    catching bugs where the critique gets dropped or the variable order is wrong.
    """
    import harness.qwen_adapt as qa

    calls: list[tuple] = []

    def mock_qwen_code(task_or_spec: str, name: str, context: str = "") -> str:
        calls.append((task_or_spec, name, context))
        return CANNED_CODE

    monkeypatch.setattr(qa, "qwen_code", mock_qwen_code)

    _, _, revise_fn = collab_make_fns(
        "qwen2.5-coder-3b", "gemma-4-e2b", "qwen2.5-coder-3b",
        "http://x",
        llm_fn=lambda p: CANNED_CRITIQUE,
        swap_fn=_NOOP_SWAP,
    )

    result = revise_fn(COLLAB_PROBLEM, CANNED_CODE, CANNED_CRITIQUE)

    assert isinstance(result, str), "revise_fn must return a string"
    assert len(calls) == 1, (
        f"revise_fn must call qwen_code exactly once, called {len(calls)} times"
    )
    ctx_passed = calls[0][2]  # 3rd arg = context
    assert CANNED_CRITIQUE in ctx_passed, (
        "REAL revise_fn must embed the critique text in the context passed to "
        f"qwen_code.  ctx_passed: {ctx_passed[:300]!r}"
    )
    # Confirm the critique is prefixed (not just appended without marker)
    assert "CRITIQUE" in ctx_passed.upper(), (
        "revise_fn must mark the critique block with a 'CRITIQUE' header in context"
    )

# #EXT-029-REQ-2 End
