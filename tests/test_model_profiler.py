"""Tests for harness/model_profiler.py — EXT-021 TASK-4 (REQ-4).

All tests are OFFLINE: eval_fn and serve_fn are injected stubs; no live
Jetson, no real eval calls.  Profile JSONs are written to pytest's tmp_path
fixture so no real profiles are touched.

Acceptance criteria covered
----------------------------
(a) A class that CLEARS the bar (passed=True) is written into the profile
    JSON with recorded evidence {name, bar, score, date}.
(b) A class BELOW the bar (passed=False) is NOT added to the profile
    — the honesty test (Tenet 3): never claim a class without proof.
(c) Profiling re-run is idempotent: an already-recorded class is NOT
    duplicated in a subsequent run; eval_fn is also not re-called for it.
(d) fits_jetson() rejects an over-budget model (>8 GB) and accepts a
    Jetson-fitting one (<=8 GB).
(e) roster_order() returns model ids in best-first order from _roster.json;
    falls back gracefully when the roster file is absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.model_profiler import fits_jetson, profile_model, roster_order
from harness.model_registry import ModelProfile, ModelRegistry


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _write_profile(
    tmp_path: Path,
    model_id: str,
    classes: Optional[list[dict]] = None,
    fits: bool = True,
) -> Path:
    """Write a minimal profile JSON to *tmp_path/<model_id>.json*."""
    data = {
        "id": model_id,
        "alias": model_id,
        "serve": {
            "gguf": f"/models/{model_id}.gguf",
            "ctx": 4096,
            "ngl": 99,
            "fits_jetson": fits,
        },
        "classes": classes if classes is not None else [],
        "adaptation": {},
    }
    path = tmp_path / f"{model_id}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _make_registry(*model_ids: str) -> ModelRegistry:
    """Build a minimal in-memory registry (no disk I/O)."""
    profiles = [ModelProfile(id=mid, alias=mid) for mid in model_ids]
    default_id = model_ids[0] if model_ids else "gemma-4-e2b"
    return ModelRegistry(profiles=list(profiles), default_id=default_id)


def _always_pass(score: str = "85%", bar: str = "HumanEval pass@1"):
    """Return an eval_fn stub that always reports passed=True."""
    def _fn(model_id: str, class_def: dict) -> dict:
        return {"passed": True, "score": score, "bar": bar}
    return _fn


def _always_fail(score: str = "30%", bar: str = "HumanEval pass@1 (>=60%)"):
    """Return an eval_fn stub that always reports passed=False."""
    def _fn(model_id: str, class_def: dict) -> dict:
        return {"passed": False, "score": score, "bar": bar}
    return _fn


def _stub_serve(calls: list) -> callable:
    """Return a serve_fn stub that appends model_id to *calls*."""
    def _fn(model_id: str) -> None:
        calls.append(model_id)
    return _fn


# ---------------------------------------------------------------------------
# (a) Class clearing the bar -> written with evidence
# ---------------------------------------------------------------------------

class TestClearingTheBar:
    """A class with passed=True must appear in the profile JSON with evidence."""

    def test_cleared_class_in_added_list(self, tmp_path):
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        result = profile_model(
            "gemma-4-e2b",
            [{"name": "standalone-fn-gen", "bar": "HumanEval pass@1"}],
            registry,
            eval_fn=_always_pass(),
            models_dir=tmp_path,
            now=lambda: "2026-06-28",
        )

        assert "standalone-fn-gen" in result["added"], (
            "A class clearing the bar must appear in added"
        )
        assert result.get("rejected", []) == []

    def test_cleared_class_written_to_json_with_all_evidence_fields(self, tmp_path):
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        profile_model(
            "gemma-4-e2b",
            [{"name": "standalone-fn-gen", "bar": "HumanEval pass@1"}],
            registry,
            eval_fn=_always_pass(score="85%", bar="HumanEval pass@1"),
            models_dir=tmp_path,
            now=lambda: "2026-06-28",
        )

        data = json.loads((tmp_path / "gemma-4-e2b.json").read_text(encoding="utf-8"))
        by_name = {c["name"]: c for c in data["classes"]}
        assert "standalone-fn-gen" in by_name, "Class must be present in the profile JSON"
        entry = by_name["standalone-fn-gen"]
        assert entry["bar"] == "HumanEval pass@1"
        assert entry["score"] == "85%"
        assert entry["date"] == "2026-06-28", "Date evidence must be recorded"

    def test_serve_fn_called_once_with_model_id(self, tmp_path):
        """serve_fn must be invoked before evals start, exactly once."""
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")
        serve_calls: list[str] = []

        profile_model(
            "gemma-4-e2b",
            [{"name": "standalone-fn-gen"}],
            registry,
            eval_fn=_always_pass(),
            serve_fn=_stub_serve(serve_calls),
            models_dir=tmp_path,
        )

        assert serve_calls == ["gemma-4-e2b"], (
            "serve_fn must be called exactly once with model_id before evals"
        )

    def test_serve_fn_none_is_noop(self, tmp_path):
        """serve_fn=None must not raise; profiling still runs."""
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        result = profile_model(
            "gemma-4-e2b",
            [{"name": "cls-x"}],
            registry,
            eval_fn=_always_pass(),
            serve_fn=None,     # explicit None — default
            models_dir=tmp_path,
        )

        assert "cls-x" in result["added"]

    def test_multiple_cleared_classes_all_written(self, tmp_path):
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        profile_model(
            "gemma-4-e2b",
            [{"name": "cls-1"}, {"name": "cls-2"}, {"name": "cls-3"}],
            registry,
            eval_fn=_always_pass(),
            models_dir=tmp_path,
        )

        data = json.loads((tmp_path / "gemma-4-e2b.json").read_text(encoding="utf-8"))
        names = {c["name"] for c in data["classes"]}
        assert {"cls-1", "cls-2", "cls-3"} <= names


# ---------------------------------------------------------------------------
# (b) Class below the bar -> NOT added (honesty test — Tenet 3)
# ---------------------------------------------------------------------------

class TestBelowTheBar:
    """A class with passed=False must NEVER appear in the profile JSON."""

    def test_failed_class_in_rejected_not_added(self, tmp_path):
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        result = profile_model(
            "gemma-4-e2b",
            [{"name": "hard-repo-class", "bar": "101-task repo bar"}],
            registry,
            eval_fn=_always_fail(),
            models_dir=tmp_path,
        )

        assert "hard-repo-class" in result["rejected"], (
            "A class below the bar must appear in rejected"
        )
        assert "hard-repo-class" not in result["added"]

    def test_failed_class_absent_from_json(self, tmp_path):
        """Tenet 3: the profile JSON must NOT contain a below-bar class."""
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        profile_model(
            "gemma-4-e2b",
            [{"name": "hard-repo-class"}],
            registry,
            eval_fn=_always_fail(),
            models_dir=tmp_path,
        )

        data = json.loads((tmp_path / "gemma-4-e2b.json").read_text(encoding="utf-8"))
        class_names = [c["name"] for c in data["classes"]]
        assert "hard-repo-class" not in class_names, (
            "A class that did not clear the bar must NEVER appear in the profile — Tenet 3"
        )

    def test_mixed_pass_fail_only_passed_written(self, tmp_path):
        """Multiple classes: only the ones clearing the bar end up in the profile."""
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        def mixed_eval(model_id: str, class_def: dict) -> dict:
            return {
                "passed": class_def["name"] == "easy-class",
                "score": "70%",
                "bar": "test-bar",
            }

        result = profile_model(
            "gemma-4-e2b",
            [{"name": "easy-class"}, {"name": "hard-class"}],
            registry,
            eval_fn=mixed_eval,
            models_dir=tmp_path,
        )

        assert "easy-class" in result["added"]
        assert "hard-class" in result["rejected"]

        data = json.loads((tmp_path / "gemma-4-e2b.json").read_text(encoding="utf-8"))
        class_names = [c["name"] for c in data["classes"]]
        assert "easy-class" in class_names
        assert "hard-class" not in class_names


# ---------------------------------------------------------------------------
# (c) Re-run idempotency: no duplicate class entries
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Re-running profiling for an already-recorded class must not duplicate it."""

    def test_no_duplicate_on_second_run(self, tmp_path):
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        classes = [{"name": "standalone-fn-gen"}]
        profile_model("gemma-4-e2b", classes, registry,
                      eval_fn=_always_pass(), models_dir=tmp_path)
        profile_model("gemma-4-e2b", classes, registry,
                      eval_fn=_always_pass(), models_dir=tmp_path)

        data = json.loads((tmp_path / "gemma-4-e2b.json").read_text(encoding="utf-8"))
        names = [c["name"] for c in data["classes"] if c["name"] == "standalone-fn-gen"]
        assert len(names) == 1, (
            "Re-running profiling must NOT add a duplicate class entry (idempotent)"
        )

    def test_second_run_returns_empty_added(self, tmp_path):
        """Second run with the same class must return added=[]."""
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        classes = [{"name": "standalone-fn-gen"}]
        profile_model("gemma-4-e2b", classes, registry,
                      eval_fn=_always_pass(), models_dir=tmp_path)
        result2 = profile_model("gemma-4-e2b", classes, registry,
                                eval_fn=_always_pass(), models_dir=tmp_path)

        assert result2["added"] == [], (
            "Second run with same class must return added=[] (already recorded)"
        )

    def test_eval_fn_not_called_for_already_recorded_class(self, tmp_path):
        """eval_fn must NOT be called for a class already in the profile JSON."""
        existing = [
            {"name": "standalone-fn-gen", "bar": "b", "score": "75%", "date": "2026-01-01"}
        ]
        _write_profile(tmp_path, "gemma-4-e2b", classes=existing)
        registry = _make_registry("gemma-4-e2b")

        eval_calls: list[str] = []

        def counting_eval(model_id: str, class_def: dict) -> dict:
            eval_calls.append(class_def["name"])
            return {"passed": True, "score": "80%", "bar": "b"}

        result = profile_model(
            "gemma-4-e2b",
            [{"name": "standalone-fn-gen"}],
            registry,
            eval_fn=counting_eval,
            models_dir=tmp_path,
        )

        assert eval_calls == [], (
            "eval_fn must NOT be called for an already-recorded class (idempotent)"
        )
        assert result["added"] == []

    def test_pre_existing_class_not_in_added_or_rejected(self, tmp_path):
        """Already-recorded classes are silently skipped — not in added OR rejected."""
        existing = [
            {"name": "cls-x", "bar": "b", "score": "s", "date": "2026-01-01"}
        ]
        _write_profile(tmp_path, "gemma-4-e2b", classes=existing)
        registry = _make_registry("gemma-4-e2b")

        result = profile_model(
            "gemma-4-e2b",
            [{"name": "cls-x"}],
            registry,
            eval_fn=_always_pass(),
            models_dir=tmp_path,
        )

        assert "cls-x" not in result["added"]
        assert "cls-x" not in result["rejected"]


