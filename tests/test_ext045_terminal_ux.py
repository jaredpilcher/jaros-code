"""EXT-045: Terminal UX -- streaming tool events + statusline.

OFFLINE -- no live model. Streaming/statusline are pure presentation over ALREADY-LOGGED
Decision data (the same seam `harness.coding_loop.Runtime.apply` uses to record each accepted
Decision to the Jaros hash-chain, `jaros.state.record_decision`); nothing here calls an LLM.

Covers:
  - `harness.tool_stream`: pure event -> line formatting, `should_stream` gating (suppressed
    under --output-format json / non-TTY, `JCODE_STREAM_EVENTS` override either way), and
    `make_printer`'s never-raises behavior on malformed events.
  - `harness.statusline.statusline`: model + $0 + latency fields, never raises.
  - `harness.coding_loop.Runtime`'s new opt-in `on_event` hook: emits call/result/error events,
    in order, at the SAME seam that already records the decision -- exercised end-to-end with a
    REAL (deterministic) fs.read Decision, no model involved.
  - `harness.cli.JcodeCli`: `stream=` opt-in wiring (default OFF -> byte-identical), the
    `/statusline` toggle command, and `/help` listing the new surface.
"""
from __future__ import annotations

import io
import json
import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from jaros.core import create_decision

from harness import tool_stream
from harness.statusline import statusline


# =====================================================================================
# harness.tool_stream -- pure formatting (synthetic events, no model)
# =====================================================================================

def test_format_call_uses_the_most_meaningful_payload_field():
    line = tool_stream.format_call("fs.read", {"path": "foo.py"})
    assert line == "→ fs.read(foo.py)"


def test_format_call_empty_payload_still_renders():
    line = tool_stream.format_call("shell.exec", {})
    assert line == "→ shell.exec()"


def test_format_result_recognizes_known_output_shapes():
    assert "match" in tool_stream.format_result("fs.grep", {"matches": [1, 2, 3]})
    assert "3" in tool_stream.format_result("fs.grep", {"matches": [1, 2, 3]})
    assert "entr" in tool_stream.format_result("fs.list", {"entries": [1, 2]})
    assert "line" in tool_stream.format_result("fs.read", {"content": "a\nb\nc"})
    assert "exit=0" in tool_stream.format_result("shell.exec", {"exitCode": 0})


def test_format_result_falls_back_to_done_for_unknown_shape():
    assert tool_stream.format_result("some.tool", {"weird": True}) == "✓ done"
    assert tool_stream.format_result("some.tool", None) == "✓ done"
    assert tool_stream.format_result("some.tool", "a plain string") == "✓ done"


def test_format_error_includes_type_and_reason():
    line = tool_stream.format_error("fs.read", "not found")
    assert "fs.read" in line and "not found" in line


def test_render_event_dispatches_by_phase():
    call = tool_stream.render_event({"phase": "call", "type": "fs.read", "payload": {"path": "x.py"}})
    result = tool_stream.render_event({"phase": "result", "type": "fs.read", "output": {"content": "a\n"}})
    error = tool_stream.render_event({"phase": "error", "type": "fs.read", "reason": "boom"})
    assert call.startswith("→")
    assert result.startswith("✓")
    assert error.startswith("✗")


def test_render_event_unrecognized_phase_is_none():
    assert tool_stream.render_event({"phase": "mystery", "type": "x"}) is None
    assert tool_stream.render_event({"type": "x"}) is None  # no phase at all


# --- streaming renders a concise line per tool event, IN ORDER ----------------------------

def test_stream_events_renders_call_then_result_in_order():
    events = [
        {"phase": "call", "type": "fs.read", "payload": {"path": "foo.py"}},
        {"phase": "result", "type": "fs.read", "output": {"content": "a\nb\n"}},
        {"phase": "call", "type": "fs.grep", "payload": {"pattern": "TODO"}},
        {"phase": "result", "type": "fs.grep", "output": {"matches": []}},
    ]
    lines = tool_stream.stream_events(events)
    assert len(lines) == 4
    assert lines[0] == "→ fs.read(foo.py)"
    assert "2 line" in lines[1]
    assert lines[2] == "→ fs.grep(TODO)"
    assert "0 match" in lines[3]


# --- never-raises on empty/malformed event streams ------------------------------------------

def test_stream_events_never_raises_on_empty_stream():
    assert tool_stream.stream_events([]) == []


def test_stream_events_never_raises_on_malformed_events():
    weird = [None, 42, "a string", {"phase": "call"}, {"no_phase_key": True}, {}]
    lines = tool_stream.stream_events(weird)   # must not raise; malformed entries render no line
    assert isinstance(lines, list)


def test_stream_events_never_raises_on_a_non_iterable():
    assert tool_stream.stream_events(None) == []  # type: ignore[arg-type]


