"""Streaming tool-event presentation for the interactive/one-shot CLI (EXT-045 REQ-1).

WHY: `docs/GAP-MAP.md` Product-surface parity row #24 names Claude Code's live, streaming
terminal feel -- you see each tool call as it happens, not just the final answer after a long
silent wait. jaros-code already logs every accepted `Decision` to the Jaros hash-chain
(`jaros.state.DecisionLog`, via `harness.coding_loop.Runtime.apply`'s `record_decision` call) --
this module is PURE PRESENTATION over that same seam: it formats a concise, human-readable line
for a tool CALL (before execution) and its RESULT (after execution), and decides whether
streaming should be active for a given invocation.

Two-plane discipline (Tenet 1): no model calls here, only deterministic string formatting over
already-produced Decision/outcome data. Never raises (Tenet 3's observability precedent, see
`harness/heartbeat.py`) -- a broken/malformed event degrades to "no line printed", never a crash
that could take down the tool call it is merely narrating.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Callable, Iterable

# #EXT-045-REQ-1 Start
# The event dict shape this module consumes: {"phase": "call"|"result"|"error", "type": str,
# "payload": dict, "output": Any, "reason": str, "source": str}. Every key is optional except
# "phase" -- any event missing "phase" (or with an unrecognized one) renders to no line.
_ARROW = "→"   # ->  (call)
_CHECK = "✓"   # OK  (result)
_CROSS = "✗"   # X   (error)

# Payload keys checked (in priority order) for a short, human-meaningful call argument.
_ARG_KEYS = ("path", "pattern", "command", "message", "old", "symbol", "action")


def _compact_payload(payload: Any) -> str:
    """Best-effort ONE-LINE summary of a Decision payload for the call line. Never raises."""
    try:
        if not isinstance(payload, dict):
            return ""
        for key in _ARG_KEYS:
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:80]
        # Fallback: first scalar value, if any.
        for val in payload.values():
            if isinstance(val, (str, int, float, bool)):
                return str(val)[:80]
        return ""
    except Exception:
        return ""


def format_call(type_: str, payload: Any) -> str:
    """``-> fs.read(foo.py)``-style line for a tool CALL. Never raises."""
    try:
        arg = _compact_payload(payload)
        return f"{_ARROW} {type_}({arg})" if arg else f"{_ARROW} {type_}()"
    except Exception:
        return f"{_ARROW} {type_}"


def format_result(type_: str, output: Any) -> str:
    """``OK 42 lines``-style line for a tool RESULT. Best-effort per known tool-output shapes;
    falls back to a generic ``done`` when the shape isn't recognized. Never raises."""
    try:
        if isinstance(output, dict):
            if "matches" in output:
                n = len(output.get("matches") or [])
                return f"{_CHECK} {n} match(es)"
            if "entries" in output:
                n = len(output.get("entries") or [])
                return f"{_CHECK} {n} entr{'y' if n == 1 else 'ies'}"
            if "symbols" in output:
                n = len(output.get("symbols") or [])
                return f"{_CHECK} {n} symbol(s)"
            if "content" in output:
                content = output.get("content") or ""
                n = len(content.splitlines()) if content else 0
                return f"{_CHECK} {n} line(s)"
            if "exitCode" in output:
                return f"{_CHECK} exit={output.get('exitCode')}"
            if "committed" in output:
                return f"{_CHECK} {'committed' if output.get('committed') else 'not committed'}"
            if "bytesAfter" in output:
                return f"{_CHECK} {output.get('bytesAfter')} bytes"
        return f"{_CHECK} done"
    except Exception:
        return f"{_CHECK} done"


def format_error(type_: str, reason: str) -> str:
    """``X fs.read failed: <reason>``-style line for a rejected/failed tool call."""
    try:
        return f"{_CROSS} {type_} failed: {reason}"
    except Exception:
        return f"{_CROSS} {type_} failed"


def render_event(event: Any) -> "str | None":
    """One event dict -> one formatted line, or ``None`` for an unrecognized/malformed event.
    Never raises."""
    try:
        if not isinstance(event, dict):
            return None
        phase = event.get("phase")
        type_ = str(event.get("type", "?"))
        if phase == "call":
            return format_call(type_, event.get("payload"))
        if phase == "result":
            return format_result(type_, event.get("output"))
        if phase == "error":
            return format_error(type_, str(event.get("reason", "")))
        return None
    except Exception:
        return None


def stream_events(events: "Iterable[Any]") -> "list[str]":
    """Map a SEQUENCE of already-logged tool events to their formatted lines, in order,
    skipping anything malformed. Never raises -- an unparseable stream degrades to whatever
    lines it could render (possibly none), never an exception."""
    out: "list[str]" = []
    try:
        for ev in events:
            line = render_event(ev)
            if line:
                out.append(line)
    except Exception:
        pass
    return out


def should_stream(output_format: str, is_tty: bool, env: "dict | None" = None) -> bool:
    """Decide whether tool-event streaming should be active for this invocation.

    - NEVER active under ``--output-format json`` (EXT-043): machine output must stay a single
      clean parseable object, never interleaved with narration lines.
    - ``JCODE_STREAM_EVENTS`` explicitly forces it on (``1``/``true``/``on``/``yes``) or off
      (``0``/``false``/``off``/``no``), overriding the TTY default either way.
    - Otherwise defaults to ``is_tty`` (a live terminal gets the live feel; a piped/redirected
      run stays quiet unless asked) -- this is the "default-on but suppressed when not a TTY
      unless asked" behavior named in EXT-045.

    Never raises -- any lookup failure degrades to ``False`` (the conservative, silent default).
    """
    try:
        if str(output_format).strip().lower() == "json":
            return False
        env = env if env is not None else os.environ
        override = str(env.get("JCODE_STREAM_EVENTS", "")).strip().lower()
        if override in ("0", "false", "off", "no"):
            return False
        if override in ("1", "true", "on", "yes"):
            return True
        return bool(is_tty)
    except Exception:
        return False


def make_printer(stream: Any = None) -> "Callable[[dict], None]":
    """Build an ``on_event`` callback (for ``harness.coding_loop.Runtime``) that prints each
    renderable event as a single line to ``stream`` (defaults to ``sys.stdout``). Never raises --
    a broken stream/event degrades to "no line printed", never a crash that could break the tool
    call it is only narrating."""
    def _emit(event: dict) -> None:
        try:
            line = render_event(event)
            if line:
                print(line, file=stream if stream is not None else sys.stdout, flush=True)
        except Exception:
            pass
    return _emit
# #EXT-045-REQ-1 End
