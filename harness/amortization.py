"""Amortization-ratio telemetry instrument (EXT-005 REQ-14).

THE PURSUIT scoreboard instrument #5 (PRIME-001 intent): the amortization ratio shows
how the $250 device amortizes its cost — how much VERIFIED work is REUSED (free, a
memory/cache/flywheel hit) versus freshly COMPUTED (a live model call). Ratio ~0 means
every request pays full inference cost (no reuse); ratio rising means captured verified
solves are being reused, so the same hardware compounds.

This module is a pure, deterministic, self-contained MEASUREMENT instrument. It makes
no model calls and does not itself add caching or reuse — it only tags and counts
events supplied by callers. Wiring real serve paths (the solution store, caches, the
flywheel) to actually call `record_event` is an explicit follow-up (EXT-005 TASK-9
Step 3); until that wiring lands, the live ratio is honestly expected to be ~0 because
verified-solution reuse elsewhere in the harness is still largely unwired (Tenet 3 —
do not fabricate a non-zero number to look better).

Event sources:
    MEMORY_HIT  — a reused verified artifact (solution-store / cache hit); free, no
                  fresh inference was needed.
    MODEL_CALL  — a fresh inference call actually ran.

Any other `source` value is still recorded (never dropped/raised on) but is not counted
toward `memory_hits` or `model_calls` in the ratio — it is surfaced as `other` so callers
never lose data, and so a typo'd source can't silently masquerade as a hit or a call.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".jaros-data" / "artifacts" / "amortization"
JSONL_SINK = ARTIFACTS / "events.jsonl"

MEMORY_HIT = "MEMORY_HIT"
MODEL_CALL = "MODEL_CALL"

# #EXT-005-REQ-14 Start
_EVENTS: list[dict[str, Any]] = []


def record_event(
    source: Any,
    *,
    kind: Any = None,
    tokens: Any = None,
    meta: Any = None,
    sink: Path | None = JSONL_SINK,
) -> dict[str, Any]:
    """Append one serve/solve event to the in-process log (and, best-effort, a JSONL sink).

    Never raises: a garbage `source`, an unserializable `meta`, or a sink write failure
    are all tolerated so telemetry can never crash a real serve/solve path. Returns the
    recorded event dict (always well-formed) regardless of what was passed in.
    """
    try:
        src = str(source) if source is not None else "UNKNOWN"
    except Exception:
        src = "UNKNOWN"

    try:
        tok = int(tokens) if tokens is not None else None
    except Exception:
        tok = None

    event: dict[str, Any] = {
        "source": src,
        "kind": kind if isinstance(kind, (str, int, float, bool)) or kind is None else str(kind),
        "tokens": tok,
        "ts": time.time(),
    }

    # meta must be JSON-serializable; fall back to a string repr, never raise.
    if meta is None:
        event["meta"] = None
    else:
        try:
            json.dumps(meta)
            event["meta"] = meta
        except Exception:
            try:
                event["meta"] = str(meta)
            except Exception:
                event["meta"] = None

    _EVENTS.append(event)

    if sink is not None:
        try:
            sink.parent.mkdir(parents=True, exist_ok=True)
            with open(sink, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")
        except Exception:
            pass  # telemetry must never break the caller

    return event


def amortization_ratio(events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compute the amortization ratio over `events` (default: the in-process log).

    Returns a well-formed dict; never raises. `total` counts only recognized sources
    (`MEMORY_HIT`/`MODEL_CALL`); unrecognized sources are reported separately as
    `other` and excluded from the ratio so a typo can never inflate or deflate it.
    """
    evs = events if events is not None else _EVENTS

    memory_hits = 0
    model_calls = 0
    other = 0
    tokens_memory = 0
    tokens_model = 0
    have_tokens = True

    try:
        for ev in evs:
            try:
                src = ev.get("source") if isinstance(ev, dict) else None
            except Exception:
                src = None

            tok = None
            if isinstance(ev, dict):
                tok = ev.get("tokens")
            if not isinstance(tok, (int, float)):
                have_tokens = False
                tok = 0

            if src == MEMORY_HIT:
                memory_hits += 1
                tokens_memory += tok
            elif src == MODEL_CALL:
                model_calls += 1
                tokens_model += tok
            else:
                other += 1
    except Exception:
        # Never let a malformed events collection raise; report what honesty allows.
        memory_hits = memory_hits or 0
        model_calls = model_calls or 0
        other = other or 0

    total = memory_hits + model_calls
    ratio = (memory_hits / total) if total > 0 else 0.0

    result: dict[str, Any] = {
        "total": total,
        "memory_hits": memory_hits,
        "model_calls": model_calls,
        "other": other,
        "ratio": ratio,
        "model_calls_avoided": memory_hits,
    }

    if have_tokens and (tokens_memory + tokens_model) > 0:
        token_total = tokens_memory + tokens_model
        result["token_weighted_ratio"] = tokens_memory / token_total
        result["tokens_memory"] = tokens_memory
        result["tokens_model"] = tokens_model

    return result


def reset() -> None:
    """Clear the in-process event log so a fresh measurement window can start."""
    _EVENTS.clear()


class ScopedCollector:
    """Context manager isolating one measurement window of recorded events.

    Snapshots the current in-process log on entry, clears it so this window's
    `record_event` calls are the only entries visible via `.events`/`.ratio()`, then
    restores the prior log (prepended with this window's events) on exit — so a
    scoped measurement never disturbs or loses another caller's in-flight events.
    """

    def __init__(self) -> None:
        self._prior: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self._open = False

    def __enter__(self) -> "ScopedCollector":
        self._prior = list(_EVENTS)
        _EVENTS.clear()
        self._open = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.events = list(_EVENTS)
        _EVENTS.clear()
        _EVENTS.extend(self._prior)
        _EVENTS.extend(self.events)
        self._open = False
        return None

    def ratio(self) -> dict[str, Any]:
        # While still inside the `with` block, read the live in-process log (this
        # window's events are the only ones present); after exit, use the snapshot
        # captured before the outer log was restored.
        return amortization_ratio(_EVENTS if self._open else self.events)
# #EXT-005-REQ-14 End
