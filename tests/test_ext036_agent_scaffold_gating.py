"""EXT-036 REQ-54: offline tests for the conservative gating on the AGENT tool-call-parse scaffold
(REQ-49's `apply_agent_scaffold`) so it does NOT fire on specs demanding custom stop/validation
orchestration the generic skeleton cannot express.

MEASURED MOTIVATION: EXT-060 REQ-30's `schema-validation-retry-loop` board class measures 0/3 --
"tool_call count mismatch: expected 2, got 20". That class's contract requires the built agent to
LOCALLY VALIDATE each structured payload and DECIDE ITSELF to stop after a successful validation
(a task-specific stop judgement); `apply_agent_scaffold`'s generic skeleton finalizes ONLY on a
model final/content turn and otherwise dispatches every `tool_calls` turn, so with the class's
2-turn stub script it dispatches to the max-steps ceiling (20) instead of stopping after the
second, valid submission -- when the scaffold fires on this spec it makes the class STRUCTURALLY
unable to pass. FULLY OFFLINE -- no real model/Jetson call anywhere.
"""

# #EXT-036-REQ-54 Start
from __future__ import annotations

from harness.agent_scaffold import (
    apply_agent_scaffold,
    spec_demands_custom_stop_logic,
    spec_demands_tool_calling_agent,
)
from harness.real_systems_suite import (
    AGENT_ADD_STEP_GUARD_MODIFY,
    PLAIN_AGENT_TASK,
    VALIDATION_RETRY_TASK,
)

_PLAIN_AGENT_SENTENCE = PLAIN_AGENT_TASK.sentence
_STEP_GUARD_MOD_SENTENCE = AGENT_ADD_STEP_GUARD_MODIFY.mod_sentence
_VALIDATION_RETRY_SENTENCE = VALIDATION_RETRY_TASK.sentence

# A representative combined spec for the MODIFY path (mirrors how the real chain feeds
# `base_sentence + mod_sentence` to the repair -- see AGENT_ADD_STEP_GUARD_MODIFY.base_sentence).
_STEP_GUARD_COMBINED_SPEC = AGENT_ADD_STEP_GUARD_MODIFY.base_sentence + "\n\n" + _STEP_GUARD_MOD_SENTENCE

_GENERIC_VALIDATION_PHRASINGS = [
    "The agent must validate the structured payload against a required schema before finalizing.",
    "Retry the request once if the model's tool call fails validation, then give up.",
    "The agent should decide when to stop: finalize when the payload is valid, otherwise retry.",
    "Keep requesting until the payload is valid, up to a maximum of 2 attempts.",
    "Enforce a max-retries cap of 2; stop after the second attempt regardless of validity.",
]

_GENERIC_TOOL_CALLING_PHRASINGS = [
    "Write a tool-calling agent that reads a goal, calls tools, and prints the final answer.",
    "Implement an agent loop against a chat-completions endpoint, dispatching every tool call "
    "the model requests until it returns a plain-content final answer.",
    "The agent should call list_files then read_file and print the result.",
]


# --------------------------------------------------------------------------------------------
# (a) spec_demands_custom_stop_logic: True on the REAL validation-retry sentence + representative
# validation/retry phrasings; False on the REAL plain-agent + agent-modify sentences and generic
# tool-calling phrasings.
# --------------------------------------------------------------------------------------------

def test_custom_stop_logic_true_for_the_real_validation_retry_sentence():
    assert spec_demands_custom_stop_logic(_VALIDATION_RETRY_SENTENCE) is True


def test_custom_stop_logic_true_for_representative_validation_retry_phrasings():
    for phrasing in _GENERIC_VALIDATION_PHRASINGS:
        assert spec_demands_custom_stop_logic(phrasing) is True, phrasing


def test_custom_stop_logic_false_for_the_real_plain_agent_sentence():
    assert spec_demands_custom_stop_logic(_PLAIN_AGENT_SENTENCE) is False


def test_custom_stop_logic_false_for_the_real_agent_modify_sentence():
    assert spec_demands_custom_stop_logic(_STEP_GUARD_MOD_SENTENCE) is False
    # also false combined with its base (create) sentence, mirroring the real MODIFY wire
    assert spec_demands_custom_stop_logic(_STEP_GUARD_COMBINED_SPEC) is False


def test_custom_stop_logic_false_for_generic_tool_calling_phrasings():
    for phrasing in _GENERIC_TOOL_CALLING_PHRASINGS:
        assert spec_demands_custom_stop_logic(phrasing) is False, phrasing


