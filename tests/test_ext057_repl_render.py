"""EXT-057 REQ-3: natural-language-first REPL render — all OFFLINE, no live model, no network.

Covers:
  (a) `harness.repl_render.render_stream` — a synthetic stream-bus event list renders the
      expected surface (tool cards, spinner/thinking indicator, ask prompt, cancel note,
      streamed assistant text) and returns the right final text; never raises on malformed
      events; defaults `out` to stdout.
  (b) `harness.cli.repl()` — non-TTY/piped stays on the CURRENT `_run_command_interruptible` +
      print behavior BYTE-STABLE (the new streamed path is TTY-gated via the existing
      `should_stream` and is never even attempted when it is off); `/`-prefixed input always
      dispatches the existing slash table.
  (c) `harness.cli._try_stream_plain` — degrades to `None` (signalling "fall back") whenever
      `coding_loop.solve_streaming` is absent, has an incompatible signature, or raises --
      `coding_loop.solve_streaming` does not exist yet (TASK-2 lands separately/in parallel), so
      these tests stub it rather than requiring it.
"""
from __future__ import annotations

# #EXT-057-REQ-3 Start
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.repl_render import render_stream  # noqa: E402


# =====================================================================================
# (a) render_stream — synthetic stream-bus event list, no coding_loop/stream_bus involved
# =====================================================================================

def test_render_stream_renders_tool_card_and_streamed_text_and_returns_final():
    events = [
        {"type": "thinking"},
        {"type": "tool_start", "name": "fs.read"},
        {"type": "tool_result", "name": "fs.read", "ok": True, "summary": "12 lines"},
        {"type": "assistant_token", "text": "Hello"},
        {"type": "assistant_token", "text": " world"},
        {"type": "done", "final": "Hello world"},
    ]
    buf = io.StringIO()
    result = render_stream(events, out=buf)
    rendered = buf.getvalue()

    assert result == "Hello world"          # the done event's "final" wins
    assert "● fs.read" in rendered           # tool_start card header
    assert "✓" in rendered and "12 lines" in rendered   # tool_result ok line
    assert "Hello" in rendered and "world" in rendered  # streamed tokens landed on the page


def test_render_stream_tool_result_not_ok_uses_cross_mark():
    events = [
        {"type": "tool_start", "name": "shell.exec"},
        {"type": "tool_result", "name": "shell.exec", "ok": False, "summary": "exit=1"},
    ]
    buf = io.StringIO()
    render_stream(events, out=buf)
    rendered = buf.getvalue()
    assert "✗" in rendered and "exit=1" in rendered
    assert "✓" not in rendered


def test_render_stream_ask_event_renders_prompt_line():
    events = [{"type": "ask", "prompt": "Which file did you mean?"}]
    buf = io.StringIO()
    render_stream(events, out=buf)
    assert "Which file did you mean?" in buf.getvalue()
    assert "?" in buf.getvalue()


def test_render_stream_cancel_event_renders_interrupted_note():
    events = [
        {"type": "assistant_token", "text": "partial"},
        {"type": "cancel"},
    ]
    buf = io.StringIO()
    result = render_stream(events, out=buf)
    assert "interrupted" in buf.getvalue()
    assert result == "partial"   # no "done" -> falls back to the joined tokens seen so far


def test_render_stream_thinking_indicator_shows_before_any_token():
    events = [{"type": "thinking"}, {"type": "thinking"}, {"type": "assistant_token", "text": "hi"}]
    buf = io.StringIO()
    render_stream(events, out=buf)
    rendered = buf.getvalue()
    assert "thinking" in rendered
    assert "hi" in rendered


def test_render_stream_no_done_event_falls_back_to_joined_tokens():
    events = [
        {"type": "assistant_token", "text": "foo"},
        {"type": "assistant_token", "text": "bar"},
    ]
    buf = io.StringIO()
    result = render_stream(events, out=buf)
    assert result == "foobar"


def test_render_stream_empty_event_list_returns_empty_string():
    buf = io.StringIO()
    assert render_stream([], out=buf) == ""
    assert buf.getvalue() == ""


def test_render_stream_never_raises_on_malformed_events():
    weird = [None, 42, "a string", {"no_type_key": True}, {}, {"type": "mystery"}]
    buf = io.StringIO()
    result = render_stream(weird, out=buf)   # must not raise
    assert isinstance(result, str)


