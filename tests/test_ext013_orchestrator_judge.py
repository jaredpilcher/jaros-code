"""Deterministic unit tests for EXT-013 / REQ-3 — OrchestratorJudgeBoundary.

All tests use a FAKE/stub LLM — no model, no Jetson, no clone.

Coverage:
  (a) Valid call -> emits exactly one ``orchestrate.next`` Decision with an
      action from the constrained set {code, gherkin, repair, done}.
  (b) Failure feedback causes the agent to pick a REVISION action (not done).
  (c) Unrecognised model output falls back to the safe default ``"code"``.
  (d) Past the step budget the agent emits ``"done"`` (no model call fired).
"""

from __future__ import annotations

# #EXT-013-REQ-3 Start

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or from the tests/ directory
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_AGENTS_DIR = _REPO_ROOT / ".jaros-data" / "agents"

# ---------------------------------------------------------------------------
# Structural sanity — the agent file must parse as valid Python
# ---------------------------------------------------------------------------

def test_agent_file_parses():
    """ast.parse must succeed on orchestrator_judge_agent.py."""
    src = (_AGENTS_DIR / "orchestrator_judge_agent.py").read_text(encoding="utf-8")
    ast.parse(src)   # raises SyntaxError if broken


# ---------------------------------------------------------------------------
# Fake / stub LLM helpers
# ---------------------------------------------------------------------------

class _FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLlm:
    """Stub LLM that always returns a predetermined text response.

    We also track whether `complete` was called, so budget-guard tests can
    assert the model was NOT invoked.
    """

    def __init__(self, response: str = "code") -> None:
        self._response = response
        self.call_count = 0

    def complete(self, request):  # noqa: ANN001
        self.call_count += 1
        return _FakeCompletion(self._response)


# ---------------------------------------------------------------------------
# Import the agent under test (load from file so we don't need a package
# install — matches how other tests in this project load agents)
# ---------------------------------------------------------------------------

def _load_agent():
    agent_path = _AGENTS_DIR / "orchestrator_judge_agent.py"
    spec = importlib.util.spec_from_file_location("orchestrator_judge_agent", agent_path)
    mod = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
    spec.loader.exec_module(mod)                  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# (a) Valid call emits one ``orchestrate.next`` Decision in the constrained set
# ---------------------------------------------------------------------------

def test_valid_call_emits_orchestrate_next_decision():
    """Given a minimal context the agent must emit exactly one orchestrate.next Decision."""
    mod = _load_agent()
    llm = _FakeLlm("code")
    agent = mod.build(llm)

    ctx = {
        "intent": "add caching to the function",
        "name": "cached_lookup",
        "step": 1,
        "feedback": "AssertionError: expected 42 got None",
    }
    decisions = agent.decide(ctx)

    assert len(decisions) == 1, "must emit exactly one Decision"
    d = decisions[0]
    assert d.type == "orchestrate.next", f"wrong type: {d.type}"
    assert d.source == mod.NAME
    assert "action" in d.payload, "payload must contain 'action'"
    assert "reason" in d.payload, "payload must contain 'reason'"
    assert d.payload["action"] in mod._ACTIONS, (
        f"action {d.payload['action']!r} not in constrained set {mod._ACTIONS}")


def test_action_is_always_in_constrained_set():
    """Whatever the LLM says, the action in the Decision must be from the fixed set."""
    mod = _load_agent()
    for raw_response in ("code\n", " GHERKIN ", "repair it now", "done.", "code"):
        llm = _FakeLlm(raw_response)
        agent = mod.build(llm)
        ctx = {"intent": "fix it", "name": "fn", "step": 0, "feedback": "fail"}
        decisions = agent.decide(ctx)
        action = decisions[0].payload["action"]
        assert action in mod._ACTIONS, (
            f"response {raw_response!r} produced out-of-set action {action!r}")


# ---------------------------------------------------------------------------
# (b) Given failure feedback, the agent picks a REVISION action (not "done")
# ---------------------------------------------------------------------------

def test_failure_feedback_picks_revision_action():
    """When tests fail and model says 'code', action must be 'code' (a revision action)."""
    mod = _load_agent()
    llm = _FakeLlm("code")
    agent = mod.build(llm)

    ctx = {
        "intent": "sort descending",
        "name": "sort_desc",
        "step": 0,
        "feedback": "AssertionError: list not sorted descending",
    }
    decisions = agent.decide(ctx)
    action = decisions[0].payload["action"]
    assert action != "done", "should pick a revision action, not 'done', when tests fail"
    assert action in {"code", "gherkin", "repair"}, (
        f"expected a revision action, got {action!r}")


