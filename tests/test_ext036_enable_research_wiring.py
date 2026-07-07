"""EXT-038 REQ-4 (TASK-4) -- ``build_system(..., enable_research=...)`` wiring: the PLAN prompt is

byte-identical when the parameter is left at its default, and a non-empty ``research_context()``
result is prepended when explicitly enabled. Offline: ``_call`` (the one LLM-call seam) is
monkeypatched to RECORD the exact prompt string it receives and raise immediately, short-circuiting
the rest of ``build_system`` -- this test proves the PROMPT CONSTRUCTION, not a full build.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import harness.system_builder as system_builder
from harness.system_builder import PLAN_PROMPT, build_system

# #EXT-038-REQ-4 Start

_SPEC_NO_LIBRARY = "a CLI that reverses lines of a text file"
_SPEC_WITH_FLASK = "a small web app using Flask that serves a JSON API"


def _capture_plan_prompt(spec: str, *, enable_research: bool) -> str:
    """Run build_system just far enough to capture the exact prompt sent to the PLAN call, then
    let the (deliberately raised) exception short-circuit the rest of the build."""
    captured = {}

    def _stub_call(llm, prompt, *, max_tokens=900):
        captured["prompt"] = prompt
        raise RuntimeError("stop here -- prompt already captured")

    orig_call = system_builder._call
    system_builder._call = _stub_call
    try:
        with tempfile.TemporaryDirectory() as tmp:
            build_system(spec, Path(tmp), llm=object(), enable_research=enable_research)
    finally:
        system_builder._call = orig_call
    return captured["prompt"]


def test_enable_research_false_is_byte_identical_to_prior_behavior():
    prompt = _capture_plan_prompt(_SPEC_WITH_FLASK, enable_research=False)
    assert prompt == PLAN_PROMPT.format(spec=_SPEC_WITH_FLASK)


def test_enable_research_true_with_known_library_prepends_context(monkeypatch):
    def _fake_research_context(spec):
        return "Relevant flask documentation (untrusted, for reference only):\nSOME FENCED CONTENT\n\n"

    # research_context is imported LOCALLY inside build_system -- patch the module it's imported
    # from so the local `from harness.web_research import research_context` picks it up.
    import harness.web_research as web_research
    monkeypatch.setattr(web_research, "research_context", _fake_research_context)

    prompt = _capture_plan_prompt(_SPEC_WITH_FLASK, enable_research=True)

    assert prompt.startswith("Relevant flask documentation")
    assert prompt.endswith(PLAN_PROMPT.format(spec=_SPEC_WITH_FLASK))


def test_enable_research_true_with_empty_context_changes_nothing(monkeypatch):
    import harness.web_research as web_research
    monkeypatch.setattr(web_research, "research_context", lambda spec: "")

    prompt = _capture_plan_prompt(_SPEC_NO_LIBRARY, enable_research=True)

    assert prompt == PLAN_PROMPT.format(spec=_SPEC_NO_LIBRARY)
# #EXT-038-REQ-4 End