def test_render_event_never_raises_on_non_dict():
    assert tool_stream.render_event(None) is None
    assert tool_stream.render_event(12345) is None
    assert tool_stream.render_event("oops") is None


# --- should_stream: suppressed under json / non-TTY, overridable -----------------------------

def test_should_stream_false_under_json_even_if_tty():
    assert tool_stream.should_stream("json", True) is False


def test_should_stream_false_under_json_even_with_force_on_env():
    assert tool_stream.should_stream("json", True, env={"JCODE_STREAM_EVENTS": "1"}) is False


def test_should_stream_defaults_to_tty():
    assert tool_stream.should_stream("text", True, env={}) is True
    assert tool_stream.should_stream("text", False, env={}) is False


def test_should_stream_env_override_forces_on_even_without_tty():
    assert tool_stream.should_stream("text", False, env={"JCODE_STREAM_EVENTS": "1"}) is True


def test_should_stream_env_override_forces_off_even_with_tty():
    assert tool_stream.should_stream("text", True, env={"JCODE_STREAM_EVENTS": "0"}) is False


def test_should_stream_never_raises_on_garbage():
    assert tool_stream.should_stream(None, "not-a-bool", env=None) in (True, False)


# --- make_printer: prints renderable lines, never raises --------------------------------------

def test_make_printer_prints_rendered_lines_to_given_stream():
    buf = io.StringIO()
    emit = tool_stream.make_printer(stream=buf)
    emit({"phase": "call", "type": "fs.read", "payload": {"path": "a.py"}})
    emit({"phase": "result", "type": "fs.read", "output": {"content": "x\n"}})
    out = buf.getvalue()
    assert "→ fs.read(a.py)" in out
    assert "✓" in out


def test_make_printer_never_raises_on_malformed_event():
    buf = io.StringIO()
    emit = tool_stream.make_printer(stream=buf)
    emit(None)          # must not raise
    emit("garbage")      # must not raise
    emit({"phase": "unknown"})
    assert buf.getvalue() == ""   # nothing renderable -> nothing printed


def test_make_printer_never_raises_when_stream_is_broken():
    class _BrokenStream:
        def write(self, *_a, **_kw):
            raise OSError("broken pipe")

        def flush(self):
            raise OSError("broken pipe")

    emit = tool_stream.make_printer(stream=_BrokenStream())
    emit({"phase": "call", "type": "fs.read", "payload": {"path": "a.py"}})   # must not raise


# =====================================================================================
# harness.statusline.statusline -- model + $0 + latency, never raises
# =====================================================================================

def test_statusline_contains_model_cost_and_latency():
    line = statusline("gemma-4-e2b", "fix", 1.234)
    assert "gemma-4-e2b" in line
    assert "$0" in line
    assert "1.23s" in line


def test_statusline_unknown_latency_renders_a_placeholder():
    line = statusline("gemma-4-e2b", "-", None)
    assert "gemma-4-e2b" in line
    assert "$0" in line
    assert line.strip().endswith("-")


def test_statusline_never_raises_on_garbage_inputs():
    line = statusline(None, None, "not-a-number")
    assert isinstance(line, str) and line.strip()
    line2 = statusline(12345, object(), -1)   # negative latency -> treated as unknown
    assert isinstance(line2, str) and "$0" in line2


# =====================================================================================
# harness.coding_loop.Runtime -- on_event hook, exercised with a REAL deterministic decision
# =====================================================================================

def test_runtime_on_event_emits_call_then_result_for_a_real_fs_read(tmp_path):
    from harness.coding_loop import Runtime

    target = tmp_path / "hello.txt"
    target.write_text("line one\nline two\n", encoding="utf-8")

    events = []
    rt = Runtime(data_dir=tmp_path / "state", on_event=events.append)
    d = create_decision(id="t1", source="test", type="fs.read", payload={"path": str(target)})
    out = rt.apply(d)

    assert out["content"] == "line one\nline two\n"
    phases = [e["phase"] for e in events]
    assert phases == ["call", "result"]
    assert events[0]["type"] == "fs.read"
    assert events[0]["payload"]["path"] == str(target)
    assert events[1]["output"]["content"] == "line one\nline two\n"

    # And it renders to real narration lines via the same formatter the printer uses (the
    # payload's full path may be truncated for concision on a long tmp path -- what matters is
    # the call/result SHAPE, already asserted precisely on the raw events above):
    lines = tool_stream.stream_events(events)
    assert lines[0].startswith("→ fs.read(")
    assert "2 line" in lines[1]


