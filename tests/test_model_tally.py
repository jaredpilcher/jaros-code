"""Tests for harness/model_tally.py — EXT-021 REQ-5 (coverage tally).

All tests are OFFLINE: stub ModelRegistry / ModelProfile objects are built
in-memory; the real .jaros-data config directory and Jetson are never touched.

Coverage
--------
- ``_parse_score``: percentage strings, explicit fractions, plain numbers,
  dual-percentage strings, unparseable values.
- ``CoverageTally.best_model_for``: highest-score winner; single-coverage;
  class with no coverage returns None.
- Tie-breaking: by roster order (lower index = better) then by default_model.
- ``ranked_models_for``: best-first ordered list; excludes non-covering models;
  empty for unknown class.
- ``coverage_gaps``: partial_models shows missing known classes; fully-covered
  model has no gap entry.
- ``as_matrix``: structure, all-classes / all-models keys, None for absent cells.
- Integration: ``model_router.route`` still routes correctly after the tally
  wiring (uses a stub tally to confirm injection path).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.model_registry import ModelProfile, ModelRegistry
from harness.model_tally import CoverageTally, _parse_score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cls(name: str, score: str, bar: str = "bench", date: str = "2026-06-28") -> dict:
    return {"name": name, "score": score, "bar": bar, "date": date}


def _profile(model_id: str, *classes) -> ModelProfile:
    return ModelProfile(id=model_id, alias=model_id, classes=list(classes))


def _registry(
    profiles: list[ModelProfile],
    default_id: str,
    roster_order: list[str] | None = None,
) -> ModelRegistry:
    return ModelRegistry(
        profiles=profiles,
        default_id=default_id,
        roster_order=roster_order or [],
    )


# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------

class TestParseScore:
    """_parse_score extracts a comparable float from diverse raw score formats."""

    def test_percentage_string(self):
        assert abs(_parse_score("~82%") - 0.82) < 1e-9

    def test_percentage_with_label(self):
        assert abs(_parse_score("~82% HumanEval") - 0.82) < 1e-9

    def test_two_percentages_takes_first(self):
        # "~82% HumanEval / ~48% MBPP" — must take first % (82), NOT interpret
        # as a fraction (82/48 would be wrong).
        v = _parse_score("~82% HumanEval / ~48% MBPP")
        assert abs(v - 0.82) < 1e-9

    def test_explicit_fraction(self):
        v = _parse_score("~18/101")
        assert abs(v - 18 / 101) < 1e-9

    def test_plain_float(self):
        assert abs(_parse_score(0.82) - 0.82) < 1e-9

    def test_plain_int_treated_as_percentage(self):
        # int 82 → 82 > 1 → treated as percentage → 0.82
        assert abs(_parse_score(82) - 0.82) < 1e-9

    def test_plain_float_below_one_used_as_is(self):
        assert abs(_parse_score(0.5) - 0.5) < 1e-9

    def test_simple_percentage_string_99(self):
        assert abs(_parse_score("99%") - 0.99) < 1e-9

    def test_unparseable_returns_lowest(self):
        # Lowest means < 0 so it never beats a real score
        assert _parse_score("no numbers here!") < 0.0

    def test_none_returns_lowest(self):
        assert _parse_score(None) < 0.0

    def test_empty_string_returns_lowest(self):
        assert _parse_score("") < 0.0


# ---------------------------------------------------------------------------
# best_model_for — highest score wins
# ---------------------------------------------------------------------------

class TestBestModelFor:
    """best_model_for returns the model with the highest parsed score."""

    def _two_model_tally(self) -> CoverageTally:
        """Two models; alpha scores 82% on standalone, 18% on repair; beta 75%/60%."""
        reg = _registry(
            [
                _profile(
                    "model-alpha",
                    _cls("standalone-fn-gen", "82%"),
                    _cls("single-file-repair", "18%"),
                ),
                _profile(
                    "model-beta",
                    _cls("standalone-fn-gen", "75%"),
                    _cls("multi-step-repo", "60%"),
                ),
            ],
            default_id="model-alpha",
            roster_order=["model-alpha", "model-beta"],
        )
        return CoverageTally(reg)

    def test_highest_score_model_wins(self):
        """alpha 82% > beta 75% on standalone-fn-gen → alpha."""
        tally = self._two_model_tally()
        assert tally.best_model_for("standalone-fn-gen") == "model-alpha"

    def test_only_covering_model_returned(self):
        """Only beta covers multi-step-repo → beta (trivial argmax)."""
        tally = self._two_model_tally()
        assert tally.best_model_for("multi-step-repo") == "model-beta"

    def test_no_coverage_returns_none(self):
        """A class no model has measured → None."""
        tally = self._two_model_tally()
        assert tally.best_model_for("totally-unknown-class") is None

    def test_none_for_empty_registry(self):
        reg = _registry([], default_id="gemma-4-e2b")
        tally = CoverageTally(reg)
        assert tally.best_model_for("standalone-fn-gen") is None

    def test_single_model_returns_that_model(self):
        reg = _registry(
            [_profile("only-model", _cls("cls-x", "55%"))],
            default_id="only-model",
        )
        tally = CoverageTally(reg)
        assert tally.best_model_for("cls-x") == "only-model"

    def test_real_score_format_with_label(self):
        """Score format "~82% HumanEval / ~48% MBPP" parsed correctly."""
        reg = _registry(
            [
                _profile("gemma", _cls("standalone-fn-gen", "~82% HumanEval / ~48% MBPP")),
                _profile("qwen", _cls("standalone-fn-gen", "~75% HumanEval")),
            ],
            default_id="gemma",
        )
        tally = CoverageTally(reg)
        assert tally.best_model_for("standalone-fn-gen") == "gemma"


# ---------------------------------------------------------------------------
# Tie-breaking: roster order, then default_model
# ---------------------------------------------------------------------------

class TestTieBreaking:
    """Ties (equal score) broken deterministically: roster order, then default."""

    def test_roster_order_breaks_tie(self):
        """Two models with same score; roster says model-b is first → model-b wins."""
        reg = _registry(
            [
                _profile("model-a", _cls("cls-x", "80%")),
                _profile("model-b", _cls("cls-x", "80%")),
            ],
            default_id="model-a",          # default is model-a
            roster_order=["model-b", "model-a"],  # but roster says b is first
        )
        tally = CoverageTally(reg)
        # Roster order wins over default preference
        assert tally.best_model_for("cls-x") == "model-b"

    def test_default_model_preferred_when_no_roster_order(self):
        """Equal scores, no roster order → registry default model wins."""
        reg = _registry(
            [
                _profile("model-a", _cls("cls-x", "80%")),
                _profile("model-b", _cls("cls-x", "80%")),
            ],
            default_id="model-b",
            roster_order=[],
        )
        tally = CoverageTally(reg)
        assert tally.best_model_for("cls-x") == "model-b"

    def test_higher_score_beats_roster_preference(self):
        """A higher score overrides a weaker roster position."""
        reg = _registry(
            [
                _profile("model-a", _cls("cls-x", "90%")),   # higher score
                _profile("model-b", _cls("cls-x", "70%")),   # first in roster
            ],
            default_id="model-b",
            roster_order=["model-b", "model-a"],
        )
        tally = CoverageTally(reg)
        # Score trumps roster
        assert tally.best_model_for("cls-x") == "model-a"

    def test_alphabetical_final_fallback(self):
        """Equal score, equal roster rank, neither is default → alphabetical."""
        reg = _registry(
            [
                _profile("zzz-model", _cls("cls-x", "80%")),
                _profile("aaa-model", _cls("cls-x", "80%")),
            ],
            default_id="other-default",   # not one of the candidates
            roster_order=[],
        )
        tally = CoverageTally(reg)
        # Alphabetical: aaa < zzz
        assert tally.best_model_for("cls-x") == "aaa-model"

    def test_roster_order_injected_to_tally_overrides_registry(self):
        """CoverageTally(reg, roster_order=[...]) uses the injected order."""
        reg = _registry(
            [
                _profile("model-a", _cls("cls-x", "80%")),
                _profile("model-b", _cls("cls-x", "80%")),
            ],
            default_id="model-a",
            roster_order=["model-a", "model-b"],  # registry says a first
        )
        # Inject opposite order
        tally = CoverageTally(reg, roster_order=["model-b", "model-a"])
        assert tally.best_model_for("cls-x") == "model-b"


# ---------------------------------------------------------------------------
# ranked_models_for
# ---------------------------------------------------------------------------

class TestRankedModelsFor:
    """ranked_models_for returns all covering models, best-score-first."""

    def test_returns_all_covering_models_best_first(self):
        reg = _registry(
            [
                _profile("model-a", _cls("cls-x", "70%")),
                _profile("model-b", _cls("cls-x", "90%")),
                _profile("model-c", _cls("cls-x", "50%")),
            ],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        ranked = tally.ranked_models_for("cls-x")
        assert ranked == ["model-b", "model-a", "model-c"]

    def test_excludes_non_covering_models(self):
        reg = _registry(
            [
                _profile("model-a", _cls("cls-x", "70%")),
                _profile("model-b", _cls("cls-y", "90%")),  # different class
            ],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        ranked = tally.ranked_models_for("cls-x")
        assert "model-b" not in ranked
        assert "model-a" in ranked

    def test_includes_runner_ups(self):
        """Runner-up models (not the argmax) must still appear in ranked list."""
        reg = _registry(
            [
                _profile("model-a", _cls("cls-x", "82%")),  # winner
                _profile("model-b", _cls("cls-x", "75%")),  # runner-up
            ],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        ranked = tally.ranked_models_for("cls-x")
        assert ranked[0] == "model-a"
        assert "model-b" in ranked

    def test_empty_for_unknown_class(self):
        reg = _registry(
            [_profile("model-a", _cls("cls-x", "70%"))],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        assert tally.ranked_models_for("cls-unknown") == []

    def test_single_entry_list(self):
        reg = _registry(
            [_profile("only-model", _cls("cls-z", "55%"))],
            default_id="only-model",
        )
        tally = CoverageTally(reg)
        assert tally.ranked_models_for("cls-z") == ["only-model"]


# ---------------------------------------------------------------------------
# coverage_gaps
# ---------------------------------------------------------------------------

class TestCoverageGaps:
    """coverage_gaps surfaces unmeasured cells to drive roster progression."""

    def test_partial_model_shows_missing_class(self):
        """model-b is missing cls-y which model-a has → appears in partial_models."""
        reg = _registry(
            [
                _profile(
                    "model-a",
                    _cls("cls-x", "70%"),
                    _cls("cls-y", "60%"),
                ),
                _profile(
                    "model-b",
                    _cls("cls-x", "80%"),
                    # cls-y NOT measured for model-b
                ),
            ],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        gaps = tally.coverage_gaps()
        assert "model-b" in gaps["partial_models"]
        assert "cls-y" in gaps["partial_models"]["model-b"]

    def test_fully_covered_model_has_no_gap_entry(self):
        """model-a covers both known classes → not in partial_models."""
        reg = _registry(
            [
                _profile(
                    "model-a",
                    _cls("cls-x", "70%"),
                    _cls("cls-y", "60%"),
                ),
                _profile(
                    "model-b",
                    _cls("cls-x", "80%"),
                    _cls("cls-y", "55%"),
                ),
            ],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        gaps = tally.coverage_gaps()
        assert "model-a" not in gaps["partial_models"]
        assert "model-b" not in gaps["partial_models"]

    def test_uncovered_class_all_scores_bad(self):
        """A class whose only cell has an unparseable score surfaces in uncovered."""
        reg = _registry(
            [_profile("model-a", _cls("cls-bad", "not-a-score"))],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        gaps = tally.coverage_gaps()
        assert "cls-bad" in gaps["uncovered_classes"]

    def test_no_gaps_single_model_single_class(self):
        reg = _registry(
            [_profile("model-a", _cls("cls-x", "80%"))],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        gaps = tally.coverage_gaps()
        assert gaps["partial_models"] == {}
        assert "cls-x" not in gaps["uncovered_classes"]

    def test_multiple_partial_models_all_listed(self):
        """When three models exist but only the first covers all classes."""
        reg = _registry(
            [
                _profile("model-a", _cls("c1", "70%"), _cls("c2", "60%"), _cls("c3", "50%")),
                _profile("model-b", _cls("c1", "80%")),   # missing c2, c3
                _profile("model-c", _cls("c2", "90%")),   # missing c1, c3
            ],
            default_id="model-a",
        )
        tally = CoverageTally(reg)
        gaps = tally.coverage_gaps()
        assert set(gaps["partial_models"]["model-b"]) == {"c2", "c3"}
        assert set(gaps["partial_models"]["model-c"]) == {"c1", "c3"}
        assert "model-a" not in gaps["partial_models"]


# ---------------------------------------------------------------------------
# as_matrix
# ---------------------------------------------------------------------------

class TestAsMatrix:
    """as_matrix returns the correct structure."""

    def test_matrix_contains_all_classes_and_models(self):
        reg = _registry(
            [
                _profile("m-a", _cls("c-x", "80%"), _cls("c-y", "60%")),
                _profile("m-b", _cls("c-x", "70%")),
            ],
            default_id="m-a",
        )
        tally = CoverageTally(reg)
        mat = tally.as_matrix()
        assert set(mat["classes"]) == {"c-x", "c-y"}
        assert set(mat["models"]) == {"m-a", "m-b"}

    def test_unmeasured_cell_is_none(self):
        reg = _registry(
            [
                _profile("m-a", _cls("c-x", "80%"), _cls("c-y", "60%")),
                _profile("m-b", _cls("c-x", "70%")),
            ],
            default_id="m-a",
        )
        tally = CoverageTally(reg)
        mat = tally.as_matrix()
        # m-b has no entry for c-y
        assert mat["cells"]["m-b"]["c-y"] is None

    def test_measured_cell_has_score(self):
        reg = _registry(
            [_profile("m-a", _cls("c-x", "80%"))],
            default_id="m-a",
        )
        tally = CoverageTally(reg)
        mat = tally.as_matrix()
        cell = mat["cells"]["m-a"]["c-x"]
        assert cell is not None
        assert abs(cell["score"] - 0.80) < 1e-9


# ---------------------------------------------------------------------------
# Integration: model_router.route uses tally (injection path)
# ---------------------------------------------------------------------------

class TestRouteUsesTally:
    """model_router.route uses the injected tally for model selection."""

    def _make_tally_and_registry(self):
        from harness.model_registry import ModelProfile, ModelRegistry
        profiles = [
            _profile("model-alpha", _cls("standalone-fn-gen", "82%")),
            _profile("model-beta", _cls("multi-step-repo", "60%")),
        ]
        reg = _registry(profiles, default_id="model-alpha")
        tally = CoverageTally(reg)
        return reg, tally

    def test_injected_tally_selects_correct_model(self):
        from harness.model_router import route
        reg, tally = self._make_tally_and_registry()
        decision = route(
            {"has_examples": True, "source": ">>> foo()\n1"},
            reg,
            tally=tally,
        )
        assert decision["model_id"] == "model-alpha"
        assert decision["problem_class"] == "standalone-fn-gen"

    def test_auto_built_tally_same_result_as_injected(self):
        """route() with tally=None builds tally internally; result must match injection."""
        from harness.model_router import route
        reg, tally = self._make_tally_and_registry()
        d_injected = route({"has_examples": True}, reg, tally=tally)
        d_auto = route({"has_examples": True}, reg, tally=None)
        assert d_injected["model_id"] == d_auto["model_id"]
        assert d_injected["problem_class"] == d_auto["problem_class"]

    def test_tally_returns_none_triggers_harness_gap(self):
        """When tally has no coverage for the class, route falls back to default."""
        from harness.model_router import route
        # Registry covering only standalone-fn-gen; repo task → no coverage → gap
        reg = _registry(
            [_profile("model-alpha", _cls("standalone-fn-gen", "82%"))],
            default_id="model-alpha",
        )
        decision = route({"is_repo_task": True}, reg, record=False)
        assert decision["model_id"] == "model-alpha"
        assert "HARNESS-GAP" in decision["rationale"]
