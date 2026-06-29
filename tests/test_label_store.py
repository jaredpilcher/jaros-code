"""Tests for harness/label_store.py -- EXT-021 REQ-7 (SPLIT, VALIDATE, label recording).

All tests are OFFLINE: temp paths are used for every label store write so
no runtime artifacts (.jaros-data/...) are created or polluted.

Acceptance criteria covered
----------------------------
- record_outcome appends parseable JSONL labels with the expected schema.
- class_outcome_stats aggregates pass_count / total / pass_rate per (class, model).
- split_candidates flags a class with a ~0.5 pass_rate (inconsistent) but NOT
  one that is ~1.0 (consistent) or has too few samples.
- validate_classes puts a >= 0.5-winrate class in predictive and a low one in
  non_predictive; insufficient-n classes are also non_predictive.
- solve_routed_escalating records an outcome to label_path when record=True;
  does NOT write when record=False.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.label_store import (
    class_outcome_stats,
    record_outcome,
    split_candidates,
    validate_classes,
)
from harness.model_registry import ModelProfile, ModelRegistry
from harness.solve_routed import solve_routed_escalating


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_profile(model_id: str, class_names: list) -> ModelProfile:
    classes = [
        {"name": n, "bar": "stub-bar", "score": "99%", "date": "2026-06-28"}
        for n in class_names
    ]
    return ModelProfile(
        id=model_id,
        alias=model_id,
        serve={"gguf": f"/models/{model_id}.gguf", "ctx": 4096, "ngl": 99},
        classes=classes,
        adaptation={"tools": [], "agents": [], "config": {}, "prompts": {}},
    )


def _stub_registry() -> ModelRegistry:
    alpha = _make_profile("model-alpha", ["standalone-fn-gen"])
    beta = _make_profile("model-beta", ["multi-step-repo"])
    return ModelRegistry(profiles=[alpha, beta], default_id="model-alpha")


def _simple_problem() -> dict:
    return {"source": "def add(x, y): return x + y", "language": "python"}


def _write_outcomes(path: Path, model_id: str, cls: str, outcomes: list) -> None:
    """Helper: record a list of bool outcomes for one (model, class)."""
    for passed in outcomes:
        record_outcome(_simple_problem(), model_id, cls, passed, path=path)


# ---------------------------------------------------------------------------
# record_outcome
# ---------------------------------------------------------------------------


class TestRecordOutcome:
    """record_outcome appends valid JSONL lines with the expected schema."""

    def test_appends_parseable_label(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        problem = {"source": "def foo(): pass", "language": "python"}
        record_outcome(problem, "model-alpha", "standalone-fn-gen", True, path=p)

        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["model_id"] == "model-alpha"
        assert rec["problem_class"] == "standalone-fn-gen"
        assert rec["passed"] is True
        assert "ts" in rec
        assert "signature" in rec

    def test_appends_multiple_labels(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        for i in range(3):
            record_outcome(_simple_problem(), f"model-{i}", "cls-a", i % 2 == 0, path=p)
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    def test_passed_false_recorded_as_false(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        record_outcome(_simple_problem(), "model-alpha", "cls-b", False, path=p)
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        assert rec["passed"] is False

    def test_defensive_against_none_problem(self, tmp_path):
        """record_outcome must not raise even with None as the problem."""
        p = tmp_path / "labels.jsonl"
        record_outcome(None, "m", "c", True, path=p)
        # May or may not write (best-effort); the important thing is no exception raised.

    def test_defensive_against_int_problem(self, tmp_path):
        """record_outcome must not raise for an int problem."""
        p = tmp_path / "labels.jsonl"
        record_outcome(42, "m", "c", False, path=p)

    def test_signature_keys_present(self, tmp_path):
        """The recorded signature includes all deterministic feature keys."""
        p = tmp_path / "labels.jsonl"
        problem = {
            "source": "def foo(): pass",
            "language": "python",
            "has_examples": False,
        }
        record_outcome(problem, "model-a", "cls-a", True, path=p)
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        sig = rec["signature"]
        for key in ("language", "is_repo_task", "is_multi_file", "has_examples"):
            assert key in sig, f"Expected key {key!r} in signature"

    def test_creates_parent_dirs(self, tmp_path):
        """record_outcome creates intermediate directories if needed."""
        p = tmp_path / "deep" / "nested" / "labels.jsonl"
        record_outcome(_simple_problem(), "m", "c", True, path=p)
        assert p.exists()


# ---------------------------------------------------------------------------
# class_outcome_stats
# ---------------------------------------------------------------------------


class TestClassOutcomeStats:
    """class_outcome_stats aggregates per-(class, model) counts correctly."""

    def test_empty_on_missing_file(self, tmp_path):
        p = tmp_path / "nonexistent.jsonl"
        assert class_outcome_stats(path=p) == {}

    def test_empty_on_empty_file(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        p.write_text("", encoding="utf-8")
        assert class_outcome_stats(path=p) == {}

    def test_aggregates_pass_count_and_total(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        # 3 pass, 1 fail -> pass_rate 0.75
        _write_outcomes(p, "model-alpha", "cls-a", [True, True, True, False])
        stats = class_outcome_stats(path=p)
        key = ("cls-a", "model-alpha")
        assert key in stats
        assert stats[key]["pass_count"] == 3
        assert stats[key]["total"] == 4
        assert abs(stats[key]["pass_rate"] - 0.75) < 1e-9

    def test_separate_models_yield_separate_keys(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        record_outcome(_simple_problem(), "model-alpha", "cls-a", True, path=p)
        record_outcome(_simple_problem(), "model-beta", "cls-a", False, path=p)
        stats = class_outcome_stats(path=p)
        assert ("cls-a", "model-alpha") in stats
        assert ("cls-a", "model-beta") in stats

    def test_all_pass_rate_is_one(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-b", [True] * 5)
        stats = class_outcome_stats(path=p)
        assert stats[("cls-b", "model-alpha")]["pass_rate"] == 1.0

    def test_all_fail_rate_is_zero(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-c", [False] * 5)
        stats = class_outcome_stats(path=p)
        assert stats[("cls-c", "model-alpha")]["pass_rate"] == 0.0

    def test_separate_classes_separate_keys(self, tmp_path):
        p = tmp_path / "labels.jsonl"
        record_outcome(_simple_problem(), "m", "cls-x", True, path=p)
        record_outcome(_simple_problem(), "m", "cls-y", False, path=p)
        stats = class_outcome_stats(path=p)
        assert ("cls-x", "m") in stats
        assert ("cls-y", "m") in stats
        assert stats[("cls-x", "m")]["pass_rate"] == 1.0
        assert stats[("cls-y", "m")]["pass_rate"] == 0.0

    def test_tolerates_corrupt_line(self, tmp_path):
        """A corrupt JSONL line is skipped; valid lines are still parsed."""
        p = tmp_path / "labels.jsonl"
        record_outcome(_simple_problem(), "model-a", "cls-a", True, path=p)
        # Append a corrupt line
        with p.open("a", encoding="utf-8") as fh:
            fh.write("NOT-VALID-JSON\n")
        record_outcome(_simple_problem(), "model-a", "cls-a", False, path=p)
        stats = class_outcome_stats(path=p)
        # 1 pass, 1 fail recorded (the corrupt line is skipped)
        assert stats[("cls-a", "model-a")]["total"] == 2


# ---------------------------------------------------------------------------
# split_candidates
# ---------------------------------------------------------------------------


class TestSplitCandidates:
    """split_candidates correctly identifies inconsistent classes."""

    def test_flags_class_with_half_pass_rate(self, tmp_path):
        """2 pass + 2 fail -> pass_rate 0.5 -> flagged (middle band)."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-coarse", [True, True, False, False])
        result = split_candidates(path=p, min_n=4)
        assert any(r["class"] == "cls-coarse" for r in result)

    def test_does_not_flag_consistent_high(self, tmp_path):
        """4/4 pass -> pass_rate 1.0 -> NOT flagged (consistent)."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-solid", [True, True, True, True])
        result = split_candidates(path=p, min_n=4)
        assert not any(r["class"] == "cls-solid" for r in result)

    def test_does_not_flag_consistent_low(self, tmp_path):
        """0/4 pass -> pass_rate 0.0 -> NOT flagged (consistently failing)."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-always-fail", [False] * 4)
        result = split_candidates(path=p, min_n=4)
        assert not any(r["class"] == "cls-always-fail" for r in result)

    def test_skips_insufficient_samples(self, tmp_path):
        """Only 2 samples (< min_n=4) -> not flagged regardless of pass_rate."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-few", [True, False])
        result = split_candidates(path=p, min_n=4)
        assert not any(r["class"] == "cls-few" for r in result)

    def test_boundary_at_threshold(self, tmp_path):
        """pass_rate exactly at variance_threshold is flagged (>= check)."""
        p = tmp_path / "labels.jsonl"
        # 35% pass rate -> exactly 0.35 with 20 samples (7 pass, 13 fail)
        outcomes = [True] * 7 + [False] * 13
        _write_outcomes(p, "m", "cls-edge", outcomes)
        result = split_candidates(path=p, min_n=4, variance_threshold=0.35)
        assert any(r["class"] == "cls-edge" for r in result)

    def test_result_entry_has_expected_keys(self, tmp_path):
        """Each entry in the result list has {class, model, pass_rate, n}."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "m", "cls-x", [True, False, True, False])
        result = split_candidates(path=p, min_n=4)
        assert len(result) >= 1
        r = result[0]
        assert "class" in r
        assert "model" in r
        assert "pass_rate" in r
        assert "n" in r

    def test_picks_most_measured_model(self, tmp_path):
        """When two models cover a class, the one with more samples is chosen."""
        p = tmp_path / "labels.jsonl"
        # model-a: 2 samples (50% pass rate) — below min_n individually
        # model-b: 6 samples (50% pass rate) — above min_n
        _write_outcomes(p, "model-a", "cls-two-models", [True, False])
        _write_outcomes(p, "model-b", "cls-two-models", [True, False, True, False, True, False])
        result = split_candidates(path=p, min_n=4)
        flagged = [r for r in result if r["class"] == "cls-two-models"]
        assert len(flagged) == 1
        assert flagged[0]["model"] == "model-b"  # most-measured
        assert flagged[0]["n"] == 6

    def test_empty_store_returns_empty_list(self, tmp_path):
        p = tmp_path / "nonexistent.jsonl"
        assert split_candidates(path=p) == []