def test_gherkin_response_maps_to_gherkin_action():
    """Model output containing 'gherkin' must map to action 'gherkin'."""
    mod = _load_agent()
    llm = _FakeLlm("gherkin")
    agent = mod.build(llm)
    ctx = {"intent": "change behavior", "name": "fn", "step": 1, "feedback": "spec wrong"}
    decisions = agent.decide(ctx)
    assert decisions[0].payload["action"] == "gherkin"


def test_repair_response_maps_to_repair_action():
    """Model output containing 'repair' must map to action 'repair'."""
    mod = _load_agent()
    llm = _FakeLlm("repair")
    agent = mod.build(llm)
    ctx = {"intent": "fix indentation", "name": "fn", "step": 1, "feedback": "SyntaxError"}
    decisions = agent.decide(ctx)
    assert decisions[0].payload["action"] == "repair"


# ---------------------------------------------------------------------------
# (c) Unrecognised model output falls back to the safe default "code"
# ---------------------------------------------------------------------------

def test_unrecognised_model_output_falls_back_to_default():
    """Output not containing any known action token must produce the safe default."""
    mod = _load_agent()
    for bad_response in ("hmm, I am not sure", "try again", "42", ""):
        llm = _FakeLlm(bad_response)
        agent = mod.build(llm)
        ctx = {"intent": "x", "name": "fn", "step": 0, "feedback": "fail"}
        decisions = agent.decide(ctx)
        action = decisions[0].payload["action"]
        assert action == mod._DEFAULT_ACTION, (
            f"bad response {bad_response!r} should fall back to {mod._DEFAULT_ACTION!r}, "
            f"got {action!r}")


# ---------------------------------------------------------------------------
# (d) Past the step budget the agent emits "done" without calling the model
# ---------------------------------------------------------------------------

def test_budget_exhausted_emits_done_no_model_call():
    """When step >= max_steps the agent must emit 'done' and NOT call the LLM."""
    mod = _load_agent()
    max_steps = 5
    llm = _FakeLlm("code")   # if called, this would return "code"
    agent = mod.build(llm, max_steps=max_steps)

    ctx = {
        "intent": "add feature",
        "name": "my_fn",
        "step": max_steps,   # exactly at budget
        "feedback": "still failing",
    }
    decisions = agent.decide(ctx)

    assert decisions[0].payload["action"] == "done", (
        "budget exhausted must produce action='done'")
    assert llm.call_count == 0, "model must NOT be called when budget is exhausted"


def test_budget_exhausted_one_over():
    """step = max_steps + 3 must also emit 'done' without model call."""
    mod = _load_agent()
    max_steps = 4
    llm = _FakeLlm("code")
    agent = mod.build(llm, max_steps=max_steps)

    ctx = {"intent": "x", "name": "fn", "step": max_steps + 3, "feedback": "fail"}
    decisions = agent.decide(ctx)

    assert decisions[0].payload["action"] == "done"
    assert llm.call_count == 0


def test_step_below_budget_calls_model():
    """Confirm model IS called when step < max_steps (complements the budget guard test)."""
    mod = _load_agent()
    max_steps = 8
    llm = _FakeLlm("code")
    agent = mod.build(llm, max_steps=max_steps)

    ctx = {"intent": "fix it", "name": "fn", "step": 0, "feedback": "fail"}
    agent.decide(ctx)

    assert llm.call_count == 1, "model must be called when step < max_steps"


# ---------------------------------------------------------------------------
# Structural: NAME constant and build() factory exist
# ---------------------------------------------------------------------------

def test_name_constant_and_build_factory_exist():
    """The module must expose a NAME string and a build() callable."""
    mod = _load_agent()
    assert isinstance(mod.NAME, str) and mod.NAME, "NAME must be a non-empty string"
    assert callable(mod.build), "build must be callable"


def test_build_returns_agent_with_decide():
    """build(llm) must return an object with a decide() method."""
    mod = _load_agent()
    agent = mod.build(_FakeLlm())
    assert hasattr(agent, "decide") and callable(agent.decide)

# #EXT-013-REQ-3 End


# ---------------------------------------------------------------------------
# EXT-013 / REQ-8 — richer-observe: the judge reasons over the actual code
# ---------------------------------------------------------------------------
# #EXT-013-REQ-8 Start

class _RecordingLlm:
    """Stub LLM that records the LlmRequest it receives (for prompt assertions)."""

    def __init__(self, response: str = "code") -> None:
        self._response = response
        self.call_count = 0
        self.last_request = None

    def complete(self, request):  # noqa: ANN001
        self.call_count += 1
        self.last_request = request
        return _FakeCompletion(self._response)


