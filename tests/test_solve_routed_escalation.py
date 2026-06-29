"""Tests for REQ-6 test-gated roster escalation in solve_routed_escalating.

ALL tests are OFFLINE: route_fn / rewire_fn / solve_fn / test_fn / tally are
injected stubs; no live Jetson, no real LLM calls, no real filesystem writes.

Acceptance criteria covered
----------------------------
(a) Best candidate passes -> returned immediately; runner-ups NOT tried.
(b) Best fails, 2nd passes -> escalates; 2nd is the winner (diversity+test-gate).
(c) All candidates fail within budget -> honest 'no candidate passed' + all
    attempts recorded.
(d) Winner selected ONLY by test_fn; no model is consulted to rank outputs
    (model-as-judge is forbidden by design -- architectural guarantee).
(e) Budget (max_models) caps the number of models tried.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.solve_routed import solve_routed_escalating


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _StubTally:
    """Stub CoverageTally that returns a fixed ordered candidate list per class."""

    def __init__(self, class_to_models: dict[str, list[str]]):
        self._map = class_to_models

    def ranked_models_for(self, class_name: str) -> list[str]:
        return list(self._map.get(class_name, []))


class _StubRegistry:
    """Minimal registry stub; only default_model() is needed for empty-tally paths."""

    def __init__(self, default_id: str = "default-model"):
        self._default = default_id

    def default_model(self) -> str:
        return self._default


def _stub_route_fn(problem_class: str = "standalone-fn-gen"):
    """Return a route_fn that always produces the given problem_class."""
    def route_fn(problem: Any, registry: Any) -> dict:
        return {
            "model_id": "stub-route-model",
            "problem_class": problem_class,
            "confidence": 0.9,
            "rationale": "stub route fn",
        }
    return route_fn


def _make_ok_rewire():
    """Rewire stub that always succeeds; records which model ids were rewired."""
    calls: list[str] = []

    def rewire_fn(model_id: str, registry: Any) -> dict:
        calls.append(model_id)
        return {
            "model_id": model_id,
            "swapped": True,
            "served_before": "none",
            "served_after": model_id,
            "adaptation_active": ["tools", "agents"],
            "ok": True,
            "error": None,
        }

    return rewire_fn, calls


def _make_solve_fn():
    """Solve stub that records which model was used and returns a stub result."""
    calls: list[str] = []

    def solve_fn(problem: Any, decision: dict, rewire_result: dict) -> dict:
        mid = decision["model_id"]
        calls.append(mid)
        return {"solved": True, "model_used": mid, "output": f"code-from-{mid}"}

    return solve_fn, calls


def _make_test_fn(passing_models: set):
    """Return a test_fn that passes for models in *passing_models*, fails otherwise.

    Records each (model, passed) evaluation for inspection.
    """
    evaluations: list[dict] = []

    def test_fn(problem: Any, solve_result: dict) -> dict:
        model_used = solve_result.get("model_used", "")
        passed = model_used in passing_models
        evaluations.append({"model": model_used, "passed": passed})
        return {"passed": passed, "model_used": model_used}

    return test_fn, evaluations


# A minimal problem dict (routing features don't matter — route_fn is injected).
_PROBLEM = {
    "source": "def add(x, y): return x + y",
    "task": "implement add function",
}


# ---------------------------------------------------------------------------
# (a) Best candidate passes -> returned immediately; runner-ups NOT tried
# ---------------------------------------------------------------------------

class TestBestCandidatePassesFirst:
    """REQ-6(a): best-tally candidate passes -> winner returned, no escalation."""

    def test_first_candidate_wins_immediately(self):
        """First candidate passes -> ok=True, winner=alpha."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta", "model-gamma"]})
        registry = _StubRegistry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()
        test_fn, evaluations = _make_test_fn({"model-alpha"})  # only alpha passes

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
            max_models=3,
        )

        assert result["ok"] is True
        assert result["winner_model_id"] == "model-alpha"
        assert result["test_gated"] is True
        assert result["error"] is None

    def test_runner_ups_not_tried_when_first_passes(self):
        """If the first candidate passes, the second and third are NOT tried."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta", "model-gamma"]})
        registry = _StubRegistry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()
        test_fn, evaluations = _make_test_fn({"model-alpha"})

        solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
            max_models=3,
        )

        # Only model-alpha was rewired and solved; beta and gamma untouched
        assert rewire_calls == ["model-alpha"]
        assert solve_calls == ["model-alpha"]
        assert len(evaluations) == 1
        assert evaluations[0]["model"] == "model-alpha"

    def test_only_one_attempt_recorded_on_first_pass(self):
        """Attempts list has exactly one entry when the first candidate passes."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn({"model-alpha"})

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert len(result["attempts"]) == 1
        assert result["attempts"][0]["model"] == "model-alpha"
        assert result["attempts"][0]["passed"] is True

    def test_solve_result_is_from_first_winner(self):
        """The returned solve result belongs to the winning model (alpha)."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn({"model-alpha"})

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert result["solve"]["model_used"] == "model-alpha"


# ---------------------------------------------------------------------------
# (b) Best fails, 2nd passes -> escalates; 2nd is the winner
# ---------------------------------------------------------------------------

class TestEscalationToSecondCandidate:
    """REQ-6(b): first candidate fails -> escalates to 2nd, which passes."""

    def test_escalates_to_second_when_first_fails(self):
        """First candidate fails the test; second candidate is tried and wins."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta", "model-gamma"]})
        registry = _StubRegistry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()
        test_fn, evaluations = _make_test_fn({"model-beta"})  # only beta passes

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
            max_models=3,
        )

        assert result["ok"] is True
        assert result["winner_model_id"] == "model-beta"
        assert result["test_gated"] is True
        assert result["error"] is None

    def test_second_wins_and_third_not_tried(self):
        """When 2nd passes, 3rd is NOT tried (early-exit on first pass)."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta", "model-gamma"]})
        registry = _StubRegistry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()
        test_fn, evaluations = _make_test_fn({"model-beta"})

        solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
            max_models=3,
        )

        # alpha was tried (failed), beta was tried (passed), gamma NOT tried
        assert rewire_calls == ["model-alpha", "model-beta"]
        assert solve_calls == ["model-alpha", "model-beta"]
        assert len(evaluations) == 2
        assert evaluations[0] == {"model": "model-alpha", "passed": False}
        assert evaluations[1] == {"model": "model-beta", "passed": True}

    def test_attempts_records_alpha_fail_beta_pass(self):
        """Attempts list records alpha=False, beta=True in order."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn({"model-beta"})

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert len(result["attempts"]) == 2
        assert result["attempts"][0]["model"] == "model-alpha"
        assert result["attempts"][0]["passed"] is False
        assert result["attempts"][1]["model"] == "model-beta"
        assert result["attempts"][1]["passed"] is True

    def test_solve_result_is_from_second_winner(self):
        """The returned solve result belongs to the winning model (beta)."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn({"model-beta"})

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert result["solve"]["model_used"] == "model-beta"


# ---------------------------------------------------------------------------
# (c) All candidates fail within budget -> honest "no candidate passed"
# ---------------------------------------------------------------------------

class TestAllCandidatesFail:
    """REQ-6(c): all candidates fail -> honest 'no candidate passed' + all recorded."""

    def test_all_fail_returns_no_winner(self):
        """When no candidate passes, ok=False and winner_model_id=None."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())  # nobody passes

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert result["ok"] is False
        assert result["winner_model_id"] is None
        assert result["test_gated"] is True

    def test_all_fail_honest_error_message(self):
        """The error string explicitly says 'no candidate passed'."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert result["error"] is not None
        assert "no candidate passed" in result["error"].lower()

    def test_all_fail_all_attempts_recorded(self):
        """All attempted models appear in the attempts list, all with passed=False."""
        tally = _StubTally({
            "standalone-fn-gen": ["model-alpha", "model-beta", "model-gamma"]
        })
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
            max_models=3,
        )

        attempted_models = [a["model"] for a in result["attempts"]]
        assert "model-alpha" in attempted_models
        assert "model-beta" in attempted_models
        assert "model-gamma" in attempted_models
        assert all(a["passed"] is False for a in result["attempts"])

    def test_all_fail_returns_last_solve_result(self):
        """When all fail, the solve result from the last attempted model is returned."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        # Last candidate is model-beta; its result is returned (not None)
        assert result["solve"] is not None
        assert result["solve"]["model_used"] == "model-beta"


