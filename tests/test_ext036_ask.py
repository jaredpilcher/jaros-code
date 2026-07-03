"""EXT-036 TASK-12: ask-the-user when a plain-language request is ambiguous (REQ-8).

OFFLINE -- no live model, no network. `harness.ask_user.detect_ambiguity` is exercised
directly against a stub llm client (mirrors the `.complete(LlmRequest) -> .text` shape used
elsewhere in EXT-036, e.g. tests/test_ext036_repo_memory.py's `_StubLlm`); the CLI wiring
(`harness/cli.py::handle`/`_maybe_ask`) is exercised via `JcodeCli` with the orchestrator
stubbed and `input()` monkeypatched -- never a real terminal read.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.ask_user import detect_ambiguity
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


class _StubLlmResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubLlm:
    """Mirrors the `.complete(LlmRequest) -> .text` shape `detect_ambiguity()` uses."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list = []

    def complete(self, request):
        self.calls.append(request)
        return _StubLlmResponse(self._text)


class _RaisingLlm:
    """Simulates an unreachable model -- `.complete` always raises."""

    def complete(self, request):
        raise RuntimeError("model unreachable")


def _stub_cli(action: str = "help", arg: str = "") -> "tuple[JcodeCli, _StubOrchestrator]":
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


# --- (a) detect_ambiguity: canned question / clear -> None / model failure -> None --------

def test_detect_ambiguity_returns_the_canned_question_for_an_ambiguous_request():
    llm = _StubLlm("Which output format do you want: CSV or JSON?")
    q = detect_ambiguity("build me an export tool", llm=llm)
    assert q == "Which output format do you want: CSV or JSON?"
    assert len(llm.calls) == 1


def test_detect_ambiguity_returns_none_for_a_clear_request():
    llm = _StubLlm("NONE")
    assert detect_ambiguity("fix the off-by-one bug in foo.py", llm=llm) is None


def test_detect_ambiguity_returns_none_when_the_llm_raises():
    assert detect_ambiguity("do something", llm=_RaisingLlm()) is None


def test_detect_ambiguity_returns_none_on_empty_request():
    assert detect_ambiguity("", llm=_StubLlm("Some question?")) is None
    assert detect_ambiguity("   ", llm=_StubLlm("Some question?")) is None


def test_detect_ambiguity_returns_none_on_empty_model_output():
    assert detect_ambiguity("do the thing", llm=_StubLlm("")) is None


def test_detect_ambiguity_returns_none_on_degenerate_non_question_output():
    """Conservative parsing: output that isn't clearly a real question defaults to None,
    even if it isn't literally NONE (under-asking is safer than over-asking)."""
    assert detect_ambiguity("do the thing", llm=_StubLlm("sure, I can help")) is None
    assert detect_ambiguity("do the thing", llm=_StubLlm("N/A")) is None
    assert detect_ambiguity("do the thing", llm=_StubLlm("ok?")) is None   # too short


def test_detect_ambiguity_strips_and_bounds_the_question():
    llm = _StubLlm('  "Which module should this change apply to?"  \nextra ignored line')
    q = detect_ambiguity("modify the system", llm=llm)
    assert q == "Which module should this change apply to?"


# --- (b) interactive path asks + folds the stubbed answer into the routed request ---------

def test_interactive_handle_asks_and_folds_answer_into_routed_request(monkeypatch):
    cli, stub = _stub_cli()
    cli.llm = _StubLlm("Which environment: staging or production?")
    inputs = iter(["production"])
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: next(inputs))

    cli.handle("deploy the service", interactive=True)

    ctx = stub.calls[0]
    assert "Clarification: production" in ctx["request"]
    assert "deploy the service" in ctx["request"]


def test_interactive_handle_records_question_and_answer_as_session_turns(monkeypatch):
    cli, _stub = _stub_cli()
    cli.llm = _StubLlm("Which environment: staging or production?")
    inputs = iter(["production"])
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: next(inputs))

    cli.handle("deploy the service", interactive=True)

    texts = [t["text"] for t in cli.session.turns]
    assert "Which environment: staging or production?" in texts
    assert "production" in texts


def test_interactive_handle_does_not_ask_when_request_is_clear(monkeypatch):
    cli, stub = _stub_cli()
    cli.llm = _StubLlm("NONE")

    def _fail_input(*_a, **_kw):
        raise AssertionError("input() must not be called for a clear request")

    monkeypatch.setattr("builtins.input", _fail_input)
    cli.handle("fix the bug in foo.py", interactive=True)
    ctx = stub.calls[0]
    assert ctx["request"] == "fix the bug in foo.py"   # unchanged, byte-identical


def test_interactive_handle_never_raises_on_interrupted_answer(monkeypatch):
    cli, stub = _stub_cli()
    cli.llm = _StubLlm("Which environment: staging or production?")

    def _interrupt(*_a, **_kw):
        raise EOFError()

    monkeypatch.setattr("builtins.input", _interrupt)
    out = cli.handle("deploy the service", interactive=True)   # must not raise
    assert isinstance(out, str)
    ctx = stub.calls[0]
    assert ctx["request"] == "deploy the service"   # no answer -> unchanged


# --- (c) headless/non-interactive path NEVER asks ------------------------------------------

def test_headless_handle_default_never_asks(monkeypatch):
    cli, stub = _stub_cli()
    cli.llm = _StubLlm("Which environment: staging or production?")

    def _fail_input(*_a, **_kw):
        raise AssertionError("input() must not be called in headless mode")

    monkeypatch.setattr("builtins.input", _fail_input)
    out = cli.handle("deploy the service")   # interactive defaults to False
    assert isinstance(out, str)
    ctx = stub.calls[0]
    assert ctx["request"] == "deploy the service"   # never augmented with a clarification


def test_headless_handle_explicit_false_never_asks(monkeypatch):
    cli, stub = _stub_cli()
    cli.llm = _StubLlm("Which environment: staging or production?")
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: (_ for _ in ()).throw(
        AssertionError("input() must not be called")))
    cli.handle("deploy the service", interactive=False)
    assert stub.calls[0]["request"] == "deploy the service"


# --- (d) slash commands never trigger a question --------------------------------------------

def test_slash_command_never_triggers_a_question(monkeypatch):
    cli, _stub = _stub_cli()
    cli.llm = _StubLlm("Which environment: staging or production?")

    def _fail_input(*_a, **_kw):
        raise AssertionError("input() must not be called for a slash command")

    monkeypatch.setattr("builtins.input", _fail_input)
    out = cli.handle("/help", interactive=True)
    assert "/find" in out   # normal /help output, unaffected


def test_dispatch_never_triggers_a_question(monkeypatch):
    cli, _stub = _stub_cli()
    cli.llm = _StubLlm("Which environment: staging or production?")

    def _fail_input(*_a, **_kw):
        raise AssertionError("input() must not be called via dispatch")

    monkeypatch.setattr("builtins.input", _fail_input)
    out = cli.dispatch("/status")
    assert isinstance(out, str)
