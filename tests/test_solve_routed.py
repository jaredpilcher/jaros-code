"""Tests for harness/solve_routed.py -- EXT-021 TASK-5 (REQ-2/REQ-3/REQ-4).

All tests are OFFLINE: route_fn / rewire_fn / solve_fn are injected stubs; no
live Jetson, no real filesystem writes, no real LLM calls.

STUB 2-PROFILE REGISTRY
------------------------
A real second model is not yet profiled (only gemma-4-e2b has measured held-out
evidence at the time TASK-5 was implemented).  This test module uses a STUB
2-profile registry:

    model-alpha  -- covers "standalone-fn-gen" (default model)
    model-beta   -- covers "multi-step-repo"   (stronger / second candidate)

This is correct and sufficient for TASK-5.  The real second-model profiling run
happens after model_profiler.profile_model() serves and profiles a candidate
from the roster (see design.md APPENDIX).

Acceptance criteria covered
----------------------------
(a) A problem classified as "standalone-fn-gen" routes to model-alpha AND
    solve_fn is invoked under model-alpha's adaptation.
(b) A problem classified as "multi-step-repo" routes to model-beta (a DIFFERENT
    model) AND solve_fn is invoked under model-beta's adaptation -- demonstrating
    2 classes -> 2 models end-to-end.
(c) A rewire failure short-circuits honestly: solve_fn is NEVER called (the
    wrong model cannot be allowed to solve), and the return dict carries the
    honest error.
(d) The returned dict always carries the full path: decision + rewire record +
    solve result (or None on failure).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.model_registry import ModelProfile, ModelRegistry
from harness.model_router import route
from harness.solve_routed import solve_routed


# ---------------------------------------------------------------------------
# Helpers: build stub registries + profiles (no filesystem)
# ---------------------------------------------------------------------------

def _make_profile(model_id: str, class_names: list[str]) -> ModelProfile:
    """Create a ModelProfile covering the listed class names (with stub evidence)."""
    classes = [
        {"name": n, "bar": "stub-bar", "score": "99%", "date": "2026-06-28"}
        for n in class_names
    ]
    return ModelProfile(
        id=model_id,
        alias=model_id,
        serve={"gguf": f"/models/{model_id}.gguf", "ctx": 4096, "ngl": 99},
        classes=classes,
        adaptation={
            "tools": [f"tool-{model_id}"],
            "agents": [f"agent-{model_id}"],
            "config": {"model": model_id},
            "prompts": {"style": "gherkin"},
        },
    )


def _stub_registry() -> ModelRegistry:
    """Build the canonical 2-profile stub registry.

    model-alpha (DEFAULT) covers standalone-fn-gen.
    model-beta            covers multi-step-repo (harder class).
    """
    alpha = _make_profile("model-alpha", ["standalone-fn-gen"])
    beta = _make_profile("model-beta", ["multi-step-repo"])
    return ModelRegistry(profiles=[alpha, beta], default_id="model-alpha")


# ---------------------------------------------------------------------------
# Shared stubs: rewire_fn and solve_fn that record what was called
# ---------------------------------------------------------------------------

def _make_ok_rewire():
    """Return a rewire_fn that always succeeds; records calls in a list."""
    calls: list[str] = []

    def rewire_fn(model_id: str, registry: Any) -> dict:
        calls.append(model_id)
        profile = registry.lookup_by_id(model_id)
        return {
            "model_id": model_id,
            "swapped": True,
            "served_before": "none",
            "served_after": profile.alias if profile else model_id,
            "adaptation_active": ["tools", "agents", "config", "prompts"],
            "ok": True,
            "error": None,
        }

    return rewire_fn, calls


def _make_fail_rewire():
    """Return a rewire_fn that always fails with an honest error."""
    calls: list[str] = []

    def rewire_fn(model_id: str, registry: Any) -> dict:
        calls.append(model_id)
        return {
            "model_id": model_id,
            "swapped": False,
            "served_before": None,
            "served_after": None,
            "adaptation_active": [],
            "ok": False,
            "error": "simulated swap failure: SSH timeout",
        }

    return rewire_fn, calls


def _make_solve_fn():
    """Return a solve_fn that records the model used and returns a stub result."""
    calls: list[dict] = []

    def solve_fn(problem: Any, decision: dict, rewire_result: dict) -> dict:
        calls.append({
            "model_id": decision["model_id"],
            "problem_class": decision["problem_class"],
        })
        return {
            "solved": True,
            "model_used": decision["model_id"],
            "adaptation": rewire_result.get("adaptation_active", []),
        }

    return solve_fn, calls


# ---------------------------------------------------------------------------
# Problems that map to the two stub classes
# ---------------------------------------------------------------------------

# Problem A: has docstring examples -> classifies as "standalone-fn-gen"
# (route._classify_deterministic: has_examples=True, not repo -> standalone-fn-gen)
_PROBLEM_A = {
    "source": "def add(x, y):\n    >>> add(1, 2)\n    3\n    return x + y",
    "description": "standalone function with docstring examples",
}

# Problem B: has a repo_root -> classifies as "multi-step-repo"
# (route._classify_deterministic: is_repo_task=True -> multi-step-repo)
_PROBLEM_B = {
    "source": "fix the failing imports in utils.py",
    "repo_root": "/some/repo",
    "description": "repo-level bug fix task",
}


# ---------------------------------------------------------------------------
# (a) + (b)  Two classes -> two different models, end-to-end
# ---------------------------------------------------------------------------

class TestTwoClassTwoModel:
    """Demonstrates 2 classes -> 2 different models end-to-end (TASK-5 core).

    Uses the REAL ``route`` function with the stub registry + mocked rewire/solve.
    This verifies that the solve_routed wiring is correct without exercising
    Jetson SSH or a live LLM.
    """

    def test_class_a_standalone_routes_to_model_alpha(self):
        """Problem A (standalone-fn-gen) routes to model-alpha and solve runs there."""
        registry = _stub_registry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_A,
            registry=registry,
            # route_fn uses the REAL route to demonstrate genuine routing
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        # Overall success
        assert result["ok"] is True, f"Expected ok=True, got: {result}"
        assert result["error"] is None

        # Decision: correct model + class
        decision = result["decision"]
        assert decision["model_id"] == "model-alpha", (
            f"Expected model-alpha for standalone-fn-gen, got {decision['model_id']!r}"
        )
        assert decision["problem_class"] == "standalone-fn-gen"
        assert decision["confidence"] > 0

        # Rewire was called with the correct model
        assert rewire_calls == ["model-alpha"]
        rewire_rec = result["rewire"]
        assert rewire_rec["ok"] is True
        assert rewire_rec["model_id"] == "model-alpha"

        # Solve ran under model-alpha
        assert len(solve_calls) == 1
        assert solve_calls[0]["model_id"] == "model-alpha"
        solve_rec = result["solve"]
        assert solve_rec is not None
        assert solve_rec["model_used"] == "model-alpha"

    def test_class_b_repo_routes_to_model_beta(self):
        """Problem B (multi-step-repo) routes to model-beta (DIFFERENT model).

        This proves the second half of the 2-class -> 2-model requirement.
        """
        registry = _stub_registry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_B,
            registry=registry,
            # route_fn uses the REAL route to demonstrate genuine routing
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        # Overall success
        assert result["ok"] is True, f"Expected ok=True, got: {result}"
        assert result["error"] is None

        # Decision: model-beta (NOT model-alpha which is the default)
        decision = result["decision"]
        assert decision["model_id"] == "model-beta", (
            f"Expected model-beta for multi-step-repo, got {decision['model_id']!r}"
        )
        assert decision["problem_class"] == "multi-step-repo"

        # Rewire was called with model-beta
        assert rewire_calls == ["model-beta"]
        rewire_rec = result["rewire"]
        assert rewire_rec["ok"] is True
        assert rewire_rec["model_id"] == "model-beta"

        # Solve ran under model-beta
        assert len(solve_calls) == 1
        assert solve_calls[0]["model_id"] == "model-beta"
        solve_rec = result["solve"]
        assert solve_rec is not None
        assert solve_rec["model_used"] == "model-beta"

    def test_two_classes_route_to_two_different_models(self):
        """Run both problem classes; confirm the two routed models are DIFFERENT."""
        registry = _stub_registry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()

        result_a = solve_routed(
            _PROBLEM_A, registry=registry, rewire_fn=rewire_fn, solve_fn=solve_fn
        )
        result_b = solve_routed(
            _PROBLEM_B, registry=registry, rewire_fn=rewire_fn, solve_fn=solve_fn
        )

        model_a = result_a["decision"]["model_id"]
        model_b = result_b["decision"]["model_id"]

        assert model_a != model_b, (
            f"Expected two different models; both routed to {model_a!r}"
        )
        assert model_a == "model-alpha"
        assert model_b == "model-beta"

        # Both problems solved successfully
        assert result_a["ok"] is True
        assert result_b["ok"] is True


# ---------------------------------------------------------------------------
# (c)  Rewire failure short-circuits honestly; solve_fn is NEVER called
# ---------------------------------------------------------------------------

class TestRewireFailureShortCircuit:
    """Honesty + safety: a rewire failure must prevent the solve."""

    def test_rewire_failure_returns_honest_error(self):
        """Rewire failure propagates honestly in the return dict."""
        registry = _stub_registry()
        rewire_fn, _ = _make_fail_rewire()
        solve_fn, solve_calls = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_A,
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        assert result["ok"] is False
        assert result["error"] is not None
        assert "rewire failed" in result["error"].lower()
        # The rewire error detail is included
        assert "SSH timeout" in result["error"] or "simulated" in result["error"]

    def test_solve_fn_not_called_on_rewire_failure(self):
        """solve_fn is NEVER invoked when rewire fails (wrong model would be active)."""
        registry = _stub_registry()
        rewire_fn, _ = _make_fail_rewire()
        solve_fn, solve_calls = _make_solve_fn()

        solve_routed(
            _PROBLEM_A,
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        assert solve_calls == [], (
            "solve_fn must NOT be called when rewire fails "
            f"(to avoid solving on the wrong model); got calls={solve_calls}"
        )

    def test_solve_is_none_on_rewire_failure(self):
        """The 'solve' key in the return dict is None when rewire failed."""
        registry = _stub_registry()
        rewire_fn, _ = _make_fail_rewire()
        solve_fn, _ = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_A,
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        assert result["solve"] is None


# ---------------------------------------------------------------------------
# (d)  Returned dict carries decision + rewire record + solve result
# ---------------------------------------------------------------------------

class TestReturnDictStructure:
    """The returned dict is always fully-inspectable."""

    def test_success_dict_keys(self):
        """On success the dict has all five keys with correct types."""
        registry = _stub_registry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_A,
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        assert set(result.keys()) >= {"decision", "rewire", "solve", "ok", "error"}
        assert isinstance(result["decision"], dict)
        assert isinstance(result["rewire"], dict)
        assert result["solve"] is not None
        assert result["ok"] is True
        assert result["error"] is None

    def test_failure_dict_keys(self):
        """On rewire failure the dict has all five keys; solve is None."""
        registry = _stub_registry()
        rewire_fn, _ = _make_fail_rewire()
        solve_fn, _ = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_A,
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        assert set(result.keys()) >= {"decision", "rewire", "solve", "ok", "error"}
        assert isinstance(result["decision"], dict)
        assert isinstance(result["rewire"], dict)
        assert result["solve"] is None
        assert result["ok"] is False
        assert isinstance(result["error"], str)
        assert len(result["error"]) > 0

    def test_decision_keys(self):
        """The decision sub-dict has the expected routing keys."""
        registry = _stub_registry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_A,
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        decision = result["decision"]
        assert "model_id" in decision
        assert "problem_class" in decision
        assert "confidence" in decision
        assert "rationale" in decision

    def test_rewire_record_keys(self):
        """The rewire sub-dict has the expected clerk record keys."""
        registry = _stub_registry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_A,
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        rewire_rec = result["rewire"]
        assert "model_id" in rewire_rec
        assert "ok" in rewire_rec

    def test_solve_result_carries_model_used(self):
        """The solve result (from our stub) records which model was active."""
        registry = _stub_registry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()

        result = solve_routed(
            _PROBLEM_A,
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        assert result["solve"]["model_used"] == "model-alpha"


# ---------------------------------------------------------------------------
# Extra: stub route_fn injection (verifies the full injection path)
# ---------------------------------------------------------------------------

class TestRouteFnInjection:
    """Verify that route_fn is injectable (covers the injection path itself)."""

    def test_custom_route_fn_is_called(self):
        """An injected route_fn replaces the real route; its Decision is used."""
        registry = _stub_registry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()

        route_calls: list[dict] = []

        def custom_route(problem, reg):
            decision = {
                "model_id": "model-beta",
                "problem_class": "multi-step-repo",
                "confidence": 0.99,
                "rationale": "custom route fn forced model-beta",
            }
            route_calls.append(decision)
            return decision

        result = solve_routed(
            _PROBLEM_A,      # would normally route to model-alpha
            registry=registry,
            route_fn=custom_route,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        assert result["ok"] is True
        # Custom route overrode the natural classification
        assert result["decision"]["model_id"] == "model-beta"
        assert rewire_calls == ["model-beta"]
        assert solve_calls[0]["model_id"] == "model-beta"
        assert len(route_calls) == 1