def test_runtime_on_event_emits_error_on_gate_rejection(tmp_path):
    """A write OUTSIDE a root-jailed Runtime's root is gate-rejected (EXT-037) -- on_event must
    still fire an honest 'error' event, not silently swallow the rejection."""
    from harness.coding_loop import Runtime

    proj = tmp_path / "proj"
    proj.mkdir()
    outside = tmp_path / "outside.py"

    events = []
    rt = Runtime(data_dir=tmp_path / "state", root=str(proj), on_event=events.append)
    d = create_decision(id="t2", source="test", type="code.write_file",
                        payload={"path": str(outside), "content": "leak\n"})
    with pytest.raises(RuntimeError):
        rt.apply(d)

    phases = [e["phase"] for e in events]
    assert "call" in phases
    assert "error" in phases


def test_runtime_with_no_on_event_is_byte_identical_to_before(tmp_path):
    """Backward-compat: `Runtime(...)` with no `on_event` (the pre-EXT-045 call shape) behaves
    exactly as before -- no crash, no behavior change, from the mere PRESENCE of the new hook."""
    from harness.coding_loop import Runtime

    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    rt = Runtime(data_dir=tmp_path / "state")
    d = create_decision(id="t3", source="test", type="fs.read", payload={"path": str(target)})
    out = rt.apply(d)
    assert out["content"] == "hi\n"


# =====================================================================================
# harness.cli.JcodeCli -- stream= wiring, /statusline, /help
# =====================================================================================

def test_cli_default_stream_is_off_no_extra_stdout(tmp_path, monkeypatch, capsys):
    """A plain run (stream=False, the default) prints EXACTLY what /help would have printed
    before this spec -- no interleaved call/result narration lines."""
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.stream is False
    out = cli.dispatch("/help")
    captured = capsys.readouterr()
    assert captured.out == ""            # dispatch() never prints on its own
    assert "/help" in out                 # help still returns its normal text


def test_cli_stream_true_narrates_a_real_tool_dispatch(tmp_path, monkeypatch, capsys):
    """With stream=True, a real deterministic tool dispatch (/read) narrates call+result lines
    to stdout AS IT HAPPENS, in addition to (not instead of) its normal return value."""
    from harness.cli import JcodeCli

    f = tmp_path / "a.txt"
    f.write_text("one\ntwo\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli(stream=True)
    out = cli.dispatch("/read a.txt")
    printed = capsys.readouterr().out
    assert "one\ntwo\n" in out            # the command's own return value is unchanged
    assert "→ fs.read" in printed    # AND the call was narrated to stdout
    assert "✓" in printed            # AND the result was narrated to stdout


def test_cmd_statusline_toggle_and_render(tmp_path, monkeypatch):
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli._show_statusline is False
    out_on = cli.cmd_statusline("on")
    assert cli._show_statusline is True
    assert "statusline: on" in out_on
    assert cli.model in out_on
    assert "$0" in out_on

    out_off = cli.cmd_statusline("off")
    assert cli._show_statusline is False
    assert "statusline: off" in out_off


def test_cli_statusline_method_reflects_last_action_and_latency(tmp_path, monkeypatch):
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    cli.dispatch("/help")   # a slash dispatch does not itself update _last_action (only handle() does)
    # Directly exercise the statusline() surface with handle()-populated state:
    cli._last_action = "read"
    cli._last_latency_s = 0.05
    line = cli.statusline()
    assert cli.model in line
    assert "read" in line
    assert "$0" in line


def test_help_lists_statusline_command():
    from harness.cli import JcodeCli

    cli = JcodeCli.__new__(JcodeCli)   # avoid full __init__ -- /help needs no runtime state
    out = cli.cmd_help("")
    assert "/statusline" in out


# --- --output-format json stays byte-clean under streaming (cross-checked with EXT-043) -----

def test_output_format_json_suppresses_streaming_end_to_end(monkeypatch, capsys):
    """main() with --output-format json must emit ONE clean parseable JSON line on stdout --
    never interleaved with tool-event narration -- even though a stub JcodeCli would otherwise
    be free to stream."""
    import harness.cli as cli_mod

    class _StubCli:
        model = "stub-model"
        last_stream = None

        def __init__(self, session_id=None, stream=False):
            _StubCli.last_stream = stream

        def handle(self, request):
            return "stub response"

        def on_stop(self):  # EXT-047: one-shot path fires Stop hooks via cli.on_stop()
            pass

    monkeypatch.setattr(cli_mod, "JcodeCli", _StubCli)
    monkeypatch.setattr("sys.argv", ["harness.cli", "--output-format", "json", "do", "thing"])
    monkeypatch.setattr(cli_mod, "_stdout_is_tty", lambda: True)   # even on a "live terminal"...
    code = cli_mod.main()
    assert code == 0
    assert _StubCli.last_stream is False   # ...streaming must resolve to OFF under json
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)                  # still a single clean parseable JSON object
    assert obj["response"] == "stub response"


def test_stdout_is_tty_never_raises(monkeypatch):
    from harness.cli import _stdout_is_tty

    class _Boom:
        def isatty(self):
            raise OSError("boom")

    monkeypatch.setattr("sys.stdout", _Boom())
    assert _stdout_is_tty() is False