def test_custom_stop_logic_never_raises_on_garbage():
    assert spec_demands_custom_stop_logic(None) is False
    assert spec_demands_custom_stop_logic("") is False
    assert spec_demands_custom_stop_logic(12345) is False
    assert spec_demands_custom_stop_logic(object()) is False


# --------------------------------------------------------------------------------------------
# (b) apply_agent_scaffold self-gates to a byte-identical no-op (+ skip note) on a gated spec,
# even when the modules dict looks broken/absent -- the scaffold must never fire on this class.
# --------------------------------------------------------------------------------------------

def test_apply_agent_scaffold_noops_on_the_real_validation_retry_spec_when_loop_broken():
    modules = {"main.py": "# TODO -- broken/absent loop\n"}
    repaired, notes = apply_agent_scaffold(modules, _VALIDATION_RETRY_SENTENCE)
    assert repaired == modules
    assert any("skipped" in n and "custom stop" in n for n in notes)


def test_apply_agent_scaffold_noops_on_the_real_validation_retry_spec_when_loop_absent():
    modules = {}
    repaired, notes = apply_agent_scaffold(modules, _VALIDATION_RETRY_SENTENCE)
    assert repaired == {}
    # the gate is checked before the empty-modules short-circuit, so the skip note still fires
    assert any("skipped" in n and "custom stop" in n for n in notes)


def test_apply_agent_scaffold_noops_on_generic_validation_phrasing_when_agent_demanded():
    # each phrasing alone doesn't mention the OPENAI_BASE_URL/tool_calls/chat-completions
    # protocol, so combine it with agent-demanding boilerplate to isolate the REQ-54 gate.
    modules = {"main.py": "OPENAI_BASE_URL JAROS_TOOL_URL tool_calls chat/completions\n"}
    for phrasing in _GENERIC_VALIDATION_PHRASINGS:
        spec_text = (
            "Write a tool-calling agent using OPENAI_BASE_URL and JAROS_TOOL_URL, sending a "
            "chat/completions request each turn. " + phrasing
        )
        assert spec_demands_tool_calling_agent(spec_text) is True, phrasing
        repaired, notes = apply_agent_scaffold(modules, spec_text)
        assert repaired == modules
        assert any("skipped" in n and "custom stop" in n for n in notes), phrasing


# --------------------------------------------------------------------------------------------
# (c) regression guard: the PLAIN agent class and the agent MODIFY task must still scaffold
# exactly as before -- their real sentences must NOT gate the scaffold.
# --------------------------------------------------------------------------------------------

_BROKEN_NO_TOOL_CALLS_PY = (
    'import os\nimport sys\n\n\n'
    'def main():\n'
    '    goal = sys.argv[1] if len(sys.argv) > 1 else ""\n'
    '    print("__JAROS_AGENT_FINAL__" + goal + "__END__", flush=True)\n\n\n'
    'if __name__ == "__main__":\n'
    '    main()\n'
)


def test_plain_agent_sentence_still_triggers_the_scaffold():
    assert spec_demands_tool_calling_agent(_PLAIN_AGENT_SENTENCE) is True
    assert spec_demands_custom_stop_logic(_PLAIN_AGENT_SENTENCE) is False
    modules = {"main.py": _BROKEN_NO_TOOL_CALLS_PY}
    repaired, notes = apply_agent_scaffold(modules, _PLAIN_AGENT_SENTENCE)
    assert repaired["main.py"] != _BROKEN_NO_TOOL_CALLS_PY
    assert any("skeleton" in n for n in notes)


def test_agent_modify_sentence_still_triggers_the_scaffold():
    assert spec_demands_tool_calling_agent(_STEP_GUARD_COMBINED_SPEC) is True
    assert spec_demands_custom_stop_logic(_STEP_GUARD_COMBINED_SPEC) is False
    modules = {"main.py": _BROKEN_NO_TOOL_CALLS_PY}
    repaired, notes = apply_agent_scaffold(modules, _STEP_GUARD_COMBINED_SPEC)
    assert repaired["main.py"] != _BROKEN_NO_TOOL_CALLS_PY
    assert any("skeleton" in n for n in notes)


def test_the_real_validation_retry_sentence_does_trigger_the_gate():
    assert spec_demands_tool_calling_agent(_VALIDATION_RETRY_SENTENCE) is True
    assert spec_demands_custom_stop_logic(_VALIDATION_RETRY_SENTENCE) is True
# #EXT-036-REQ-54 End
