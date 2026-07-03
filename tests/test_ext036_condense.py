"""EXT-036 TASK-11: short-term memory condensation (REQ-15).

OFFLINE — no live model. ``harness.session.condense`` is exercised directly against a stub
llm client (mirrors the `.complete(LlmRequest) -> .text` shape used elsewhere in EXT-036,
e.g. tests/test_ext036_repo_memory.py's `_StubLlm`), and the CLI wiring
(`harness/cli.py::handle`'s history-injection path) is exercised via `JcodeCli` with both the
orchestrator and the llm stubbed — no network, no real model.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli
from harness.session import MAX_TURNS, CONDENSE_KEEP, Session, condense


class _FakeDecision:
    def __init__(self, action: str, arg: str) -> None:
        self.payload = {"action": action, "arg": arg}


class _StubOrchestrator:
    """Records every context dict `decide()` receives; routes to a fixed action."""

    def __init__(self, action: str = "help", arg: str = "") -> None:
        self.calls: list[dict] = []
        self._action = action
        self._arg = arg

    def decide(self, context):
        self.calls.append(context)
        return [_FakeDecision(self._action, self._arg)]


class _StubLlmResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubLlm:
    """Mirrors the `.complete(LlmRequest) -> .text` shape `condense()`'s summary call uses."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list = []

    def complete(self, request):
        self.calls.append(request)
        return _StubLlmResponse(self._text)


class _RaisingLlm:
    """Simulates an unreachable model — `.complete` always raises."""

    def complete(self, request):
        raise RuntimeError("model unreachable")


def _stub_cli(action: str = "help", arg: str = "") -> tuple[JcodeCli, _StubOrchestrator]:
    cli = JcodeCli()
    stub = _StubOrchestrator(action, arg)
    cli._load_agent = lambda filename, llm: stub   # any agent name -> the stub
    return cli, stub


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors the other
    EXT-036 test files)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path)
    yield tmp_path


def _make_session(n_turns: int, fact_turn_text: str | None = None) -> Session:
    """A Session with `n_turns` turns; if `fact_turn_text` is given it's planted as the FIRST
    turn's text (so it lands among the oldest, now-summarized turns once condensed)."""
    s = Session()
    for i in range(n_turns):
        text = fact_turn_text if (i == 0 and fact_turn_text) else f"turn {i}"
        s.append("user" if i % 2 == 0 else "assistant", text)
    return s


# --- (a) under budget -> no condense, raw turns returned unchanged ------------------------

def test_under_budget_returns_raw_recent_unchanged():
    s = _make_session(10)   # well under MAX_TURNS
    assert condense(s, llm=_StubLlm("should never be called")) == s.recent()


def test_under_budget_never_calls_the_model():
    s = _make_session(MAX_TURNS)   # exactly AT the budget -> still no condense (<=)
    llm = _StubLlm("unused")
    condense(s, llm=llm)
    assert llm.calls == []


# --- (b) over budget -> oldest turns replaced by a summary entry, recent turns kept -------

def test_over_budget_condenses_oldest_into_a_single_summary_entry():
    s = _make_session(MAX_TURNS + 20)
    llm = _StubLlm("condensed summary of the older turns")
    out = condense(s, llm=llm)

    assert out[0] == {"role": "summary", "text": "condensed summary of the older turns"}
    assert len(out) == 1 + CONDENSE_KEEP   # summary + kept recent turns
    # the kept turns are exactly the raw most-recent CONDENSE_KEEP turns
    assert out[1:] == s.recent(cap=CONDENSE_KEEP, max_chars=300)
    # the model was actually called (the only model step)
    assert len(llm.calls) == 1


def test_over_budget_slice_stays_small_regardless_of_transcript_size():
    small = condense(_make_session(MAX_TURNS + 5), llm=_StubLlm("s"))
    huge = condense(_make_session(MAX_TURNS + 500), llm=_StubLlm("s"))
    assert len(small) == len(huge) == 1 + CONDENSE_KEEP   # bounded, not growing with transcript size


# --- (c) model-failure fallback truncates without raising ---------------------------------

def test_model_failure_falls_back_to_truncation_without_raising():
    s = _make_session(MAX_TURNS + 20)
    out = condense(s, llm=_RaisingLlm())   # must not raise
    assert out[0]["role"] == "summary"
    assert isinstance(out[0]["text"], str) and out[0]["text"]   # some fallback text, not empty
    assert len(out) == 1 + CONDENSE_KEEP


def test_model_returning_empty_text_also_falls_back():
    s = _make_session(MAX_TURNS + 20, fact_turn_text="the deploy target is staging-west")
    out = condense(s, llm=_StubLlm(""))   # empty completion -> treated as a failure
    assert out[0]["role"] == "summary"
    assert "the deploy target is staging-west" in out[0]["text"]   # fallback preserves the fact


# --- (d) a fact from an old (now-summarized) turn appears in the canned summary -----------

def test_old_fact_survives_into_the_canned_summary():
    s = _make_session(MAX_TURNS + 20, fact_turn_text="the API key rotates every 90 days")
    llm = _StubLlm("Earlier the user noted the API key rotates every 90 days.")
    out = condense(s, llm=llm)
    assert "API key rotates every 90 days" in out[0]["text"]
    # and the fact-bearing turn itself is old enough to have been dropped from the raw kept slice
    assert not any("API key" in t.get("text", "") for t in out[1:])


# --- CLI wiring: history-injection path uses condense() ------------------------------------

def test_cli_short_session_history_unaffected_by_condense_wiring():
    """Byte-identical to the pre-TASK-11 behavior for a short session (no condense engaged)."""
    cli, stub = _stub_cli()
    cli.llm = _StubLlm("should not be called for a short session")
    cli.handle("first request")
    expected_history = cli.session.recent()   # snapshot before the next turn is appended
    cli.handle("second request")
    ctx = stub.calls[-1]
    assert ctx["history"] == expected_history
    assert cli.llm.calls == []


def test_cli_long_session_injects_condensed_history_with_summary():
    """Once the session transcript grows past MAX_TURNS, the router sees a condensed
    [summary] + recent-turns slice instead of the raw (unbounded) transcript."""
    cli, stub = _stub_cli()
    cli.llm = _StubLlm("summary: earlier the user asked about widget-42 configuration")
    cli.handle("please remember widget-42 configuration details")
    # drive the transcript well past MAX_TURNS (each handle() call appends 2 turns)
    for i in range(MAX_TURNS):
        cli.handle(f"followup request {i}")

    ctx = stub.calls[-1]
    history = ctx["history"]
    assert history[0]["role"] == "summary"
    assert "widget-42" in history[0]["text"]
    assert len(history) == 1 + CONDENSE_KEEP
    assert "widget-42" in ctx["request"]   # the augmented request carries the summary too