# ---------------------------------------------------------------------------
# (d) fits_jetson: rejects over-budget, accepts fitting
# ---------------------------------------------------------------------------

class TestFitsJetson:
    """fits_jetson() is the Jetson admission check (~8 GB VRAM budget)."""

    # -- numeric size_gb field ------------------------------------------------

    def test_accepts_small_model_by_size_gb(self):
        serve = {"gguf": "/models/small.gguf", "size_gb": 2.0, "ngl": 99}
        assert fits_jetson(serve) is True

    def test_rejects_large_model_by_size_gb(self):
        serve = {"gguf": "/models/huge.gguf", "size_gb": 14.0, "ngl": 99}
        assert fits_jetson(serve) is False

    def test_accepts_exactly_at_budget_boundary(self):
        """Exactly 8 GB should be accepted (boundary is inclusive: <=)."""
        serve = {"gguf": "/m.gguf", "size_gb": 8.0}
        assert fits_jetson(serve) is True

    def test_rejects_just_over_budget(self):
        serve = {"gguf": "/m.gguf", "size_gb": 8.1}
        assert fits_jetson(serve) is False

    # -- vram_gb alternate field ----------------------------------------------

    def test_accepts_by_vram_gb(self):
        serve = {"gguf": "/m.gguf", "vram_gb": 3.0}
        assert fits_jetson(serve) is True

    def test_rejects_over_vram_gb(self):
        serve = {"gguf": "/m.gguf", "vram_gb": 10.0}
        assert fits_jetson(serve) is False

    # -- explicit fits_jetson flag (fallback when no size field) --------------

    def test_accepts_by_fits_jetson_true_flag(self):
        serve = {"gguf": "/m.gguf", "ctx": 4096, "ngl": 99, "fits_jetson": True}
        assert fits_jetson(serve) is True

    def test_rejects_by_fits_jetson_false_flag(self):
        serve = {"gguf": "/m.gguf", "ctx": 4096, "ngl": 99, "fits_jetson": False}
        assert fits_jetson(serve) is False

    def test_no_size_info_defaults_to_false(self):
        """No size info and no fits_jetson flag -> rejected (honest by default)."""
        serve = {"gguf": "/m.gguf", "ctx": 4096}
        assert fits_jetson(serve) is False

    # -- ModelProfile instances ------------------------------------------------

    def test_accepts_model_profile_fitting(self):
        profile = ModelProfile(
            id="small-3b",
            alias="small-3b",
            serve={"gguf": "/m.gguf", "size_gb": 2.0, "ngl": 99, "fits_jetson": True},
        )
        assert fits_jetson(profile) is True

    def test_rejects_over_budget_model_profile(self):
        profile = ModelProfile(
            id="big-70b",
            alias="big-70b",
            serve={"gguf": "/m.gguf", "size_gb": 45.0, "ngl": 99, "fits_jetson": False},
        )
        assert fits_jetson(profile) is False

    # -- founding Gemma profile (real JSON) -----------------------------------

    def test_founding_gemma_passes_admission(self):
        """The real Gemma 4 2B profile must be admitted (fits_jetson: True)."""
        profile = ModelProfile(
            id="gemma-4-e2b",
            alias="gemma-4-e2b",
            serve={
                "gguf": "<JETSON_GGUF_PATH>/gemma-4-e2b.gguf",
                "ctx": 4096,
                "ngl": 99,
                "fits_jetson": True,
            },
        )
        assert fits_jetson(profile) is True


