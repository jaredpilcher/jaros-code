"""Statusline: a one-line "model · class · $0 · latency" surface (EXT-045 REQ-2).

WHY: `docs/GAP-MAP.md` Product-surface parity row #24 names a Claude-Code-like statusline so
the user knows, at a glance, WHAT is serving the current session, WHAT KIND of problem it just
routed, that it cost nothing (Tenet 2 -- always local/$0), and HOW LONG the last turn took.
Every field is read from state the CLI already tracks (the active model label, the last routed
action, and the measured wall-clock latency of the last `handle()` turn) -- no new model call,
no new measurement mechanism (Tenet 1: pure execution-plane presentation).

Never raises (mirrors `harness/heartbeat.py`'s observability discipline): a statusline must
never break the thing it is merely describing.
"""
from __future__ import annotations

# #EXT-045-REQ-2 Start
_DOT = "·"  # ·


def statusline(model: "str | None", problem_class: "str | None" = None,
                latency_s: "float | None" = None, cost: str = "$0") -> str:
    """Render ``model · problem-class · $0 · latency`` for the given fields.

    ``problem_class`` defaults to ``"-"`` when unknown (no turn routed yet this session).
    ``latency_s`` defaults to ``"-"`` when unknown (no turn timed yet); otherwise formatted to
    two decimal seconds. ``cost`` is always the honest ``$0`` marker (Tenet 2: no paid/cloud
    model is ever in the loop) unless a caller overrides it for testing.

    Never raises -- any bad input degrades to a minimal, still-honest fallback line.
    """
    try:
        model_s = str(model).strip() if model else "unknown-model"
        class_s = str(problem_class).strip() if problem_class else "-"
        cost_s = str(cost).strip() if cost else "$0"
        if isinstance(latency_s, (int, float)) and latency_s >= 0:
            lat_s = f"{latency_s:.2f}s"
        else:
            lat_s = "-"
        return f"{model_s} {_DOT} {class_s} {_DOT} {cost_s} {_DOT} {lat_s}"
    except Exception:
        return f"jcode {_DOT} - {_DOT} $0 {_DOT} -"
# #EXT-045-REQ-2 End
