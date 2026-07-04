"""Observability heartbeat for jaros-code's long-running operations (EXT-040).

WHY (owner directive 2026-07-04): autonomous builds, suite runs, and eval loops are
opaque -- you cannot tell "working" from "wedged", and a blind wait costs 20-40 min.
This records a timestamped ACTIVITY TRAIL to ``.jaros-data/artifacts/heartbeat/`` so a
``/status`` reader (and the autonomous watcher) can answer, at a glance: WHAT is running,
since WHEN, for HOW LONG, and whether the last beat is STALE (>5 min -> likely stalled).

Deterministic execution-plane code (Tenet 1): no model calls. NEVER RAISES -- an
observability layer must never break the thing it observes; every public function swallows
its own errors and degrades to a best-effort/honest-empty result.
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

# #EXT-040-REQ-1 Start
# 5-minute heartbeat threshold -- the owner's "5 minute heartbeat" (2026-07-04). A current
# activity whose last beat is older than this is reported ``stalled=True``.
DEFAULT_STALL_S = 300
_KEEPALIVE_S = 30  # background keepalive cadence while a heartbeat() context is open
_CURRENT = "current.json"


def _hb_dir() -> Path:
    d = Path(os.environ.get("JCODE_HEARTBEAT_DIR", ".jaros-data/artifacts/heartbeat"))
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def beat(activity: str, detail: str = "", *, run_id: "str | None" = None,
         started_at: "float | None" = None) -> None:
    """Record ONE heartbeat: append to the per-run log AND overwrite ``current.json`` with
    the latest state. ``started_at`` (epoch secs) lets a caller keep elapsed anchored to the
    operation's true start across many beats. Never raises."""
    try:
        d = _hb_dir()
        now = time.time()
        rec = {
            "ts": now,
            "activity": str(activity),
            "detail": str(detail),
            "pid": os.getpid(),
            "run_id": str(run_id or ""),
            "started_at": float(started_at) if started_at is not None else now,
        }
        line = json.dumps(rec)
        rid = (str(run_id or "global")).replace("/", "_").replace("\\", "_")
        try:
            with (d / f"{rid}.jsonl").open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        (d / _CURRENT).write_text(line, encoding="utf-8")
    except Exception:
        pass


def status(stall_after_s: float = DEFAULT_STALL_S) -> dict:
    """Read the latest heartbeat -> a status dict. When there is no current activity, returns
    ``{"idle": True, ...}`` honestly (never a fabricated "running"). Never raises.

    Keys: activity, detail, pid, run_id, started_at, last_beat, elapsed_s,
    since_last_beat_s, stalled (last beat older than ``stall_after_s``), idle."""
    try:
        cur = _hb_dir() / _CURRENT
        if not cur.is_file():
            return {"activity": None, "idle": True, "stalled": False}
        rec = json.loads(cur.read_text(encoding="utf-8"))
        now = time.time()
        last = float(rec.get("ts", now))
        started = float(rec.get("started_at", last))
        since = max(0.0, now - last)
        return {
            "activity": rec.get("activity"),
            "detail": rec.get("detail", ""),
            "pid": rec.get("pid"),
            "run_id": rec.get("run_id", ""),
            "started_at": started,
            "last_beat": last,
            "elapsed_s": round(max(0.0, now - started), 1),
            "since_last_beat_s": round(since, 1),
            "stalled": since > stall_after_s,
            "idle": False,
        }
    except Exception:
        return {"activity": None, "idle": True, "stalled": False, "error": True}


def format_status(st: "dict | None" = None, stall_after_s: float = DEFAULT_STALL_S) -> str:
    """One-line human-readable status for a ``/status`` CLI. Never raises."""
    try:
        st = st if st is not None else status(stall_after_s)
        if st.get("idle"):
            return "jcode: idle (no activity in progress)"
        act = st.get("activity") or "?"
        detail = st.get("detail") or ""
        elapsed = st.get("elapsed_s", 0)
        since = st.get("since_last_beat_s", 0)
        flag = "  !! STALLED" if st.get("stalled") else ""
        tail = f" - {detail}" if detail else ""
        return (f"jcode: {act}{tail} (elapsed {elapsed:.0f}s, last beat {since:.0f}s ago, "
                f"pid {st.get('pid')}){flag}")
    except Exception:
        return "jcode: status unavailable"


@contextmanager
def heartbeat(activity: str, *, run_id: "str | None" = None, detail: str = ""):
    """Wrap a long operation. Beats START on entry; yields a handle whose ``.beat(phase,
    detail)`` records phase transitions; beats END (with elapsed) on clean exit, or ERROR on
    exception (which is re-raised). A daemon keepalive thread re-beats every ~30s so even a
    long single-phase step keeps showing life (and its absence => a real stall). Never raises
    on its own bookkeeping (the wrapped body's exceptions DO propagate)."""
    start = time.time()
    rid = run_id or f"{activity}-{int(start)}"

    class _Handle:
        phase = "START"

        def beat(self, phase: str, d: str = "") -> None:
            self.phase = str(phase)
            beat(activity, f"{phase}: {d}" if d else str(phase), run_id=rid, started_at=start)

    handle = _Handle()
    beat(activity, f"START: {detail}" if detail else "START", run_id=rid, started_at=start)

    stop = threading.Event()

    def _keepalive() -> None:
        while not stop.wait(_KEEPALIVE_S):
            beat(activity, f"{handle.phase} (running {round(time.time() - start)}s)",
                 run_id=rid, started_at=start)

    t = threading.Thread(target=_keepalive, name=f"heartbeat-{rid}", daemon=True)
    try:
        t.start()
    except Exception:
        pass
    try:
        yield handle
        beat(activity, f"END ({round(time.time() - start)}s)", run_id=rid, started_at=start)
    except Exception as exc:
        beat(activity, f"ERROR ({round(time.time() - start)}s): {type(exc).__name__}",
             run_id=rid, started_at=start)
        raise
    finally:
        stop.set()
# #EXT-040-REQ-1 End