def test_render_stream_never_raises_on_a_non_iterable():
    buf = io.StringIO()
    result = render_stream(None, out=buf)    # type: ignore[arg-type]
    assert result == ""


def test_render_stream_never_raises_when_out_is_broken():
    class _BrokenStream:
        def write(self, *_a, **_kw):
            raise OSError("broken pipe")

        def flush(self):
            raise OSError("broken pipe")

    events = [{"type": "assistant_token", "text": "hi"}, {"type": "done", "final": "hi"}]
    result = render_stream(events, out=_BrokenStream())   # must not raise
    assert result == "hi"


def test_render_stream_defaults_out_to_stdout(capsys):
    events = [{"type": "assistant_token", "text": "via stdout"}, {"type": "done", "final": "via stdout"}]
    result = render_stream(events)
    captured = capsys.readouterr()
    assert result == "via stdout"
    assert "via stdout" in captured.out


# =====================================================================================
# (c) harness.cli._try_stream_plain — degrades to None whenever streaming isn't usable
# =====================================================================================

class _StubCli:
    def __init__(self):
        self.llm = object()


def test_try_stream_plain_returns_none_when_solve_streaming_absent(monkeypatch):
    import harness.coding_loop as coding_loop
    import harness.cli as cli_mod

    monkeypatch.delattr(coding_loop, "solve_streaming", raising=False)
    assert cli_mod._try_stream_plain(_StubCli(), "fix the bug") is None


def test_try_stream_plain_returns_none_when_solve_streaming_raises(monkeypatch):
    import harness.coding_loop as coding_loop
    import harness.cli as cli_mod

    def _boom(request, *, llm=None, **kw):
        raise RuntimeError("not wired yet")

    monkeypatch.setattr(coding_loop, "solve_streaming", _boom, raising=False)
    assert cli_mod._try_stream_plain(_StubCli(), "fix the bug") is None


def test_try_stream_plain_renders_when_solve_streaming_stubbed(monkeypatch, capsys):
    import harness.coding_loop as coding_loop
    import harness.cli as cli_mod

    def _fake_solve_streaming(request, *, llm=None, **kw):
        assert request == "fix the bug"
        yield {"type": "assistant_token", "text": "on it"}
        yield {"type": "done", "final": "on it"}

    monkeypatch.setattr(coding_loop, "solve_streaming", _fake_solve_streaming, raising=False)
    result = cli_mod._try_stream_plain(_StubCli(), "fix the bug")
    assert result == "on it"
    assert "on it" in capsys.readouterr().out


def test_try_stream_plain_falls_back_when_signature_incompatible(monkeypatch):
    """A future TASK-2 signature that doesn't accept `llm=` as a keyword must not crash the
    REPL -- retried once with just the request; if that ALSO fails to work as a generator, this
    degrades to None (fallback), never an exception escaping to the caller."""
    import harness.coding_loop as coding_loop
    import harness.cli as cli_mod

    def _positional_only(request):
        raise TypeError("solve_streaming() got an unexpected keyword argument 'llm'")

    monkeypatch.setattr(coding_loop, "solve_streaming", _positional_only, raising=False)
    assert cli_mod._try_stream_plain(_StubCli(), "fix the bug") is None


# =====================================================================================
# (b) harness.cli.repl() — non-TTY fallback is byte-stable; slash dispatch retained
# =====================================================================================

class _StubSession:
    id = "sess-1"
    turns: "list" = []


class _RecordingStubCli:
    """Mirrors the surface `repl()` touches on a real `JcodeCli`, without any model/agent/tool
    machinery -- lets these tests assert exactly what `repl()` prints and calls, independent of
    everything `JcodeCli.__init__` would otherwise need (llm client, hooks, permissions, ...)."""

    def __init__(self, session_id=None, stream=False, interactive=False):
        self.model = "stub-model"
        self.session = _StubSession()
        self.stream = stream
        self._show_statusline = False
        self.llm = object()
        self.handled: "list[str]" = []

    def handle(self, line, *, interactive=False):
        assert interactive is True
        self.handled.append(line)
        return f"handled:{line}"

    def on_stop(self):
        pass


