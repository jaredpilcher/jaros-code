"""Offline tests for harness/adaptation.py (EXT-021 REQ-3).

All tests are OFFLINE: no Jetson, no real LLM calls, no filesystem writes.
The code-gen callables inside ADAPTATION_REGISTRY are monkeypatched with stubs
where needed; the registry itself is built in-process.

Coverage
--------
(A) code_gen_for(qwen adaptation) returns the qwen code-gen.
(B) code_gen_for(gemma adaptation dict) returns the gemma code-gen.
(C) code_gen_for with unknown / missing / None label returns the DEFAULT (gemma).
(D) code_gen_for never raises — exhaustive bad-input check.
(E) solve_routed with the default solver (no solve_fn injected) invokes the
    qwen code-gen for qwen-routed problems and the gemma code-gen for
    gemma-routed problems — verified via ADAPTATION_REGISTRY monkeypatching.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import harness.adaptation as adapt_mod
from harness.adaptation import (
    ADAPTATION_REGISTRY,
    _DEFAULT_LABEL,
    _extract_label,
    _gemma_gherkin_code_gen,
    _qwen_instruct_code_gen,
    _r1_reasoning_code_gen,
    code_gen_for,
)
from harness.model_registry import ModelProfile, ModelRegistry
from harness.solve_routed import solve_routed


# ---------------------------------------------------------------------------
# Helpers: stub adaptation dicts + profiles mirroring the real JSON shapes
# ---------------------------------------------------------------------------

# Gemma's real shape: adaptation["prompts"] is a dict containing solve_style
_GEMMA_ADAPTATION = {
    "prompts": {"solve_style": "gherkin-decompose", "note": "stub"},
}

# Qwen's real shape: adaptation["prompts"] is a string
_QWEN_ADAPTATION = {
    "prompts": "qwen-instruct-direct",
}


def _make_model_profile(model_id: str, adaptation: dict) -> ModelProfile:
    return ModelProfile(
        id=model_id,
        alias=model_id,
        serve={"gguf": f"/stub/{model_id}.gguf", "ctx": 4096, "ngl": 99},
        classes=[{"name": "stub-class", "bar": "stub", "score": "99%", "date": "2026-06-28"}],
        adaptation=adaptation,
    )


def _stub_registry_two_models() -> ModelRegistry:
    """Registry with a qwen profile (primary) and a gemma profile (default)."""
    qwen = _make_model_profile("qwen2.5-coder-3b", _QWEN_ADAPTATION)
    gemma = _make_model_profile("gemma-4-e2b", _GEMMA_ADAPTATION)
    return ModelRegistry(profiles=[qwen, gemma], default_id="gemma-4-e2b")


# ---------------------------------------------------------------------------
# (A) code_gen_for with qwen adaptation
# ---------------------------------------------------------------------------

class TestCodeGenForQwen:
    def test_adaptation_dict_returns_qwen_callable(self):
        """code_gen_for(qwen_adaptation) returns the qwen code-gen callable."""
        fn = code_gen_for(_QWEN_ADAPTATION)
        assert fn is _qwen_instruct_code_gen, (
            f"Expected _qwen_instruct_code_gen, got {fn!r}"
        )

    def test_adaptation_string_label_returns_qwen_callable(self):
        """code_gen_for('qwen-instruct-direct') returns the qwen code-gen."""
        fn = code_gen_for("qwen-instruct-direct")
        assert fn is _qwen_instruct_code_gen

    def test_model_profile_qwen_returns_qwen_callable(self):
        """code_gen_for(ModelProfile with qwen adaptation) returns the qwen code-gen."""
        profile = _make_model_profile("qwen2.5-coder-3b", _QWEN_ADAPTATION)
        fn = code_gen_for(profile)
        assert fn is _qwen_instruct_code_gen


# ---------------------------------------------------------------------------
# (B) code_gen_for with gemma adaptation
# ---------------------------------------------------------------------------

class TestCodeGenForGemma:
    def test_adaptation_dict_nested_returns_gemma_callable(self):
        """code_gen_for(gemma_adaptation with nested prompts dict) returns the gemma callable."""
        fn = code_gen_for(_GEMMA_ADAPTATION)
        assert fn is _gemma_gherkin_code_gen, (
            f"Expected _gemma_gherkin_code_gen, got {fn!r}"
        )

    def test_adaptation_string_label_returns_gemma_callable(self):
        """code_gen_for('gherkin-decompose') returns the gemma code-gen."""
        fn = code_gen_for("gherkin-decompose")
        assert fn is _gemma_gherkin_code_gen

    def test_model_profile_gemma_returns_gemma_callable(self):
        """code_gen_for(ModelProfile with gemma nested adaptation) returns the gemma callable."""
        profile = _make_model_profile("gemma-4-e2b", _GEMMA_ADAPTATION)
        fn = code_gen_for(profile)
        assert fn is _gemma_gherkin_code_gen


# ---------------------------------------------------------------------------
# (C) Unknown / missing label → DEFAULT (gemma), never raises
# ---------------------------------------------------------------------------

class TestCodeGenForDefault:
    def test_none_returns_default(self):
        """code_gen_for(None) returns the default (gemma) callable."""
        fn = code_gen_for(None)
        assert fn is _gemma_gherkin_code_gen

    def test_unknown_string_label_returns_default(self):
        """An unknown string label falls back to the gemma default."""
        fn = code_gen_for("totally-unknown-style")
        assert fn is _gemma_gherkin_code_gen

    def test_empty_dict_returns_default(self):
        """An empty adaptation dict falls back to the gemma default."""
        fn = code_gen_for({})
        assert fn is _gemma_gherkin_code_gen

    def test_dict_with_unknown_prompts_returns_default(self):
        """An adaptation dict with an unregistered prompts value falls back."""
        fn = code_gen_for({"prompts": "xyzzy-unknown"})
        assert fn is _gemma_gherkin_code_gen

    def test_nested_prompts_dict_missing_solve_style_returns_default(self):
        """A nested prompts dict without 'solve_style' falls back to default."""
        fn = code_gen_for({"prompts": {"note": "no solve_style here"}})
        assert fn is _gemma_gherkin_code_gen

    def test_default_label_constant_is_gherkin(self):
        """The DEFAULT label is 'gherkin-decompose' (gemma's path)."""
        assert _DEFAULT_LABEL == "gherkin-decompose"

    def test_default_is_in_registry(self):
        """The DEFAULT label has a registry entry."""
        assert _DEFAULT_LABEL in ADAPTATION_REGISTRY


# ---------------------------------------------------------------------------
# (D) code_gen_for never raises on adversarial input
# ---------------------------------------------------------------------------

class TestCodeGenForNeverRaises:
    @pytest.mark.parametrize("bad_input", [
        None,
        "",
        0,
        [],
        {},
        {"prompts": None},
        {"prompts": 42},
        {"prompts": []},
        object(),
    ])
    def test_never_raises(self, bad_input):
        """code_gen_for never raises, regardless of input."""
        result = code_gen_for(bad_input)
        assert callable(result)

    def test_result_is_always_callable(self):
        """Whatever code_gen_for returns is always callable."""
        for val in [None, "unknown", {}, {"prompts": "bad"}, _QWEN_ADAPTATION, _GEMMA_ADAPTATION]:
            fn = code_gen_for(val)
            assert callable(fn), f"Not callable for input {val!r}: {fn!r}"


# ---------------------------------------------------------------------------
# (E) solve_routed with the default solver dispatches to the right code-gen
#     (via ADAPTATION_REGISTRY monkeypatching — no Jetson, no real LLM)
# ---------------------------------------------------------------------------

class TestSolveRoutedDefaultSolverDispatch:
    """The DEFAULT solver (no solve_fn injected) uses ADAPTATION_REGISTRY to
    pick the code-gen for the routed model.  We monkeypatch the registry entries
    to stub callables that record invocations.
    """

    @staticmethod
    def _make_ok_rewire(registry: ModelRegistry):
        def rewire_fn(model_id: str, reg: Any) -> dict:
            return {"model_id": model_id, "ok": True, "error": None,
                    "swapped": True, "served_before": "none", "served_after": model_id,
                    "adaptation_active": []}
        return rewire_fn

    @staticmethod
    def _qwen_route_fn(qwen_model_id: str = "qwen2.5-coder-3b"):
        def route_fn(problem: Any, registry: Any) -> dict:
            return {
                "model_id": qwen_model_id,
                "problem_class": "standalone-fn-gen",
                "confidence": 1.0,
                "rationale": "forced to qwen for test",
            }
        return route_fn

    @staticmethod
    def _gemma_route_fn(gemma_model_id: str = "gemma-4-e2b"):
        def route_fn(problem: Any, registry: Any) -> dict:
            return {
                "model_id": gemma_model_id,
                "problem_class": "single-file-repair",
                "confidence": 1.0,
                "rationale": "forced to gemma for test",
            }
        return route_fn

    def test_qwen_routed_invokes_qwen_code_gen(self, monkeypatch):
        """When routed to qwen, _default_solve_fn calls the qwen code-gen."""
        qwen_calls: list[tuple] = []
        gemma_calls: list[tuple] = []

        def mock_qwen(spec: str, name: str, context: str = "") -> str:
            qwen_calls.append((spec, name, context))
            return f"def {name}(): return 42"

        def mock_gemma(spec: str, name: str, context: str = "") -> str:
            gemma_calls.append((spec, name, context))
            return f"def {name}(): return 0"

        monkeypatch.setitem(adapt_mod.ADAPTATION_REGISTRY, "qwen-instruct-direct", mock_qwen)
        monkeypatch.setitem(adapt_mod.ADAPTATION_REGISTRY, "gherkin-decompose", mock_gemma)

        registry = _stub_registry_two_models()
        rewire_fn = self._make_ok_rewire(registry)

        problem = {"intent": "implement add", "name": "add", "context": ""}

        result = solve_routed(
            problem,
            registry=registry,
            route_fn=self._qwen_route_fn(),
            rewire_fn=rewire_fn,
            # NO solve_fn injected — uses _default_solve_fn with adaptation
        )

        assert result["ok"] is True, f"Expected ok=True, got: {result}"
        assert len(qwen_calls) >= 1, "qwen code-gen should have been called"
        assert len(gemma_calls) == 0, "gemma code-gen should NOT be called when qwen is routed"
        assert result["solve"]["code"].startswith("def add")

    def test_gemma_routed_invokes_gemma_code_gen(self, monkeypatch):
        """When routed to gemma, _default_solve_fn calls the gemma code-gen."""
        qwen_calls: list[tuple] = []
        gemma_calls: list[tuple] = []

        def mock_qwen(spec: str, name: str, context: str = "") -> str:
            qwen_calls.append((spec, name, context))
            return f"def {name}(): return 42"

        def mock_gemma(spec: str, name: str, context: str = "") -> str:
            gemma_calls.append((spec, name, context))
            return f"def {name}(): return 0"

        monkeypatch.setitem(adapt_mod.ADAPTATION_REGISTRY, "qwen-instruct-direct", mock_qwen)
        monkeypatch.setitem(adapt_mod.ADAPTATION_REGISTRY, "gherkin-decompose", mock_gemma)

        registry = _stub_registry_two_models()
        rewire_fn = self._make_ok_rewire(registry)

        problem = {"intent": "fix the sort function", "name": "sort_items", "context": ""}

        result = solve_routed(
            problem,
            registry=registry,
            route_fn=self._gemma_route_fn(),
            rewire_fn=rewire_fn,
            # NO solve_fn injected — uses _default_solve_fn with adaptation
        )

        assert result["ok"] is True, f"Expected ok=True, got: {result}"
        assert len(gemma_calls) >= 1, "gemma code-gen should have been called"
        assert len(qwen_calls) == 0, "qwen code-gen should NOT be called when gemma is routed"
        assert result["solve"]["code"].startswith("def sort_items")

    def test_qwen_and_gemma_routed_call_different_code_gens(self, monkeypatch):
        """Two different routings call two different code-gens (diversity in action)."""
        calls: dict[str, list] = {"qwen": [], "gemma": []}

        def mock_qwen(spec: str, name: str, context: str = "") -> str:
            calls["qwen"].append(name)
            return f"def {name}(): return 'qwen'"

        def mock_gemma(spec: str, name: str, context: str = "") -> str:
            calls["gemma"].append(name)
            return f"def {name}(): return 'gemma'"

        monkeypatch.setitem(adapt_mod.ADAPTATION_REGISTRY, "qwen-instruct-direct", mock_qwen)
        monkeypatch.setitem(adapt_mod.ADAPTATION_REGISTRY, "gherkin-decompose", mock_gemma)

        registry = _stub_registry_two_models()
        rewire_fn = self._make_ok_rewire(registry)

        problem_q = {"intent": "impl foo", "name": "foo"}
        problem_g = {"intent": "impl bar", "name": "bar"}

        result_q = solve_routed(problem_q, registry=registry, route_fn=self._qwen_route_fn(), rewire_fn=rewire_fn)
        result_g = solve_routed(problem_g, registry=registry, route_fn=self._gemma_route_fn(), rewire_fn=rewire_fn)

        assert result_q["ok"] is True
        assert result_g["ok"] is True
        assert "foo" in calls["qwen"]
        assert "bar" in calls["gemma"]
        # No cross-contamination
        assert "foo" not in calls["gemma"]
        assert "bar" not in calls["qwen"]

    def test_rewire_failure_still_short_circuits(self, monkeypatch):
        """Rewire failure prevents solve_fn call — even with the default solve path."""
        gemma_calls: list[tuple] = []

        def mock_gemma(spec: str, name: str, context: str = "") -> str:
            gemma_calls.append((spec, name, context))
            return f"def {name}(): pass"

        monkeypatch.setitem(adapt_mod.ADAPTATION_REGISTRY, "gherkin-decompose", mock_gemma)

        registry = _stub_registry_two_models()

        def fail_rewire(model_id: str, reg: Any) -> dict:
            return {"model_id": model_id, "ok": False, "error": "simulated SSH timeout"}

        problem = {"intent": "fix something", "name": "fix_it"}

        result = solve_routed(
            problem,
            registry=registry,
            route_fn=self._gemma_route_fn(),
            rewire_fn=fail_rewire,
        )

        assert result["ok"] is False
        assert result["solve"] is None
        assert len(gemma_calls) == 0, "code-gen must NOT be called when rewire failed"

    def test_run_tests_loop_with_adaptation_path(self, monkeypatch):
        """When run_tests is in problem, the adaptation path exercises the fix loop."""
        calls: list[str] = []

        def mock_qwen(spec: str, name: str, context: str = "") -> str:
            calls.append(f"gen:{name}")
            return f"def {name}(): return 1"

        monkeypatch.setitem(adapt_mod.ADAPTATION_REGISTRY, "qwen-instruct-direct", mock_qwen)

        registry = _stub_registry_two_models()
        rewire_fn = self._make_ok_rewire(registry)

        test_results = [False, True]  # first call fails, second passes
        test_idx = [0]

        def run_tests(code: str, tests: str):
            idx = test_idx[0]
            test_idx[0] += 1
            passed = test_results[idx] if idx < len(test_results) else True
            return passed, "feedback" if not passed else ""

        problem = {
            "intent": "implement square",
            "name": "square",
            "context": "",
            "run_tests": run_tests,
            "max_fix": 2,
        }

        result = solve_routed(
            problem,
            registry=registry,
            route_fn=self._qwen_route_fn(),
            rewire_fn=rewire_fn,
        )

        assert result["ok"] is True
        assert result["solve"]["self_pass"] is True
        # Code-gen called at least twice (first attempt + at least one fix)
        assert len(calls) >= 2, f"Expected multiple code-gen calls; got {calls}"


# ---------------------------------------------------------------------------
# _extract_label: unit tests for the label extraction helper
# ---------------------------------------------------------------------------

class TestExtractLabel:
    def test_string_input(self):
        assert _extract_label("qwen-instruct-direct") == "qwen-instruct-direct"
        assert _extract_label("gherkin-decompose") == "gherkin-decompose"

    def test_none_input(self):
        assert _extract_label(None) == _DEFAULT_LABEL

    def test_empty_string(self):
        assert _extract_label("") == _DEFAULT_LABEL

    def test_qwen_adaptation_dict(self):
        assert _extract_label(_QWEN_ADAPTATION) == "qwen-instruct-direct"

    def test_gemma_nested_adaptation_dict(self):
        """Gemma's nested prompts dict is unwrapped correctly."""
        assert _extract_label(_GEMMA_ADAPTATION) == "gherkin-decompose"

    def test_model_profile_qwen(self):
        profile = _make_model_profile("qwen2.5-coder-3b", _QWEN_ADAPTATION)
        assert _extract_label(profile) == "qwen-instruct-direct"

    def test_model_profile_gemma(self):
        profile = _make_model_profile("gemma-4-e2b", _GEMMA_ADAPTATION)
        assert _extract_label(profile) == "gherkin-decompose"

    def test_missing_prompts_key(self):
        assert _extract_label({"tools": ["abc"]}) == _DEFAULT_LABEL

    def test_solve_style_key_directly(self):
        """adaptation dict with top-level solve_style (alternative layout)."""
        assert _extract_label({"solve_style": "gherkin-decompose"}) == "gherkin-decompose"


# ---------------------------------------------------------------------------
# (F) r1-reasoning adaptation (qwen3-4b-thinking) — EXT-021 TASK-34 follow-up
# ---------------------------------------------------------------------------

# #EXT-021-REQ-3 r1-reasoning-wiring Start
class TestR1ReasoningAdaptation:
    """'r1-reasoning' must resolve to r1_code-based gen (qwen3-4b-thinking path).

    qwen3-4b-thinking uses adaptation = {"prompts": "r1-reasoning"}, which maps
    to harness.r1_adapt.r1_code via ADAPTATION_REGISTRY.  The <think> block is
    stripped and the LAST fenced code block is extracted — all inside r1_code.
    """

    def test_r1_reasoning_label_in_registry(self):
        """'r1-reasoning' is a registered key in ADAPTATION_REGISTRY."""
        assert "r1-reasoning" in ADAPTATION_REGISTRY, (
            "ADAPTATION_REGISTRY must have 'r1-reasoning' for qwen3-4b-thinking routing"
        )

    def test_r1_reasoning_string_label_returns_r1_callable(self):
        """code_gen_for('r1-reasoning') returns _r1_reasoning_code_gen."""
        fn = code_gen_for("r1-reasoning")
        assert fn is _r1_reasoning_code_gen, (
            f"Expected _r1_reasoning_code_gen, got {fn!r}"
        )

    def test_r1_reasoning_is_distinct_from_gemma_and_qwen(self):
        """r1-reasoning callable is different from both gemma and qwen callables."""
        r1_fn = code_gen_for("r1-reasoning")
        assert r1_fn is not _gemma_gherkin_code_gen, "r1 != gemma (different model path)"
        assert r1_fn is not _qwen_instruct_code_gen, "r1 != qwen (different model path)"

    def test_qwen3_thinking_adaptation_dict_resolves_to_r1(self):
        """An adaptation dict matching qwen3-4b-thinking's real shape resolves to r1."""
        # Real qwen3-4b-thinking.json shape: adaptation["prompts"] is a string "r1-reasoning"
        adaptation = {
            "prompts": "r1-reasoning",
            "note": "Qwen3 native <think> reasoning; r1_code parses code after </think>",
        }
        fn = code_gen_for(adaptation)
        assert fn is _r1_reasoning_code_gen, (
            f"qwen3-4b-thinking adaptation dict must resolve to r1_code-based callable, "
            f"got {fn!r}"
        )

    def test_r1_reasoning_label_extraction(self):
        """_extract_label correctly reads 'r1-reasoning' from qwen3-4b-thinking-shaped dict."""
        adaptation = {"prompts": "r1-reasoning", "note": "stub"}
        assert _extract_label(adaptation) == "r1-reasoning"

    def test_code_gen_for_r1_is_callable(self):
        """The returned r1 callable has the uniform (spec, name, context) signature."""
        import inspect
        fn = code_gen_for("r1-reasoning")
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        # Must accept at least subject_or_spec and name; context is optional
        assert len(params) >= 2, f"Expected >=2 params, got: {params}"
# #EXT-021-REQ-3 r1-reasoning-wiring End
