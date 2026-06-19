"""Scheduled push-report gating (EXT-005 / REQ-8).

Deterministic rules for WHEN the supervisor pushes a phone report: roughly every
``interval_min`` minutes, but never during quiet hours (default 02:00–08:00 local).
Kept pure + testable so reporting cadence does not depend on eyeballing the clock.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".jaros-data" / "artifacts" / "eval" / "last_push.json"

QUIET_START = 2   # inclusive hour (local)
QUIET_END = 8     # exclusive hour (local)
INTERVAL_MIN = 30


def in_quiet_hours(now: datetime, start: int = QUIET_START, end: int = QUIET_END) -> bool:
    """True if ``now`` (local) is within the no-report window [start, end)."""
    return start <= now.hour < end


def should_push(now: datetime, last_push_iso: str | None,
                interval_min: int = INTERVAL_MIN,
                start: int = QUIET_START, end: int = QUIET_END) -> bool:
    """Push iff outside quiet hours AND >= interval since the last push."""
    if in_quiet_hours(now, start, end):
        return False
    if not last_push_iso:
        return True
    try:
        last = datetime.fromisoformat(last_push_iso)
    except ValueError:
        return True
    return (now - last) >= timedelta(minutes=interval_min)


def read_last_push() -> str | None:
    try:
        return json.loads(STATE.read_text(encoding="utf-8")).get("lastPush")
    except (OSError, ValueError):
        return None


def record_push(now: datetime) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"lastPush": now.isoformat(timespec="seconds")}), encoding="utf-8")


def due(now: datetime | None = None) -> bool:
    """Convenience: is a push due right now (reads persisted state)?"""
    return should_push(now or datetime.now(), read_last_push())
