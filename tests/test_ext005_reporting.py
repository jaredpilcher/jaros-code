"""EXT-005 REQ-8/REQ-9 tests: push gating (quiet hours) + growth census."""

from __future__ import annotations

from datetime import datetime

from harness.notify import in_quiet_hours, should_push
from harness.report import census


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 19, hour, minute, 0)


def test_quiet_hours_window():
    assert in_quiet_hours(_at(2)) is True
    assert in_quiet_hours(_at(7, 59)) is True
    assert in_quiet_hours(_at(8)) is False
    assert in_quiet_hours(_at(1, 59)) is False
    assert in_quiet_hours(_at(13)) is False


def test_no_push_during_quiet_hours_even_if_overdue():
    assert should_push(_at(3), last_push_iso=None) is False
    assert should_push(_at(3), last_push_iso=_at(0).isoformat()) is False


def test_push_when_interval_elapsed_outside_quiet():
    assert should_push(_at(13), last_push_iso=None) is True
    assert should_push(_at(13, 30), last_push_iso=_at(13).isoformat()) is True
    assert should_push(_at(13, 10), last_push_iso=_at(13).isoformat()) is False


def test_census_counts_present_and_positive():
    c = census()
    assert c["agents"] >= 4 and c["tools"] >= 7 and c["evals"] >= 9 and c["specs"] >= 5