# ---------------------------------------------------------------------------
# (e) roster_order: best-first from _roster.json
# ---------------------------------------------------------------------------

class TestRosterOrder:
    """roster_order() returns model ids in best-first order."""

    def test_order_matches_roster_file(self, tmp_path):
        _write_profile(tmp_path, "model-a")
        _write_profile(tmp_path, "model-b")
        (tmp_path / "_roster.json").write_text(
            json.dumps({"default": "model-b", "order": ["model-b", "model-a"]}),
            encoding="utf-8",
        )
        registry = _make_registry("model-a", "model-b")

        order = roster_order(registry, models_dir=tmp_path)
        assert order == ["model-b", "model-a"], (
            "roster_order must return models in the order defined by _roster.json"
        )

    def test_first_entry_is_best_model(self, tmp_path):
        """The first entry in the roster is the strongest (best-first) model."""
        _write_profile(tmp_path, "strong-3b")
        _write_profile(tmp_path, "gemma-4-e2b")
        (tmp_path / "_roster.json").write_text(
            json.dumps({
                "default": "strong-3b",
                "order": ["strong-3b", "gemma-4-e2b"],
            }),
            encoding="utf-8",
        )
        registry = _make_registry("strong-3b", "gemma-4-e2b")

        order = roster_order(registry, models_dir=tmp_path)
        assert order[0] == "strong-3b", "The first entry must be the strongest model"

    def test_fallback_when_roster_absent(self, tmp_path):
        """No _roster.json -> fallback puts the default model first."""
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        order = roster_order(registry, models_dir=tmp_path)
        assert isinstance(order, list)
        assert len(order) >= 1
        assert order[0] == "gemma-4-e2b", "Default model must come first in fallback"

    def test_fallback_when_roster_malformed(self, tmp_path):
        """Malformed _roster.json -> graceful fallback, no crash."""
        _write_profile(tmp_path, "gemma-4-e2b")
        (tmp_path / "_roster.json").write_text("{not valid json", encoding="utf-8")
        registry = _make_registry("gemma-4-e2b")

        order = roster_order(registry, models_dir=tmp_path)
        assert isinstance(order, list)
        assert "gemma-4-e2b" in order

    def test_real_roster_contains_gemma(self):
        """Real roster_order() with no models_dir reads the actual _roster.json."""
        from harness.model_registry import load_registry
        registry = load_registry()
        order = roster_order(registry)  # uses default models_dir
        assert isinstance(order, list)
        assert len(order) >= 1
        assert "gemma-4-e2b" in order, "Real roster must contain the founding Gemma model"