def _run_repl_with_scripted_input(monkeypatch, lines, *, is_tty):
    """Drive `harness.cli.repl()` with a scripted list of `input()` returns, ending the session
    on an `EOFError` once the script is exhausted. Returns (printed_stdout, stub_cli)."""
    import harness.cli as cli_mod

    stub = _RecordingStubCli()
    monkeypatch.setattr(cli_mod, "JcodeCli", lambda **kw: stub)
    monkeypatch.setattr(cli_mod, "_stdout_is_tty", lambda: is_tty)

    remaining = list(lines)

    def _fake_input(_prompt=""):
        if not remaining:
            raise EOFError()
        return remaining.pop(0)

    monkeypatch.setattr("builtins.input", _fake_input)
    code = cli_mod.repl()
    assert code == 0
    return stub


def test_repl_non_tty_plain_input_falls_back_to_run_command_interruptible(monkeypatch, capsys):
    """The defining non-TTY guarantee: a plain (non-slash) line on a non-TTY/piped run is
    handled by the SAME path as before this spec -- `cli.handle(line, interactive=True)` via
    `_run_command_interruptible` -- never `_try_stream_plain`/`solve_streaming`/`render_stream`.
    A poisoned `solve_streaming` that raises if ever called proves it is never even attempted."""
    import harness.coding_loop as coding_loop

    def _poison(*_a, **_kw):
        raise AssertionError("solve_streaming must NEVER be called on a non-TTY run")

    monkeypatch.setattr(coding_loop, "solve_streaming", _poison, raising=False)

    stub = _run_repl_with_scripted_input(monkeypatch, ["fix the bug in foo.py"], is_tty=False)

    assert stub.handled == ["fix the bug in foo.py"]   # cli.handle() ran, exactly once
    printed = capsys.readouterr().out
    assert "handled:fix the bug in foo.py" in printed
    # no streaming-render artifacts (tool cards / spinner) leaked into the byte-stable output
    assert "●" not in printed


def test_repl_tty_streaming_plain_input_uses_render_stream_when_available(monkeypatch, capsys):
    """On a TTY with a working `solve_streaming` stub, a plain line is rendered live and
    `cli.handle()` is NOT invoked for that line -- the new path replaces the old one for the
    lines it can actually handle."""
    import harness.coding_loop as coding_loop

    def _fake_solve_streaming(request, *, llm=None, **kw):
        yield {"type": "tool_start", "name": "fs.read"}
        yield {"type": "tool_result", "name": "fs.read", "ok": True, "summary": "3 lines"}
        yield {"type": "assistant_token", "text": "fixed it"}
        yield {"type": "done", "final": "fixed it"}

    monkeypatch.setattr(coding_loop, "solve_streaming", _fake_solve_streaming, raising=False)

    stub = _run_repl_with_scripted_input(monkeypatch, ["fix the bug in foo.py"], is_tty=True)

    assert stub.handled == []              # NOT routed through cli.handle() for this line
    printed = capsys.readouterr().out
    assert "● fs.read" in printed
    assert "fixed it" in printed


def test_repl_slash_command_always_uses_existing_dispatch_even_on_tty(monkeypatch, capsys):
    """A `/`-prefixed line ALWAYS takes the existing slash dispatch (`cli.handle` via
    `_run_command_interruptible`), even when the terminal is a TTY and streaming is available --
    the new streamed path is for plain natural-language input only."""
    import harness.coding_loop as coding_loop

    def _poison(*_a, **_kw):
        raise AssertionError("solve_streaming must NEVER be called for a slash command")

    monkeypatch.setattr(coding_loop, "solve_streaming", _poison, raising=False)

    stub = _run_repl_with_scripted_input(monkeypatch, ["/help"], is_tty=True)

    assert stub.handled == ["/help"]
    assert "handled:/help" in capsys.readouterr().out


def test_repl_banner_invites_natural_language(monkeypatch, capsys):
    _run_repl_with_scripted_input(monkeypatch, [], is_tty=False)
    printed = capsys.readouterr().out
    assert "Ask me to build, fix, or explain" in printed
    assert "/help" in printed


def test_repl_quit_and_clear_still_work(monkeypatch, capsys):
    stub = _run_repl_with_scripted_input(monkeypatch, ["/clear", "/quit"], is_tty=False)
    assert stub.handled == []   # neither /clear nor /quit ever reaches cli.handle()
    printed = capsys.readouterr().out
    assert "\033[2J\033[H" in printed   # /clear's escape sequence was emitted
# #EXT-057-REQ-3 End
