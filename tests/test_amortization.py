"""Tests for the amortization-ratio telemetry instrument (EXT-005 REQ-14).

Offline, deterministic, no model calls. Every `record_event` call passes `sink=None`
so tests never touch `.jaros-data/artifacts/amortization/events.jsonl` on disk.
"""

from __future__ import annotations

import pytest

from harness import amortization
from harness.amortization import (
    MEMORY_HIT,
    MODEL_CALL,
    ScopedCollector,
    amortization_ratio,
    record_event,
    reset,
)


@pytest.fixture(autouse=True)
def _isolated_log():
    """Every test starts and ends with a clean in-process event log."""
    reset()
    yield
    reset()


def test_record_and_ratio_exact_counts():
    record_event(MEMORY_HIT, sink=None)
    record_event(MEMORY_HIT, sink=None)
    record_event(MEMORY_HIT, sink=None)
    record_event(MODEL_CALL, sink=None)
    record_event(MODEL_CALL, sink=None)

    result = amortization_ratio()

    assert result["total"] == 5
    assert result["memory_hits"] == 3
    assert result["model_calls"] == 2
    assert result["model_calls_avoided"] == 3
    assert result["ratio"] == pytest.approx(3 / 5)


def test_ratio_zero_total_is_honest_zero_not_exception():
    result = amortization_ratio()  # nothing recorded
    assert result["total"] == 0
    assert result["memory_hits"] == 0
    assert result["model_calls"] == 0
    assert result["model_calls_avoided"] == 0
    assert result["ratio"] == 0.0


def test_ratio_zero_total_from_explicit_empty_list():
    result = amortization_ratio([])
    assert result == {
        "total": 0,
        "memory_hits": 0,
        "model_calls": 0,
        "other": 0,
        "ratio": 0.0,
        "model_calls_avoided": 0,
    }


def test_all_memory_hits_ratio_is_one():
    for _ in range(4):
        record_event(MEMORY_HIT, sink=None)
    result = amortization_ratio()
    assert result["ratio"] == 1.0
    assert result["model_calls_avoided"] == 4


def test_all_model_calls_ratio_is_zero():
    for _ in range(4):
        record_event(MODEL_CALL, sink=None)
    result = amortization_ratio()
    assert result["ratio"] == 0.0
    assert result["model_calls_avoided"] == 0


def test_reset_clears_the_log():
    record_event(MEMORY_HIT, sink=None)
    record_event(MODEL_CALL, sink=None)
    assert amortization_ratio()["total"] == 2

    reset()

    assert amortization_ratio() == {
        "total": 0,
        "memory_hits": 0,
        "model_calls": 0,
        "other": 0,
        "ratio": 0.0,
        "model_calls_avoided": 0,
    }


def test_scoped_collector_isolates_a_measurement_window():
    # Outer-scope events recorded before entering the window.
    record_event(MEMORY_HIT, sink=None)
    record_event(MEMORY_HIT, sink=None)
    assert amortization_ratio()["total"] == 2

    with ScopedCollector() as window:
        record_event(MODEL_CALL, sink=None)
        record_event(MODEL_CALL, sink=None)
        record_event(MODEL_CALL, sink=None)
        inner = window.ratio()

    # The window saw only its own 3 MODEL_CALL events, isolated from the outer 2 hits.
    assert inner["total"] == 3
    assert inner["model_calls"] == 3
    assert inner["memory_hits"] == 0

    # After the window closes, the outer log is restored plus the window's own events.
    outside = amortization_ratio()
    assert outside["total"] == 5
    assert outside["memory_hits"] == 2
    assert outside["model_calls"] == 3


def test_scoped_collector_restores_prior_log_on_exception():
    record_event(MEMORY_HIT, sink=None)

    with pytest.raises(RuntimeError):
        with ScopedCollector():
            record_event(MODEL_CALL, sink=None)
            raise RuntimeError("boom")

    # Prior event plus the window's event are both preserved even though the
    # `with` block raised.
    result = amortization_ratio()
    assert result["total"] == 2
    assert result["memory_hits"] == 1
    assert result["model_calls"] == 1


@pytest.mark.parametrize(
    "garbage_source",
    [None, 123, object(), "TOTALLY_UNKNOWN", "", ["a", "list"], {"a": "dict"}],
)
def test_record_event_never_raises_on_garbage_source(garbage_source):
    # Must not raise for any of these inputs.
    event = record_event(garbage_source, sink=None)
    assert isinstance(event, dict)
    assert "source" in event


def test_garbage_source_is_recorded_but_not_counted_as_hit_or_call():
    record_event("NOT_A_REAL_SOURCE", sink=None)
    record_event(MEMORY_HIT, sink=None)

    result = amortization_ratio()

    assert result["memory_hits"] == 1
    assert result["model_calls"] == 0
    assert result["other"] == 1
    # `total` (the ratio denominator) counts only recognized sources.
    assert result["total"] == 1
    assert result["ratio"] == 1.0


def test_record_event_never_raises_on_bad_meta_and_tokens():
    class Unserializable:
        pass

    event = record_event(
        MODEL_CALL,
        kind=Unserializable(),
        tokens="not-a-number",
        meta=Unserializable(),
        sink=None,
    )
    assert isinstance(event, dict)
    # Bad tokens degrade to None rather than raising or corrupting the count.
    assert event["tokens"] is None

    result = amortization_ratio()
    assert result["total"] == 1
    assert result["model_calls"] == 1


def test_amortization_ratio_never_raises_on_malformed_events_list():
    malformed = [None, "not-a-dict", 42, {"source": MEMORY_HIT}, {"no_source_key": True}]
    result = amortization_ratio(malformed)  # must not raise
    assert isinstance(result, dict)
    assert result["memory_hits"] == 1
    assert result["total"] == 1


def test_record_event_sink_write_failure_does_not_raise(tmp_path):
    # A sink path that cannot be created (its parent is a FILE, not a dir) must not
    # crash record_event.
    blocker = tmp_path / "blocker_file"
    blocker.write_text("x")
    bad_sink = blocker / "events.jsonl"  # parent ("blocker_file") is a file, not a dir

    event = record_event(MEMORY_HIT, sink=bad_sink)
    assert isinstance(event, dict)
    assert amortization_ratio()["memory_hits"] == 1


def test_module_constants_are_the_documented_source_names():
    assert amortization.MEMORY_HIT == "MEMORY_HIT"
    assert amortization.MODEL_CALL == "MODEL_CALL"
