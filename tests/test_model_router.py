"""Tests for harness/model_router.py -- EXT-021 TASK-2 (REQ-2).

Verifies four acceptance criteria:
  (a) A class covered only by a specific model routes to THAT model.
  (b) An unknown / uncovered class routes to default_model() with low
      confidence and a rationale that marks it as a HARNESS-GAP.
  (c) The returned value is inert plain data (no I/O, no model served).
  (d) route(..., llm=None) works purely deterministically.

All tests use a stub registry built from fake ModelProfile objects; the real
registry and Jetson are never touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.model_registry import ModelProfile, ModelRegistry
from harness.model_router import route

# ---------------------------------------------------------------------------
# Helpers: build fake registries without touching the filesystem
# ---------------------------------------------------------------------------

def _make_profile(model_id: str, class_names: list[str]) -> ModelProfile:
    """Create a ModelProfile covering the listed class names."""
    classes = [
        {"name": n, "bar": "test-bar", "score": "99%", "date": "2026-01-01"}
        for n in class_names
    ]
    return ModelProfile(id=model_id, alias=model_id, classes=classes, adaptation={})


def _make_registry(profiles: list[ModelProfile], default_id: str) -> ModelRegistry:
    return ModelRegistry(profiles=profiles, default_id=default_id)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_GEMMA_PROFILE = _make_profile(
    "gemma-4-e2b",
    ["standalone-fn-gen", "single-file-repair"],
)
_STRONG_PROFILE = _make_profile(
    "strong-model-7b",
    ["multi-step-repo"],
)


def _two_model_registry() -> ModelRegistry:
    """Registry with gemma (standalone) + strong (repo); default = gemma."""
    return _make_registry([_GEMMA_PROFILE, _STRONG_PROFILE], default_id="gemma-4-e2b")


def _gemma_only_registry() -> ModelRegistry:
    """Registry with only gemma; default = gemma."""
    return _make_registry([_GEMMA_PROFILE], default_id="gemma-4-e2b")


# ---------------------------------------------------------------------------
# (a) Covered class routes to the right specific model
# ---------------------------------------------------------------------------

class TestRouteCoveredClass:
    """Acceptance criterion (a): covered class -> the covering model."""

    def test_repo_task_routes_to_strong_model(self):
        """is_repo_task=True -> 'multi-step-repo' -> strong-model-7b."""
        reg = _two_model_registry()
        decision = route({"is_repo_task": True, "source": "fix bug in repo"}, reg)

        assert decision["model_id"] == "strong-model-7b"
        assert decision["problem_class"] == "multi-step-repo"
        assert decision["confidence"] > 0.5

    def test_multi_file_routes_to_strong_model(self):
        """is_multi_file=True -> 'multi-step-repo' -> strong-model-7b."""
        reg = _two_model_registry()
        decision = route({"is_multi_file": True}, reg)

        assert decision["model_id"] == "strong-model-7b"
        assert decision["problem_class"] == "multi-step-repo"

    def test_standalone_with_examples_routes_to_gemma(self):
        """Docstring examples, no repo -> 'standalone-fn-gen' -> gemma."""
        reg = _two_model_registry()
        decision = route(
            {"has_examples": True, "source": ">>> add(1,2)\n3"},
            reg,
        )

        assert decision["model_id"] == "gemma-4-e2b"
        assert decision["problem_class"] == "standalone-fn-gen"
        assert decision["confidence"] > 0.5

    def test_examples_in_source_heuristic_routes_to_gemma(self):
        """'>>>' in source triggers has_examples heuristic -> standalone-fn-gen."""
        reg = _two_model_registry()
        decision = route({"source": "def add(a,b):\n    >>> add(1,2)\n    3"}, reg)

        assert decision["model_id"] == "gemma-4-e2b"
        assert decision["problem_class"] == "standalone-fn-gen"

    def test_only_covering_model_used_when_default_does_not_cover(self):
        """When the default doesn't cover the class, first covering model is used."""
        # strong-model-7b is default, but only gemma covers standalone-fn-gen
        reg = _make_registry(
            [_GEMMA_PROFILE, _STRONG_PROFILE],
            default_id="strong-model-7b",
        )
        decision = route({"has_examples": True}, reg)

        assert decision["model_id"] == "gemma-4-e2b"
        assert decision["problem_class"] == "standalone-fn-gen"

    def test_default_preferred_when_both_cover_class(self):
        """When two models both cover a class, prefer the default."""
        profile_a = _make_profile("model-a", ["standalone-fn-gen"])
        profile_b = _make_profile("model-b", ["standalone-fn-gen"])
        reg = _make_registry([profile_a, profile_b], default_id="model-b")

        decision = route({"has_examples": True, "source": ">>> foo()\n1"}, reg)
        assert decision["model_id"] == "model-b"


