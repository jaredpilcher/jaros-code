"""EXT-036 TASK-81: spec-declared stdlib-affordance hint for the build prompt (REQ-66).

MOTIVATION (MEASURED, EXT-060 board `base32-codec-lib`, 0/3): the task sentence explicitly
says "using only the standard library (the `base64` module is allowed)", yet gemma
HAND-ROLLS the RFC 4648 codec anyway and ships two bugs. The spec HANDS the model a
trivial correct path (`base64.b32encode`/`b32decode`) and it ignores it. The lever: scan
the spec sentence for an EXPLICIT permission of a named stdlib module and surface that
affordance more prominently in the per-module build prompt, gated to genuine stdlib module
names (never a hallucinated/third-party one).

OFFLINE — no live model, no network. `spec_declared_stdlib_affordances` is pure/deterministic
(no model call at all); the prompt-level tests use a tiny capturing stub `llm` (the same
`.complete(LlmRequest) -> .text` convention every other EXT-036 offline test uses) to inspect
the EXACT prompt text `_build_module` sends, never actually invoking a model.
"""

from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    BUILD_PROMPT,
    _build_module,
    _spec_affordance_hint,
    spec_declared_stdlib_affordances,
)
from harness.real_systems_suite import BASE32_CODEC_TASK


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CapturingLlm:
    """Minimal stub llm: records every prompt it is sent and always returns a syntactically
    valid canned module body, so `_build_module`'s bounded repair loop never needs a second
    call (the FIRST captured prompt is always the one under test)."""

    def __init__(self, module_code: str = "def encode(data):\n    return ''\n") -> None:
        self.module_code = module_code
        self.prompts: list[str] = []

    def complete(self, request):
        self.prompts.append(request.prompt)
        return _Resp(self.module_code)


# ---------------------------------------------------------------------------
# (a) spec_declared_stdlib_affordances -- pure extraction + stdlib gating
# ---------------------------------------------------------------------------

def test_extracts_base64_from_the_real_base32_task_sentence():
    # The exact sentence on the EXT-060 board that motivated this task.
    assert spec_declared_stdlib_affordances(BASE32_CODEC_TASK.sentence) == ["base64"]


def test_extracts_module_named_via_the_x_module_is_allowed_phrasing():
    sentence = "Write a module using only the standard library (the `difflib` module is allowed)."
    assert spec_declared_stdlib_affordances(sentence) == ["difflib"]


def test_extracts_module_named_via_using_the_x_module_phrasing():
    sentence = "Format the output using the textwrap module for line wrapping."
    assert spec_declared_stdlib_affordances(sentence) == ["textwrap"]


def test_extracts_module_named_via_you_may_use_x_phrasing():
    sentence = "You may use `shlex` to tokenize the command line."
    assert spec_declared_stdlib_affordances(sentence) == ["shlex"]


def test_extracts_module_named_via_with_the_x_module_phrasing():
    sentence = "Parse the config with the configparser module."
    assert spec_declared_stdlib_affordances(sentence) == ["configparser"]


def test_non_stdlib_module_is_gated_out():
    # "requests" is a real, common package name but is NOT in the standard library --
    # must never be surfaced (this function can never invent/leak a non-stdlib affordance).
    sentence = "Make HTTP calls -- the `requests` module is allowed for this."
    assert spec_declared_stdlib_affordances(sentence) == []


def test_no_module_named_returns_empty_list():
    sentence = "Write a CLI that reverses each line of stdin."
    assert spec_declared_stdlib_affordances(sentence) == []


def test_case_and_backtick_variants_normalize_to_canonical_stdlib_name():
    sentence = "The BASE64 module is allowed for encoding."
    assert spec_declared_stdlib_affordances(sentence) == ["base64"]


def test_dedup_first_appearance_order_across_multiple_mentions():
    sentence = (
        "The `os` module is allowed for filesystem access. Also try using the sys module "
        "for exit codes. The `os` module is allowed, as stated."
    )
    assert spec_declared_stdlib_affordances(sentence) == ["os", "sys"]


def test_none_and_empty_sentence_never_raise():
    assert spec_declared_stdlib_affordances(None) == []
    assert spec_declared_stdlib_affordances("") == []


# ---------------------------------------------------------------------------
# _spec_affordance_hint -- the rendered hint text
# ---------------------------------------------------------------------------

def test_hint_empty_when_no_affordance():
    assert _spec_affordance_hint("Write a CLI that reverses stdin.") == ""


def test_hint_text_names_the_module():
    hint = _spec_affordance_hint(BASE32_CODEC_TASK.sentence)
    assert hint == (
        "Note: the specification explicitly permits the standard-library module(s): "
        "base64. Prefer using them directly where they already implement the required "
        "behavior, instead of re-implementing that behavior by hand."
    )


# ---------------------------------------------------------------------------
# (b) prompt-level: the hint actually reaches the per-module build prompt, and the
# empty-list path is BYTE-IDENTICAL to the pre-lever prompt (zero blast radius).
# ---------------------------------------------------------------------------

_MODULE = {
    "name": "base32_codec.py",
    "responsibility": "RFC 4648 base32 encode/decode",
    "exports": [{"name": "encode", "signature": "def encode(data):"}],
    "imports": [],
}


def test_build_prompt_contains_hint_when_spec_names_a_stdlib_module():
    llm = _CapturingLlm()
    _build_module(BASE32_CODEC_TASK.sentence, _MODULE, {}, llm)
    assert len(llm.prompts) == 1
    prompt = llm.prompts[0]
    assert "standard-library module(s): base64" in prompt
    assert "instead of re-implementing that behavior by hand." in prompt


def test_build_prompt_byte_identical_to_pre_lever_prompt_when_no_affordance():
    spec = "Write a single-file CLI that reverses each line of stdin."
    llm = _CapturingLlm()
    _build_module(spec, _MODULE, {}, llm)
    assert len(llm.prompts) == 1
    prompt = llm.prompts[0]
    sigs = "; ".join(
        e.get("signature", e.get("name", "")) for e in (_MODULE.get("exports", []) or [])
    )
    expected = BUILD_PROMPT.format(
        name=_MODULE["name"], spec=spec, resp=_MODULE["responsibility"], sigs=sigs,
        ledger="", routing="", deps="",
    )
    assert prompt == expected
    assert "standard-library module(s)" not in prompt


def test_build_prompt_never_contains_hint_substring_for_non_stdlib_named_module():
    spec = "Make HTTP calls -- the `requests` module is allowed for this task."
    llm = _CapturingLlm()
    _build_module(spec, _MODULE, {}, llm)
    prompt = llm.prompts[0]
    assert "standard-library module(s)" not in prompt
