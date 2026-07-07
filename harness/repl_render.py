"""EXT-057 REQ-3: live REPL rendering of the stream-bus event vocabulary.

WHY: the REPL today runs a command silently and dumps the whole result at once
(``out = _run_command_interruptible(cli, line); print(out)`` in ``harness/cli.py``) -- the
single biggest felt-experience gap versus Claude Code (see ``.jarify/EXT-057/design.md``'s
"felt-experience gap"). ``render_stream`` is the L4 presentation layer over the L3 stream bus
(``harness/stream_bus.py``, TASK-2) + L2 event-yielding solve path (``coding_loop.solve_streaming``,
TASK-2): it consumes an ORDERED sequence of already-produced bus events and renders them live --
assistant text streamed inline as it arrives, a tool card per ``tool_start``/``tool_result`` pair,
a working indicator while the model is thinking with no token yet, an ``ask`` prompt line, and an
honest interrupted note on ``cancel``.

This module is deliberately standalone: it does NOT import ``coding_loop`` or ``stream_bus`` (both
owned by a concurrently-built task) -- it only consumes the ``dict`` event shape documented in the
EXT-057 SHARED INTERFACE CONTRACT (``.jarify/EXT-057/tasks.md``), so it is fully unit-testable
against a synthetic event list today, and will integrate unchanged once TASK-2 lands.

Two-plane discipline (Tenet 1): pure presentation over already-produced event data -- no model
call, no host side effect, here. Never raises (mirrors ``harness/tool_stream.py``'s presentation
discipline): a malformed event or a broken ``out`` writer degrades to "render what we can", never
a crash that could take down the render of everything that follows it.
"""
from __future__ import annotations

import sys
from typing import Any, Iterable, TextIO

# #EXT-057-REQ-3 Start
_DOT = "●"      # ●  tool_start card header
_CHECK = "✓"    # ✓  tool_result ok
_CROSS = "✗"    # ✗  tool_result not ok
_WARN = "⚠"     # ⚠  cancel / interrupted note
_SPINNER_FRAMES = ("|", "/", "-", "\\")   # ASCII-safe rotating "thinking" indicator


def _write(out: "TextIO | None", text: str) -> None:
    """Best-effort write -- a broken/``None`` writer must never crash the render loop (a
    presentation failure must never break the underlying result, Tenet 3)."""
    if out is None:
        return
    try:
        out.write(text)
        flush = getattr(out, "flush", None)
        if flush is not None:
            flush()
    except Exception:
        pass


def render_stream(events: "Iterable[Any]", out: "TextIO | None" = None) -> str:
    """Consume an ordered stream-bus event sequence (the EXT-057 SHARED CONTRACT vocabulary) and
    render it LIVE to ``out`` (defaults to ``sys.stdout``):

      - ``assistant_token`` -- the model's text (``"text"``), streamed inline, token by token,
        as it arrives -- this is what kills the silent-black-box wait.
      - ``tool_start``      -- a tool card header: ``● <name>``.
      - ``tool_result``     -- the card's outcome line: ``  ✓ <summary>`` when ``"ok"`` is
        truthy, ``  ✗ <summary>`` otherwise.
      - ``thinking``        -- a rotating spinner/working indicator while the model has no token
        yet; cleared as soon as any other event follows.
      - ``ask``             -- a mid-task clarifying-question prompt line (``? <prompt>``).
      - ``cancel``          -- an honest "interrupted" note (EXT-055 cooperative cancel).
      - ``done``            -- ends the render; its ``"final"`` field, when present, becomes the
        returned text.

    Returns the assembled final text: the ``done`` event's ``"final"`` string when one was seen,
    otherwise the concatenation of every ``assistant_token`` text seen (so a stream that never
    emits ``done`` -- e.g. a partial/stubbed event list -- still returns something honest rather
    than an empty string).

    Never raises: a malformed/unrecognized event is skipped and rendering continues; any writer
    failure degrades to "nothing printed" for that write, never a crash (same discipline as
    ``harness/tool_stream.py``)."""
    if out is None:
        out = sys.stdout
    tokens: "list[str]" = []
    final_text: "str | None" = None
    indicator_on = False
    spin_i = 0

    def _clear_indicator() -> None:
        nonlocal indicator_on
        if indicator_on:
            _write(out, "\r \r")
            indicator_on = False

    try:
        iterator = iter(events)
    except TypeError:
        iterator = iter(())

    while True:
        try:
            event = next(iterator)
        except StopIteration:
            break
        except Exception:
            break
        try:
            if not isinstance(event, dict):
                continue
            etype = event.get("type")
            if etype == "assistant_token":
                _clear_indicator()
                text = event.get("text")
                if isinstance(text, str) and text:
                    tokens.append(text)
                    _write(out, text)
            elif etype == "tool_start":
                _clear_indicator()
                name = event.get("name") or "?"
                _write(out, f"\n{_DOT} {name}\n")
            elif etype == "tool_result":
                _clear_indicator()
                ok = event.get("ok", True)
                summary = event.get("summary") or ("done" if ok else "failed")
                mark = _CHECK if ok else _CROSS
                _write(out, f"  {mark} {summary}\n")
            elif etype == "thinking":
                frame = _SPINNER_FRAMES[spin_i % len(_SPINNER_FRAMES)]
                spin_i += 1
                _write(out, f"\r{frame} thinking…")
                indicator_on = True
            elif etype == "ask":
                _clear_indicator()
                prompt = event.get("prompt") or ""
                _write(out, f"\n? {prompt}\n")
            elif etype == "cancel":
                _clear_indicator()
                _write(out, f"\n{_WARN} interrupted\n")
            elif etype == "done":
                _clear_indicator()
                final = event.get("final")
                if isinstance(final, str):
                    final_text = final
                _write(out, "\n")
            # any other/unrecognized "type" is silently skipped -- forward-compatible with a
            # bus vocabulary that grows without this renderer crashing on the new event.
        except Exception:
            continue

    if final_text is not None:
        return final_text
    return "".join(tokens)
# #EXT-057-REQ-3 End