# ---------------------------------------------------------------------------
# (b) Unknown / uncovered class -> default with low confidence + HARNESS-GAP
# ---------------------------------------------------------------------------

class TestRouteFallback:
    """Acceptance criterion (b): uncovered class -> default + low conf + gap marker."""

    def test_uncovered_class_routes_to_default(self):
        """Repo task, only gemma registered (covers standalone) -> fallback to gemma."""
        reg = _gemma_only_registry()
        decision = route({"is_repo_task": True}, reg)

        assert decision["model_id"] == "gemma-4-e2b"  # the only / default model
        assert decision["confidence"] < 0.5

    def test_fallback_confidence_is_low(self):
        """Fallback decisions must have clearly low confidence."""
        reg = _gemma_only_registry()
        decision = route({"is_repo_task": True}, reg)
        assert decision["confidence"] <= 0.3

    def test_fallback_rationale_contains_harness_gap_marker(self):
        """HARNESS-GAP marker must appear so the convergence loop can see it."""
        reg = _gemma_only_registry()
        decision = route({"is_repo_task": True}, reg)
        assert "HARNESS-GAP" in decision["rationale"]

    def test_fallback_rationale_not_model_limit(self):
        """Misroute is a HARNESS gap, NEVER attributed to a model limit (PRIME-001).

        The rationale may mention 'model limit' when explicitly DENYING it
        (e.g. '...not a model limit'), which is correct.  The forbidden pattern
        is attributing the fallback TO the model without denial.
        """
        reg = _gemma_only_registry()
        decision = route({"is_repo_task": True}, reg)
        # The gap marker is the positive signal; just verify it's present
        assert "HARNESS-GAP" in decision["rationale"]
        # Must NOT use a bare "is a model limit" or "model ceiling" attribution
        rationale_lower = decision["rationale"].lower()
        assert "is a model limit" not in rationale_lower
        assert "model ceiling" not in rationale_lower

    def test_empty_registry_always_returns_default(self):
        """Even with zero loaded profiles, route() returns the default id."""
        reg = ModelRegistry(profiles=[], default_id="gemma-4-e2b")
        decision = route({"source": "do something"}, reg)

        assert decision["model_id"] == "gemma-4-e2b"
        assert isinstance(decision["model_id"], str)
        assert len(decision["model_id"]) > 0

    def test_completely_unknown_class_via_llm_still_fallbacks(self):
        """If LLM returns an unrecognised class name, deterministic default wins."""
        reg = _gemma_only_registry()

        def bad_llm(prompt: str) -> str:
            return "totally-unknown-class-xyz"

        decision = route({"source": "some task"}, reg, llm=bad_llm)
        assert decision["model_id"] == "gemma-4-e2b"


# ---------------------------------------------------------------------------
# (c) Return value is inert plain data -- no I/O, no model served
# ---------------------------------------------------------------------------

class TestRouteInertData:
    """Acceptance criterion (c): return is a plain dict, no side effects."""

    def test_return_is_dict(self):
        reg = _gemma_only_registry()
        result = route({"source": "foo()"}, reg)
        assert isinstance(result, dict)

    def test_return_has_required_keys(self):
        reg = _gemma_only_registry()
        result = route({"source": "foo()"}, reg)
        assert "model_id" in result
        assert "problem_class" in result
        assert "confidence" in result
        assert "rationale" in result

    def test_model_id_is_str(self):
        reg = _gemma_only_registry()
        result = route({"source": "foo()"}, reg)
        assert isinstance(result["model_id"], str)
        assert len(result["model_id"]) > 0

    def test_problem_class_is_str(self):
        reg = _gemma_only_registry()
        result = route({"source": "foo()"}, reg)
        assert isinstance(result["problem_class"], str)

    def test_confidence_is_float_in_range(self):
        reg = _gemma_only_registry()
        result = route({"source": "foo()", "has_examples": True}, reg)
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_rationale_is_str(self):
        reg = _gemma_only_registry()
        result = route({"source": "foo()"}, reg)
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 0

    def test_no_side_effects_on_filesystem(self, tmp_path):
        """route() must not write any files to disk."""
        import os
        reg = _gemma_only_registry()
        before = set(os.listdir(tmp_path))
        route({"source": "foo()"}, reg)
        after = set(os.listdir(tmp_path))
        assert before == after

    def test_return_has_no_extra_required_state(self):
        """The dict is self-contained plain data (JSON-serialisable)."""
        import json
        reg = _gemma_only_registry()
        result = route({"source": "foo()"}, reg)
        # Must be JSON-serialisable (no objects, no callables, no file handles)
        serialised = json.dumps(result)
        parsed = json.loads(serialised)
        assert parsed["model_id"] == result["model_id"]
        assert parsed["problem_class"] == result["problem_class"]