# ---------------------------------------------------------------------------
# validate_classes
# ---------------------------------------------------------------------------


class TestValidateClasses:
    """validate_classes partitions classes into predictive and non_predictive."""

    def test_high_winrate_is_predictive(self, tmp_path):
        """4/4 pass -> pass_rate 1.0 >= 0.5 -> predictive."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-good", [True, True, True, True])
        result = validate_classes(path=p, min_n=4)
        classes = [r["class"] for r in result["predictive"]]
        assert "cls-good" in classes

    def test_low_winrate_is_non_predictive(self, tmp_path):
        """1/4 pass -> pass_rate 0.25 < 0.5 -> non_predictive."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-weak", [True, False, False, False])
        result = validate_classes(path=p, min_n=4)
        classes = [r["class"] for r in result["non_predictive"]]
        assert "cls-weak" in classes

    def test_insufficient_n_is_non_predictive(self, tmp_path):
        """2 samples (< min_n=4) -> non_predictive even with pass_rate 1.0."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-few2", [True, True])
        result = validate_classes(path=p, min_n=4)
        classes = [r["class"] for r in result["non_predictive"]]
        assert "cls-few2" in classes

    def test_both_keys_always_present(self, tmp_path):
        """The dict always has both 'predictive' and 'non_predictive' keys."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "m", "cls-ok", [True] * 4)
        _write_outcomes(p, "m", "cls-bad", [False] * 4)
        result = validate_classes(path=p, min_n=4)
        assert "predictive" in result
        assert "non_predictive" in result

    def test_exactly_50pct_is_predictive(self, tmp_path):
        """pass_rate 0.5 with min_winrate=0.5 -> predictive (>= is the check)."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "model-alpha", "cls-exactly50", [True, True, False, False])
        result = validate_classes(path=p, min_n=4, min_winrate=0.5)
        predictive_classes = [r["class"] for r in result["predictive"]]
        assert "cls-exactly50" in predictive_classes

    def test_empty_store_yields_empty_lists(self, tmp_path):
        p = tmp_path / "nonexistent.jsonl"
        result = validate_classes(path=p)
        assert result == {"predictive": [], "non_predictive": []}

    def test_entry_has_expected_keys(self, tmp_path):
        """Each entry has {class, model, pass_rate, n}."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "m", "cls-z", [True, True, True, True])
        result = validate_classes(path=p, min_n=4)
        assert len(result["predictive"]) >= 1
        r = result["predictive"][0]
        assert "class" in r
        assert "model" in r
        assert "pass_rate" in r
        assert "n" in r

    def test_custom_min_winrate_respected(self, tmp_path):
        """With min_winrate=0.8, a 75% pass rate is non_predictive."""
        p = tmp_path / "labels.jsonl"
        _write_outcomes(p, "m", "cls-75", [True, True, True, False])  # 75%
        result = validate_classes(path=p, min_n=4, min_winrate=0.8)
        non_p = [r["class"] for r in result["non_predictive"]]
        assert "cls-75" in non_p


