"""EXT-043: Headless / Unix-composable CLI -- stdin pipe, --output-format json, --max-turns,
deterministic exit codes, all as a thin deterministic layer over the existing one-shot path.

OFFLINE -- no live model. `harness.cli.JcodeCli` is monkeypatched with a stub class so
`_run_one_shot`/`main()` never construct a real Runtime/LLM/agent. This mirrors the stubbing
approach in tests/test_ext036_cli_session.py.
"""
from __future__ import annotations

import io
import json

import pytest

import harness.cli as cli_mod
from harness.cli import (
    _parse_headless_args,
    _read_stdin_request,
    _run_one_shot,
    main,
)


class _StubCli:
    """Stand-in for JcodeCli: records the request it was given and returns a fixed response,
    or raises if configured to (simulating an unresolvable request / tool failure)."""

    response = "stub response text"
    model = "stub-model"
    raise_on_handle = False
    raise_on_init = False
    last_request = None
    last_session_id = None
    last_stream = None  # #EXT-045-REQ-1

    def __init__(self, session_id=None, stream=False):
        if _StubCli.raise_on_init:
            raise RuntimeError("stub init failure")
        _StubCli.last_session_id = session_id
        _StubCli.last_stream = stream  # #EXT-045-REQ-1

    def handle(self, request):
        _StubCli.last_request = request
        if _StubCli.raise_on_handle:
            raise RuntimeError("stub handle failure")
        return _StubCli.response

    def on_stop(self):
        # EXT-047: a one-shot run both starts and stops within its call, so the headless path
        # now calls cli.on_stop() to fire any configured Stop hooks. The real JcodeCli.on_stop
        # is internally guarded (never raises); the stub just needs to accept the call.
        pass


@pytest.fixture(autouse=True)
def _reset_stub():
    _StubCli.raise_on_handle = False
    _StubCli.raise_on_init = False
    _StubCli.last_request = None
    _StubCli.last_session_id = None
    _StubCli.last_stream = None  # #EXT-045-REQ-1
    yield


@pytest.fixture()
def stub_jcode_cli(monkeypatch):
    """Patch harness.cli.JcodeCli (the name _run_one_shot/main look up) with the stub class."""
    monkeypatch.setattr(cli_mod, "JcodeCli", _StubCli)
    return _StubCli


# --- _parse_headless_args ---------------------------------------------------------------

def test_parse_no_flags_leaves_rest_unchanged():
    session_id, fmt, max_turns, rest = _parse_headless_args(["fix", "the", "bug", "in", "foo.py"])
    assert session_id is None
    assert fmt == "text"
    assert max_turns is None
    assert rest == ["fix", "the", "bug", "in", "foo.py"]


def test_parse_resume_extracted():
    session_id, fmt, max_turns, rest = _parse_headless_args(["--resume", "abc123", "hello"])
    assert session_id == "abc123"
    assert rest == ["hello"]


def test_parse_output_format_json():
    _, fmt, _, rest = _parse_headless_args(["--output-format", "json", "do", "thing"])
    assert fmt == "json"
    assert rest == ["do", "thing"]


def test_parse_output_format_unrecognized_falls_back_to_text():
    _, fmt, _, _ = _parse_headless_args(["--output-format", "bogus", "req"])
    assert fmt == "text"


def test_parse_max_turns_integer():
    _, _, max_turns, rest = _parse_headless_args(["--max-turns", "3", "req"])
    assert max_turns == 3
    assert rest == ["req"]


def test_parse_max_turns_non_integer_falls_back_to_none():
    _, _, max_turns, _ = _parse_headless_args(["--max-turns", "nope", "req"])
    assert max_turns is None


def test_parse_flags_in_any_order():
    session_id, fmt, max_turns, rest = _parse_headless_args(
        ["--max-turns", "2", "--output-format", "json", "--resume", "sid1", "fix", "it"]
    )
    assert session_id == "sid1"
    assert fmt == "json"
    assert max_turns == 2
    assert rest == ["fix", "it"]


def test_parse_dash_request_stays_in_rest():
    _, _, _, rest = _parse_headless_args(["-"])
    assert rest == ["-"]


# --- stdin piping (REQ-1) ----------------------------------------------------------------

def test_stdin_piped_request_routes_to_handle(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli"])
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: False)
    monkeypatch.setattr(cli_mod, "_read_stdin_request", lambda: "fix foo.py via pipe")
    code = main()
    assert code == 0
    assert _StubCli.last_request == "fix foo.py via pipe"
    out = capsys.readouterr().out
    assert "stub response text" in out


def test_dash_reads_stdin_unconditionally_even_if_tty(monkeypatch, stub_jcode_cli):
    monkeypatch.setattr("sys.argv", ["harness.cli", "-"])
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)   # even a "tty" -- explicit '-' wins
    monkeypatch.setattr(cli_mod, "_read_stdin_request", lambda: "piped via dash")
    code = main()
    assert code == 0
    assert _StubCli.last_request == "piped via dash"


