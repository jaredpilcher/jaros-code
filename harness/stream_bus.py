"""EXT-057 REQ-2 — the stream-bus event vocabulary for the interactive REPL.

A single ordered event stream unifies the two things a Claude-Code-grade REPL must show LIVE: the
model's output as it is generated (``assistant_token``) and each tool/Decision as it fires
(``tool_start``/``tool_result`` — sourced from the existing EXT-045 ``Runtime.on_event`` seam, NOT a
new side-effect path, so Tenet 1 is preserved). ``coding_loop.solve_streaming`` (REQ-2) YIELDS these
events; ``repl_render.render_stream`` (REQ-3) consumes and renders them. This module is pure data —
dict factories + a validator — with NO I/O and NO model call, so it is trivially testable and can be
imported by both the producer and the renderer without a dependency cycle.
"""
# #EXT-057-REQ-2 Start
from __future__ import annotations

EVENT_TYPES = (
    "assistant_token",  # a chunk of the model's streamed output ({"text": str})
    "tool_start",       # a Decision/tool began ({"name": str})
    "tool_result",      # a Decision/tool finished ({"name": str, "ok": bool, "summary": str})
    "thinking",         # the model is working with no token yet ({"text": str}) -> spinner
    "ask",              # a mid-task clarifying question ({"prompt": str}) -> EXT-036 REQ-8
    "done",             # the turn is complete ({"final": str})
    "cancel",           # cooperative interrupt honored ({"reason": str}) -> EXT-055
)


def assistant_token(text: str) -> dict:
    """A chunk of the model's streamed output."""
    return {"type": "assistant_token", "text": str(text)}


def tool_start(name: str) -> dict:
    """A tool/Decision began executing."""
    return {"type": "tool_start", "name": str(name)}


def tool_result(name: str, ok: bool = True, summary: str = "") -> dict:
    """A tool/Decision finished; ``ok`` False renders as a failure, ``summary`` is a short line."""
    return {"type": "tool_result", "name": str(name), "ok": bool(ok), "summary": str(summary)}


def thinking(text: str = "") -> dict:
    """The model is working but has emitted no token yet -> a working/thinking indicator."""
    return {"type": "thinking", "text": str(text)}


def ask(prompt: str) -> dict:
    """A mid-task clarifying question surfaced to the user (EXT-036 REQ-8)."""
    return {"type": "ask", "prompt": str(prompt)}


def done(final: str = "") -> dict:
    """The turn is complete; ``final`` is the full assembled response text."""
    return {"type": "done", "final": str(final)}


def cancel(reason: str = "interrupted") -> dict:
    """A cooperative interrupt was honored (EXT-055)."""
    return {"type": "cancel", "reason": str(reason)}


def is_valid(event) -> bool:
    """True iff ``event`` is a dict with a known ``type``. Never raises — a malformed event is
    simply invalid (the renderer skips it) rather than crashing the whole stream."""
    try:
        return isinstance(event, dict) and event.get("type") in EVENT_TYPES
    except Exception:
        return False
# #EXT-057-REQ-2 End
