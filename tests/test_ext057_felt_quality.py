"""EXT-057 REQ-4 — the felt-quality / interactivity dimension of the parity instrument.

The Product-Parity Checklist measured FEATURE PRESENCE and reported ~84% while the owner's lived
verdict on the actual REPL (2026-07-07) was "awful" — a Tenet-3 gap where the instrument reported
high while the felt experience was poor. These tests pin that the felt-quality dimension exists,
scores the CURRENT state HONESTLY, and pulls the flattering feature-only number down.
"""
# #EXT-057-REQ-4 Start
from harness.product_parity import (
    FELT_QUALITY_ROWS,
    FeltQualityRow,
    score,
    score_felt_quality,
    score_overall,
)

VALID = {"works", "partial", "missing"}
EXPECTED_KEYS = {
    "streams_model_output",
    "live_tool_feedback",
    "natural_language_first",
    "working_indicator",
    "interrupt_surfaced",
}


def test_felt_quality_rows_cover_the_interactivity_subscores():
    keys = {r.key for r in FELT_QUALITY_ROWS}
    assert EXPECTED_KEYS.issubset(keys), f"missing sub-scores: {EXPECTED_KEYS - keys}"
    for r in FELT_QUALITY_ROWS:
        assert isinstance(r, FeltQualityRow)
        assert r.state in VALID
        assert r.label and r.measured_as  # every sub-score documents how it's measured


def test_scored_honestly_not_aspirational():
    by_key = {r.key: r.state for r in FELT_QUALITY_ROWS}
    # A working/thinking indicator does not exist yet -> honestly missing.
    assert by_key["working_indicator"] == "missing"
    # The streaming CLIENT exists (REQ-1) but no interactive caller consumes it yet -> NOT "works".
    assert by_key["streams_model_output"] in ("partial", "missing")
    # Nothing in the current tree is dishonestly marked a perfect felt experience.
    assert not all(s == "works" for s in by_key.values())


def test_score_felt_quality_shape_and_range():
    res = score_felt_quality()
    for k in ("pct", "n_total", "n_works", "n_partial", "n_missing", "attack_list"):
        assert k in res
    assert 0.0 <= res["pct"] <= 100.0
    assert res["n_total"] == len(FELT_QUALITY_ROWS)
    # The current felt experience is poor -> well below a perfect score.
    assert res["pct"] < 100.0
    # The attack list surfaces the partial+missing rows to fix.
    assert len(res["attack_list"]) == res["n_partial"] + res["n_missing"]


def test_overall_blends_and_is_dragged_down_by_felt_quality():
    feature_only = score()["pct"]
    overall = score_overall()
    felt = score_felt_quality()["pct"]
    # Equal-weighted blend of feature-presence and felt-quality.
    assert overall["pct"] == round((feature_only + felt) / 2, 1)
    # The whole point: felt-quality is worse than feature-presence, so the honest overall
    # number is pulled DOWN below the flattering feature-only number.
    assert felt < feature_only
    assert overall["pct"] < feature_only
# #EXT-057-REQ-4 End