# ---------------------------------------------------------------------------
# (d) route(..., llm=None) is purely deterministic
# ---------------------------------------------------------------------------

class TestRouteDeterministic:
    """Acceptance criterion (d): works without LLM; deterministic."""

    def test_works_without_llm(self):
        reg = _gemma_only_registry()
        result = route({"source": "def add(a, b): ..."}, reg, llm=None)
        assert result is not None
        assert "model_id" in result

    def test_same_problem_always_same_result(self):
        """No randomness: same problem always produces the same decision."""
        reg = _two_model_registry()
        problem = {"source": ">>> foo(1)\n1", "has_examples": True}
        r1 = route(problem, reg, llm=None)
        r2 = route(problem, reg, llm=None)
        assert r1 == r2

    def test_llm_not_called_when_confidence_high(self):
        """High-confidence deterministic result -> LLM callable is never invoked."""
        reg = _two_model_registry()
        calls: list[str] = []

        def tracking_llm(prompt: str) -> str:
            calls.append(prompt)
            return "standalone-fn-gen"

        # is_repo_task=True gives _HIGH_CONFIDENCE -> LLM should NOT be called
        route({"is_repo_task": True}, reg, llm=tracking_llm)
        assert calls == [], "LLM must not be called when deterministic confidence is high"

    def test_llm_called_when_ambiguous(self):
        """Low-confidence deterministic -> LLM is consulted when provided."""
        reg = _two_model_registry()
        calls: list[str] = []

        def tracking_llm(prompt: str) -> str:
            calls.append(prompt)
            return "standalone-fn-gen"

        # No examples, not repo -> medium confidence (< ambiguity threshold)
        route({"source": "some ambiguous code"}, reg, llm=tracking_llm)
        assert len(calls) >= 1, "LLM should be consulted for ambiguous problems"

    def test_llm_label_used_when_valid(self):
        """When LLM returns a known class label it overrides the deterministic one."""
        reg = _two_model_registry()

        def override_llm(prompt: str) -> str:
            return "standalone-fn-gen"

        # Without examples, deterministic would say "single-file-repair"
        result = route({"source": "some code without examples"}, reg, llm=override_llm)
        # LLM overrode to "standalone-fn-gen"
        assert result["problem_class"] == "standalone-fn-gen"

    def test_llm_exception_falls_back_to_deterministic(self):
        """If LLM raises, route() still returns a valid decision."""
        reg = _gemma_only_registry()

        def exploding_llm(prompt: str) -> str:
            raise RuntimeError("LLM unavailable")

        result = route({"source": "some code"}, reg, llm=exploding_llm)
        assert isinstance(result, dict)
        assert "model_id" in result

    def test_non_dict_problem_handled_gracefully(self):
        """A plain string or object as problem does not raise."""
        reg = _gemma_only_registry()
        # Plain string -- _to_dict falls back to {}
        result = route("fix the bug in foo.py", reg, llm=None)
        assert isinstance(result, dict)
        assert "model_id" in result

    def test_empty_problem_handled(self):
        """An empty dict produces a valid decision."""
        reg = _gemma_only_registry()
        result = route({}, reg, llm=None)
        assert isinstance(result, dict)
        assert result["model_id"] == reg.default_model()

    def test_repo_root_key_implies_repo_task(self):
        """Presence of repo_root (no explicit flag) classifies as repo task."""
        reg = _two_model_registry()
        result = route({"repo_root": "/home/user/myproject"}, reg, llm=None)
        assert result["problem_class"] == "multi-step-repo"
        assert result["model_id"] == "strong-model-7b"

    def test_files_list_implies_multi_file(self):
        """files=[a, b] with no explicit flag derives is_multi_file=True."""
        reg = _two_model_registry()
        result = route({"files": ["a.py", "b.py"]}, reg, llm=None)
        assert result["problem_class"] == "multi-step-repo"
        assert result["model_id"] == "strong-model-7b"

    def test_single_file_no_examples_is_repair(self):
        """No examples, not repo, single file -> single-file-repair class."""
        reg = _gemma_only_registry()
        result = route({"source": "def foo(): pass", "has_examples": False}, reg, llm=None)
        assert result["problem_class"] == "single-file-repair"
