"""EXT-036 TASK-1: CLI conversational session state + resume (REQ-12 backbone).

OFFLINE — no live model. The orchestrator agent is stubbed via `cli._load_agent`
(an instance attribute set in JcodeCli.__init__ from harness.coding_loop._load_agent,
so it can be monkeypatched per-instance without touching the real agent file or
network). The NL-fix path is exercised by monkeypatching harness.multi_file.multi_file_fix.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli


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


def _stub_cli(action: str = "help", arg: str = "") -> tuple[JcodeCli, _StubOrchestrator]:
    cli = JcodeCli()
    stub = _StubOrchestrator(action, arg)
    cli._load_agent = lambda filename, llm: stub   # any agent name -> the stub
    return cli, stub


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Every test in this file persists sessions under a throwaway tmp dir, never the
    real .jaros-data/sessions/."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path)
    yield tmp_path


# --- (a) Session accumulates user+assistant turns across handle() calls ---------------

def test_session_accumulates_turns_across_calls():
    cli, _ = _stub_cli()
    cli.handle("hello there")
    cli.handle("another plain request")
    assert [t["role"] for t in cli.session.turns] == ["user", "assistant", "user", "assistant"]
    assert cli.session.turns[0]["text"] == "hello there"
    assert cli.session.turns[2]["text"] == "another plain request"


def test_session_has_a_stable_id_across_turns():
    cli, _ = _stub_cli()
    cli.handle("first")
    sid = cli.session.id
    cli.handle("second")
    assert cli.session.id == sid


# --- (b) bounded recent transcript is passed into plain-language routing --------------

def test_first_turn_has_no_history_and_request_is_unchanged():
    cli, stub = _stub_cli()
    cli.handle("solo request")
    ctx = stub.calls[0]
    assert ctx["history"] == []
    assert ctx["request"] == "solo request"   # no history -> byte-identical to old behavior


def test_orchestrator_receives_prior_turn_context_on_followup():
    cli, stub = _stub_cli()
    cli.handle("first request")
    cli.handle("second request")
    ctx2 = stub.calls[1]
    assert "history" in ctx2
    assert any(h["text"] == "first request" for h in ctx2["history"])
    assert "first request" in ctx2["request"]      # augmented request carries the context too
    assert "second request" in ctx2["request"]


def test_history_is_bounded_to_the_cap():
    cli, stub = _stub_cli()
    cli.handle("first request")
    cli.handle("second request")
    for i in range(3, 10):
        cli.handle(f"request {i}")
    last_ctx = stub.calls[-1]
    assert len(last_ctx["history"]) == 6   # cap ~6 turns (small model -> small context)


def test_nl_fix_receives_bounded_history(monkeypatch):
    """The NL-fix path (orchestrator routes to 'fix') also gets conversation context —
    a follow-up like 'now add error handling to that' resolves against the prior turn."""
    cli, _ = _stub_cli(action="fix", arg="")
    seen_instructions: list[str] = []

    def fake_multi_file_fix(root, testcmd, instruction, test_file, max_iters=3, verbose=True):
        seen_instructions.append(instruction)
        return {"solved": True, "fixed": []}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", fake_multi_file_fix)
    cli.handle("please fix something")
    cli.handle("now add error handling to that")
    assert len(seen_instructions) == 2
    assert seen_instructions[0] == "please fix something"      # first turn: no history yet
    assert "please fix something" in seen_instructions[1]       # second turn: prior context folded in
    assert "now add error handling to that" in seen_instructions[1]


# --- (c) persist -> /resume round-trips a transcript -----------------------------------

def test_persist_and_resume_roundtrip(tmp_path):
    cli, _ = _stub_cli()
    cli.handle("remember this detail")
    sid = cli.session.id
    assert (tmp_path / f"{sid}.json").is_file()

    cli2, _ = _stub_cli()
    out = cli2.dispatch(f"/resume {sid}")
    assert "resumed" in out.lower()
    assert cli2.session.id == sid
    assert any(t["text"] == "remember this detail" for t in cli2.session.turns)


def test_resume_unknown_id_reports_cleanly():
    cli, _ = _stub_cli()
    out = cli.dispatch("/resume no-such-session-xyz")
    assert "no saved session" in out.lower()
    assert cli.session.turns == []   # unaffected


def test_resume_continues_and_further_turns_see_restored_history():
    cli, stub = _stub_cli()
    cli.handle("original topic")
    sid = cli.session.id

    cli2, stub2 = _stub_cli()
    cli2.dispatch(f"/resume {sid}")
    cli2.handle("a follow-up")
    ctx = stub2.calls[0]
    assert any(h["text"] == "original topic" for h in ctx["history"])


def test_new_starts_a_fresh_session():
    cli, _ = _stub_cli()
    cli.handle("turn one")
    old_id = cli.session.id
    out = cli.dispatch("/new")
    assert cli.session.id != old_id
    assert cli.session.turns == []
    assert old_id in out


def test_sessions_command_lists_saved_sessions(tmp_path):
    cli, _ = _stub_cli()
    cli.handle("a message")
    sid = cli.session.id
    listing = cli.dispatch("/sessions")
    assert sid in listing


def test_resume_session_id_arg_on_construction(tmp_path):
    cli, _ = _stub_cli()
    cli.handle("saved via constructor test")
    sid = cli.session.id

    cli2 = JcodeCli(session_id=sid)
    assert cli2.session.id == sid
    assert any(t["text"] == "saved via constructor test" for t in cli2.session.turns)


# --- (d) slash commands remain stateless + unchanged ------------------------------------

def test_slash_command_output_unaffected_by_prior_history():
    cli, _ = _stub_cli()
    cli.handle("first plain request")   # accumulate some session history
    out_with_history = cli.dispatch("/help")

    fresh = JcodeCli()
    out_fresh = fresh.dispatch("/help")
    assert out_with_history == out_fresh


def test_slash_dispatch_never_invokes_the_orchestrator():
    cli, stub = _stub_cli()
    cli.handle("plain request")   # invokes the orchestrator once
    calls_before = len(stub.calls)
    cli.dispatch("/status")
    cli.dispatch("/ls .")
    assert len(stub.calls) == calls_before   # slash commands stay direct/stateless


def test_slash_commands_still_recorded_but_not_context_augmented():
    """Slash turns ARE recorded into the transcript (so /resume shows the full session),
    but dispatch() itself receives no injected context — pure passthrough, same as before."""
    cli, _ = _stub_cli()
    out = cli.dispatch("/help")
    assert "/find" in out   # identical to the pre-EXT-036 /help output
    assert cli.session.turns == []   # dispatch() alone (not handle()) never touches the session

    out2 = cli.handle("/help")
    assert out2 == out
    assert cli.session.turns[-2:] == [
        {"role": "user", "text": "/help", "ts": cli.session.turns[-2]["ts"]},
        {"role": "assistant", "text": out2, "ts": cli.session.turns[-1]["ts"]},
    ]