# ---------------------------------------------------------------------------
# Error handling / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Boundary and error cases for profile_model."""

    def test_missing_profile_json_returns_error(self, tmp_path):
        """If no profile JSON exists for the model, return an error honestly."""
        registry = _make_registry("gemma-4-e2b")

        result = profile_model(
            "nonexistent-model",
            [{"name": "cls-x"}],
            registry,
            eval_fn=_always_pass(),
            models_dir=tmp_path,
        )

        assert "error" in result
        assert result["added"] == []
        assert result["rejected"] == []

    def test_empty_classes_list_is_noop(self, tmp_path):
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        result = profile_model(
            "gemma-4-e2b",
            [],
            registry,
            eval_fn=_always_pass(),
            models_dir=tmp_path,
        )

        assert result["added"] == []
        assert result["rejected"] == []
        data = json.loads((tmp_path / "gemma-4-e2b.json").read_text(encoding="utf-8"))
        assert data["classes"] == []

    def test_eval_fn_exception_counted_as_rejected(self, tmp_path):
        """An eval_fn that raises must count as a rejection, not crash profiling."""
        _write_profile(tmp_path, "gemma-4-e2b")
        registry = _make_registry("gemma-4-e2b")

        def exploding_eval(model_id: str, class_def: dict) -> dict:
            raise RuntimeError("eval harness unavailable")

        result = profile_model(
            "gemma-4-e2b",
            [{"name": "cls-x"}],
            registry,
            eval_fn=exploding_eval,
            models_dir=tmp_path,
        )

        assert "cls-x" in result["rejected"]
        assert "cls-x" not in result["added"]
