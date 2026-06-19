"""EXT-007 REQ-5 honesty-audit tests (deterministic)."""

from __future__ import annotations

from harness.honesty import audit


def _codes(flags):
    return {f["code"] for f in flags}


def test_flags_zero_model_calls_as_critical():
    sc = {"total": 18, "solved": 12, "modelCalls": {"count": 0}}
    flags = audit(sc, [])
    assert "no-model-calls" in _codes(flags)
    assert any(f["level"] == "CRITICAL" for f in flags if f["code"] == "no-model-calls")


def test_flags_tiny_suite_as_misleading():
    sc = {"total": 2, "solved": 2, "modelCalls": {"count": 4}}
    assert "tiny-suite" in _codes(audit(sc, []))


def test_flags_stagnation_when_flat():
    history = [{"total": 18, "passRate": 0.67} for _ in range(3)]
    sc = {"total": 18, "solved": 12, "modelCalls": {"count": 40}}
    assert "flat-passrate" in _codes(audit(sc, history))


def test_no_stagnation_when_improving():
    history = [{"total": 18, "passRate": p} for p in (0.5, 0.6, 0.72)]
    sc = {"total": 18, "solved": 13, "modelCalls": {"count": 40}}
    assert "flat-passrate" not in _codes(audit(sc, history))


def test_flags_orphans():
    sc = {"total": 18, "solved": 12, "modelCalls": {"count": 40},
          "census": {"agents": 5, "tools": 9},
          "toolUsage": {"code.write_file": 5, "advance": 5},
          "wiringUsage": {"rewriter -> code.write_file": 5}}
    assert "orphans" in _codes(audit(sc, []))