# ---------------------------------------------------------------------------
# solve_routed_escalating records an outcome when record=True (mocked)
# ---------------------------------------------------------------------------


class TestSolveRoutedEscalatingRecordsOutcome:
    """solve_routed_escalating calls record_outcome when record=True."""

    def _make_ok_rewire(self):
        def rewire_fn(model_id: str, registry: Any) -> dict:
            return {
                "model_id": model_id,
                "swapped": False,
                "served_before": None,
                "served_after": model_id,
                "adaptation_active": [],
                "ok": True,
                "error": None,
            }
        return rewire_fn

    def _make_solve_fn(self):
        def solve_fn(problem: Any, decision: dict, rewire_result: dict) -> dict:
            return {"code": "def foo(): pass", "self_pass": True,
                    "model_used": decision["model_id"]}
        return solve_fn

    def _stub_route(self, model_id: str, problem_class: str):
        def route_fn(problem: Any, registry: Any) -> dict:
            return {
                "model_id": model_id,
                "problem_class": problem_class,
                "confidence": 0.9,
                "rationale": "stub",
            }
        return route_fn

    def test_records_outcome_on_pass(self, tmp_path):
        """When record=True and the candidate passes, a label is written."""
        p = tmp_path / "labels.jsonl"
        registry = _stub_registry()
        problem = {"source": "def add(x, y):\n    >>> add(1, 2)\n    3\n    return x+y"}

        result = solve_routed_escalating(
            problem,
            registry=registry,
            route_fn=self._stub_route("model-alpha", "standalone-fn-gen"),
            rewire_fn=self._make_ok_rewire(),
            solve_fn=self._make_solve_fn(),
            test_fn=lambda prob, sol: {"passed": True},
            record=True,
            label_path=p,
        )

        assert result["ok"] is True
        assert p.exists(), "label store should have been written"
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        rec = json.loads(lines[0])
        assert rec["model_id"] == "model-alpha"
        assert rec["problem_class"] == "standalone-fn-gen"
        assert rec["passed"] is True

    def test_records_outcome_on_fail(self, tmp_path):
        """When the candidate fails the test, a False label is written."""
        p = tmp_path / "labels.jsonl"
        registry = _stub_registry()
        problem = {"source": "def add(x, y): return x + y"}

        solve_routed_escalating(
            problem,
            registry=registry,
            route_fn=self._stub_route("model-alpha", "standalone-fn-gen"),
            rewire_fn=self._make_ok_rewire(),
            solve_fn=self._make_solve_fn(),
            test_fn=lambda prob, sol: {"passed": False},
            record=True,
            label_path=p,
        )

        assert p.exists()
        rec = json.loads(p.read_text(encoding="utf-8").strip().splitlines()[0])
        assert rec["passed"] is False

    def test_no_label_when_record_false(self, tmp_path):
        """When record=False, the label store is NOT written."""
        p = tmp_path / "labels_disabled.jsonl"
        registry = _stub_registry()
        problem = {"source": "def add(x, y): return x + y"}

        solve_routed_escalating(
            problem,
            registry=registry,
            route_fn=self._stub_route("model-alpha", "standalone-fn-gen"),
            rewire_fn=self._make_ok_rewire(),
            solve_fn=self._make_solve_fn(),
            test_fn=lambda prob, sol: {"passed": True},
            record=False,
            label_path=p,
        )

        assert not p.exists(), "label store must NOT be written when record=False"

    def test_escalation_records_both_attempts(self, tmp_path):
        """When alpha fails and beta passes, both attempts are recorded."""
        p = tmp_path / "labels.jsonl"

        from harness.model_tally import CoverageTally  # noqa: PLC0415

        class _StubTally:
            def ranked_models_for(self, cls: str) -> list:
                return ["model-alpha", "model-beta"]

        def route_fn(problem, registry):
            return {
                "model_id": "model-alpha",
                "problem_class": "standalone-fn-gen",
                "confidence": 0.9,
                "rationale": "stub",
            }

        call_count = {"n": 0}

        def test_fn(prob, sol):
            call_count["n"] += 1
            # First call (alpha) fails; second call (beta) passes
            return {"passed": call_count["n"] > 1}

        registry = _stub_registry()
        solve_routed_escalating(
            _simple_problem(),
            registry=registry,
            route_fn=route_fn,
            rewire_fn=self._make_ok_rewire(),
            solve_fn=self._make_solve_fn(),
            test_fn=test_fn,
            tally=_StubTally(),
            record=True,
            label_path=p,
        )

        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        recs = [json.loads(ln) for ln in lines]
        assert recs[0]["passed"] is False   # alpha failed
        assert recs[1]["passed"] is True    # beta passed