def test_with_code_the_code_text_appears_in_the_prompt():
    """(a) When ctx['code'] is present the code text must appear in the recorded prompt."""
    mod = _load_agent()
    llm = _RecordingLlm("repair")
    agent = mod.build(llm)

    code_text = "def cached_lookup(x):\n    return x + 1  # UNIQUE_MARKER_42"
    ctx = {
        "intent": "add caching to the function",
        "name": "cached_lookup",
        "step": 1,
        "feedback": "IndentationError: unexpected indent",
        "code": code_text,
    }
    decisions = agent.decide(ctx)

    assert llm.last_request is not None
    assert "UNIQUE_MARKER_42" in llm.last_request.prompt, (
        "the actual current code must appear in the richer prompt")
    assert decisions[0].payload["action"] == "repair"


def test_without_code_the_prompt_equals_the_existing_template_backward_compat():
    """(b) WITHOUT ctx['code'] the recorded prompt must equal the ORIGINAL _PROMPT output
    exactly — byte-for-byte backward-compat with the proven solve loop."""
    mod = _load_agent()
    llm = _RecordingLlm("code")
    agent = mod.build(llm)

    ctx = {
        "intent": "sort descending",
        "name": "sort_desc",
        "step": 0,
        "feedback": "AssertionError: list not sorted descending",
    }
    agent.decide(ctx)

    menu = "\n".join(f"  {a} = {d}" for a, d in mod._REV_DESCRIPTIONS.items())
    expected_prompt = mod._PROMPT.format(
        name=ctx["name"], intent=ctx["intent"], feedback=ctx["feedback"], menu=menu)

    assert llm.last_request.prompt == expected_prompt, (
        "prompt without 'code' in ctx must be byte-for-byte identical to the "
        "existing _PROMPT template output (backward-compat)"
    )


def test_empty_string_code_also_uses_existing_template():
    """An explicit empty-string ctx['code'] must be treated the same as absent (backward-compat)."""
    mod = _load_agent()
    llm = _RecordingLlm("code")
    agent = mod.build(llm)

    ctx = {
        "intent": "sort descending",
        "name": "sort_desc",
        "step": 0,
        "feedback": "AssertionError: list not sorted descending",
        "code": "",
    }
    agent.decide(ctx)

    menu = "\n".join(f"  {a} = {d}" for a, d in mod._REV_DESCRIPTIONS.items())
    expected_prompt = mod._PROMPT.format(
        name=ctx["name"], intent=ctx["intent"], feedback=ctx["feedback"], menu=menu)

    assert llm.last_request.prompt == expected_prompt


def test_code_is_truncated_to_safe_budget():
    """The code text embedded in the richer prompt must be truncated (no unbounded prompt growth)."""
    mod = _load_agent()
    llm = _RecordingLlm("code")
    agent = mod.build(llm)

    long_code = "x = 1\n" * 1000  # far larger than the safe budget
    ctx = {
        "intent": "fix it",
        "name": "fn",
        "step": 0,
        "feedback": "fail",
        "code": long_code,
    }
    agent.decide(ctx)

    assert len(llm.last_request.prompt) < len(long_code), (
        "the embedded code must be truncated, not dumped in full")


def test_action_selection_unchanged_with_richer_observe():
    """(c) Action-selection behavior is unchanged when code is supplied — same constrained
    set, same degeneracy-guard fallback."""
    mod = _load_agent()

    for raw_response, expected in (
        ("code\n", "code"),
        (" GHERKIN ", "gherkin"),
        ("repair it now", "repair"),
        ("done.", "done"),
        ("gibberish nonsense", mod._DEFAULT_ACTION),
    ):
        llm = _RecordingLlm(raw_response)
        agent = mod.build(llm)
        ctx = {
            "intent": "fix it", "name": "fn", "step": 0, "feedback": "fail",
            "code": "def fn():\n    pass",
        }
        decisions = agent.decide(ctx)
        action = decisions[0].payload["action"]
        assert action == expected, (
            f"response {raw_response!r} with code present produced {action!r}, "
            f"expected {expected!r}")
        assert action in mod._ACTIONS


def test_step_budget_guard_unchanged_with_richer_observe():
    """(c) The step-budget guard still short-circuits (no model call) even when code is present."""
    mod = _load_agent()
    max_steps = 3
    llm = _RecordingLlm("code")
    agent = mod.build(llm, max_steps=max_steps)

    ctx = {
        "intent": "fix it", "name": "fn", "step": max_steps, "feedback": "fail",
        "code": "def fn():\n    pass",
    }
    decisions = agent.decide(ctx)

    assert decisions[0].payload["action"] == "done"
    assert llm.call_count == 0, "model must NOT be called when budget is exhausted, even with code present"

# #EXT-013-REQ-8 End