# ---------------------------------------------------------------------------
# (d) Winner selected ONLY by test_fn; no model is consulted to rank outputs
# ---------------------------------------------------------------------------

class TestTestFnIsTheSoleJudge:
    """REQ-6(d): model-as-judge is forbidden; test_fn alone picks the winner."""

    def test_test_gated_always_true(self):
        """test_gated=True is set in every return path (single candidate, pass)."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn({"model-alpha"})

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert result["test_gated"] is True

    def test_test_gated_true_on_all_fail(self):
        """test_gated=True is also set when all candidates fail."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())  # none pass

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert result["test_gated"] is True

    def test_test_fn_overrides_tally_rank(self):
        """Even when tally ranks alpha > beta, if alpha fails and beta passes,
        beta wins — the test result overrides tally rank (test-gate is authoritative)."""
        # tally order: alpha (best) > beta
        tally = _StubTally({"standalone-fn-gen": ["model-alpha", "model-beta"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        # test_fn: only beta's output passes
        test_fn, _ = _make_test_fn({"model-beta"})

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        # beta wins even though the tally ranks it below alpha
        assert result["winner_model_id"] == "model-beta"
        assert result["ok"] is True

    def test_failing_test_fn_prevents_win_for_best_model(self):
        """If the test always returns passed=False, even the best model never wins."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())  # nobody passes

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        assert result["ok"] is False
        assert result["winner_model_id"] is None


# ---------------------------------------------------------------------------
# (e) Budget (max_models) caps the number of models tried
# ---------------------------------------------------------------------------

class TestBudgetCap:
    """REQ-6(e): max_models bounds the escalation; models beyond budget are skipped."""

    def test_budget_2_skips_third_candidate(self):
        """With max_models=2 and 3 candidates, only 2 are tried (all fail)."""
        tally = _StubTally({
            "standalone-fn-gen": ["model-alpha", "model-beta", "model-gamma"]
        })
        registry = _StubRegistry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, solve_calls = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())  # all fail

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
            max_models=2,
        )

        assert len(result["attempts"]) == 2
        assert rewire_calls == ["model-alpha", "model-beta"]
        assert solve_calls == ["model-alpha", "model-beta"]
        tried_models = [a["model"] for a in result["attempts"]]
        assert "model-gamma" not in tried_models

    def test_budget_1_only_tries_best(self):
        """With max_models=1, only the single best candidate is tried."""
        tally = _StubTally({
            "standalone-fn-gen": ["model-alpha", "model-beta"]
        })
        registry = _StubRegistry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
            max_models=1,
        )

        assert len(result["attempts"]) == 1
        assert rewire_calls == ["model-alpha"]

    def test_early_exit_does_not_exhaust_budget(self):
        """If the first candidate passes, we stop (not all max_models tried)."""
        tally = _StubTally({
            "standalone-fn-gen": ["model-alpha", "model-beta", "model-gamma"]
        })
        registry = _StubRegistry()
        rewire_fn, rewire_calls = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn({"model-alpha"})  # alpha passes

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
            max_models=3,
        )

        # Stopped after the first win (not all 3 tried despite budget=3)
        assert len(result["attempts"]) == 1
        assert rewire_calls == ["model-alpha"]
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Return dict structure
# ---------------------------------------------------------------------------

class TestReturnDictStructure:
    """The return dict always carries the expected keys."""

    def test_success_dict_has_all_required_keys(self):
        """On success the dict has: decision, winner_model_id, attempts,
        solve, test_gated, ok, error."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn({"model-alpha"})

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        required = {"decision", "winner_model_id", "attempts", "solve",
                    "test_gated", "ok", "error"}
        assert required.issubset(result.keys())
        assert result["ok"] is True
        assert result["error"] is None
        assert result["test_gated"] is True

    def test_failure_dict_has_all_required_keys(self):
        """On all-fail the dict has the same keys; ok=False, winner_model_id=None."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn(set())

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        required = {"decision", "winner_model_id", "attempts", "solve",
                    "test_gated", "ok", "error"}
        assert required.issubset(result.keys())
        assert result["ok"] is False
        assert result["winner_model_id"] is None
        assert result["test_gated"] is True
        assert isinstance(result["error"], str)

    def test_decision_keys_present(self):
        """The decision sub-dict carries the expected routing keys."""
        tally = _StubTally({"standalone-fn-gen": ["model-alpha"]})
        registry = _StubRegistry()
        rewire_fn, _ = _make_ok_rewire()
        solve_fn, _ = _make_solve_fn()
        test_fn, _ = _make_test_fn({"model-alpha"})

        result = solve_routed_escalating(
            _PROBLEM,
            registry=registry,
            route_fn=_stub_route_fn("standalone-fn-gen"),
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
            test_fn=test_fn,
            tally=tally,
        )

        decision = result["decision"]
        assert "model_id" in decision
        assert "problem_class" in decision
        assert "confidence" in decision
        assert "rationale" in decision


# ---------------------------------------------------------------------------
# Regression: existing solve_routed is unaffected
# ---------------------------------------------------------------------------

class TestExistingSolveRoutedUnchanged:
    """Confirm that the original solve_routed function is unaffected (no regressions)."""

    def test_solve_routed_still_importable_and_works(self):
        """The original solve_routed function is still importable and correct."""
        from harness.solve_routed import solve_routed
        from harness.model_registry import ModelProfile, ModelRegistry

        alpha = ModelProfile(
            id="model-alpha",
            alias="model-alpha",
            serve={"gguf": "/m/alpha.gguf", "ctx": 4096, "ngl": 99},
            classes=[{
                "name": "standalone-fn-gen",
                "bar": "b",
                "score": "90%",
                "date": "2026-06-28",
            }],
            adaptation={"tools": [], "agents": [], "config": {}, "prompts": {}},
        )
        registry = ModelRegistry(profiles=[alpha], default_id="model-alpha")

        def rewire_fn(mid, reg):
            return {
                "model_id": mid, "swapped": False, "served_before": None,
                "served_after": mid, "adaptation_active": [], "ok": True, "error": None,
            }

        def solve_fn(prob, dec, rew):
            return {"solved": True, "model_used": dec["model_id"]}

        result = solve_routed(
            {"source": "def add(x,y):\n    >>> add(1,2)\n    3"},
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=solve_fn,
        )

        assert result["ok"] is True
        assert "decision" in result
        assert "rewire" in result
        assert "solve" in result

    def test_solve_routed_does_not_have_test_gated_key(self):
        """The original solve_routed does NOT return test_gated (different API)."""
        from harness.solve_routed import solve_routed
        from harness.model_registry import ModelProfile, ModelRegistry

        alpha = ModelProfile(
            id="model-alpha",
            alias="model-alpha",
            serve={"gguf": "/m/alpha.gguf", "ctx": 4096, "ngl": 99},
            classes=[{
                "name": "standalone-fn-gen",
                "bar": "b",
                "score": "90%",
                "date": "2026-06-28",
            }],
            adaptation={"tools": [], "agents": [], "config": {}, "prompts": {}},
        )
        registry = ModelRegistry(profiles=[alpha], default_id="model-alpha")

        def rewire_fn(mid, reg):
            return {
                "model_id": mid, "swapped": False, "served_before": None,
                "served_after": mid, "adaptation_active": [], "ok": True, "error": None,
            }

        result = solve_routed(
            {"source": "def add(x,y):\n    >>> add(1,2)\n    3"},
            registry=registry,
            rewire_fn=rewire_fn,
            solve_fn=lambda p, d, r: {"solved": True},
        )

        # solve_routed has decision/rewire/solve/ok/error (not test_gated)
        assert "test_gated" not in result
        assert "winner_model_id" not in result