def test_no_args_and_tty_falls_through_to_repl(monkeypatch):
    monkeypatch.setattr("sys.argv", ["harness.cli"])
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)
    called = {}

    def fake_repl(session_id=None):
        called["session_id"] = session_id
        return 0

    monkeypatch.setattr(cli_mod, "repl", fake_repl)
    code = main()
    assert code == 0
    assert "session_id" in called   # repl() was reached, unchanged behavior


def test_empty_piped_stdin_falls_through_to_repl(monkeypatch):
    """An empty pipe (no request text at all) is not a request -- falls back to repl(), not a
    silent no-op one-shot run."""
    monkeypatch.setattr("sys.argv", ["harness.cli"])
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: False)
    monkeypatch.setattr(cli_mod, "_read_stdin_request", lambda: "")
    called = {}

    def fake_repl(session_id=None):
        called["hit"] = True
        return 0

    monkeypatch.setattr(cli_mod, "repl", fake_repl)
    code = main()
    assert code == 0
    assert called.get("hit") is True


# --- --output-format json (REQ-2) ---------------------------------------------------------

def test_output_format_json_is_parseable_with_expected_keys(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "--output-format", "json", "do", "a", "thing"])
    code = main()
    assert code == 0
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)   # must be valid, single-line JSON
    assert obj["request"] == "do a thing"
    assert obj["response"] == "stub response text"
    assert obj["ok"] is True
    assert obj["model"] == "stub-model"


def test_output_format_text_default_unaffected(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "plain", "request"])
    code = main()
    assert code == 0
    out = capsys.readouterr().out
    assert out.strip() == "stub response text"   # no JSON wrapping in the default/text format


# --- exit codes (REQ-3) --------------------------------------------------------------------

def test_exit_code_zero_on_success_text(monkeypatch, stub_jcode_cli):
    monkeypatch.setattr("sys.argv", ["harness.cli", "a", "request"])
    assert main() == 0


def test_exit_code_nonzero_on_handle_failure_text(monkeypatch, stub_jcode_cli, capsys):
    _StubCli.raise_on_handle = True
    monkeypatch.setattr("sys.argv", ["harness.cli", "a", "request"])
    code = main()
    assert code != 0
    out = capsys.readouterr().out
    assert "error" in out.lower()


def test_exit_code_nonzero_on_init_failure_json(monkeypatch, stub_jcode_cli, capsys):
    _StubCli.raise_on_init = True
    monkeypatch.setattr("sys.argv", ["harness.cli", "--output-format", "json", "a", "request"])
    code = main()
    assert code != 0
    obj = json.loads(capsys.readouterr().out.strip())
    assert obj["ok"] is False
    assert "error" in obj
    assert obj["response"] is None


# --- --max-turns cap (REQ-4) ----------------------------------------------------------------

def test_max_turns_zero_refuses_without_constructing_cli(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "--max-turns", "0", "a", "request"])
    code = main()
    assert code != 0
    assert _StubCli.last_request is None   # handle() was never reached
    out = capsys.readouterr().out
    assert "max-turns" in out.lower() or "0" in out


def test_max_turns_one_runs_normally(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "--max-turns", "1", "a", "request"])
    code = main()
    assert code == 0
    assert _StubCli.last_request == "a request"


def test_max_turns_absent_behaves_as_today(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "a", "request"])
    code = main()
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out == "stub response text"


# --- backward-compat: default/no-flags behavior is unchanged -------------------------------

def test_run_one_shot_text_no_cap_matches_pre_ext043_contract(monkeypatch, stub_jcode_cli):
    """_run_one_shot's text/no-max-turns branch must reproduce the EXACT pre-EXT-043 main()
    body: print(handle(...)) on success, red error text + exit 1 on exception."""
    text, code = _run_one_shot("a request", None, "text", None)
    assert text == "stub response text"
    assert code == 0

    _StubCli.raise_on_handle = True
    text, code = _run_one_shot("a request", None, "text", None)
    assert text.startswith("\033[31merror:\033[0m")
    assert code == 1


def test_resume_flag_still_passes_session_id(monkeypatch, stub_jcode_cli):
    monkeypatch.setattr("sys.argv", ["harness.cli", "--resume", "sess-1", "hi", "there"])
    code = main()
    assert code == 0
    assert _StubCli.last_session_id == "sess-1"
    assert _StubCli.last_request == "hi there"


# --- _read_stdin_request never raises -------------------------------------------------------

def test_read_stdin_request_never_raises(monkeypatch):
    class _Boom:
        def read(self):
            raise OSError("boom")

    monkeypatch.setattr("sys.stdin", _Boom())
    assert _read_stdin_request() == ""
