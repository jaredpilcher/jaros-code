"""Tests for harness/model_router.py -- EXT-021 TASK-2/TASK-27 (REQ-2 + REQ-7).

Verifies acceptance criteria:
  (a) A class covered only by a specific model routes to THAT model.
  (b) An unknown / uncovered class routes to default_model() with low
      confidence and a rationale that marks it as a HARNESS-GAP.
  (c) The returned value is inert plain data (no I/O, no model served).
  (d) route() is purely deterministic -- no LLM param, no model-as-judge.
  (e) _failure_signal parses Python error types from traceback fields.
  (f) A problem with a failure signal classifies to the richer prior class.

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
from harness.model_router import route, _failure_signal

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
        decision = route({"is_repo_task": True}, reg, record=False)

        assert decision["model_id"] == "gemma-4-e2b"  # the only / default model
        assert decision["confidence"] < 0.5

    def test_fallback_confidence_is_low(self):
        """Fallback decisions must have clearly low confidence."""
        reg = _gemma_only_registry()
        decision = route({"is_repo_task": True}, reg, record=False)
        assert decision["confidence"] <= 0.3

    def test_fallback_rationale_contains_harness_gap_marker(self):
        """HARNESS-GAP marker must appear so the convergence loop can see it."""
        reg = _gemma_only_registry()
        decision = route({"is_repo_task": True}, reg, record=False)
        assert "HARNESS-GAP" in decision["rationale"]

    def test_fallback_rationale_not_model_limit(self):
        """Misroute is a HARNESS gap, NEVER attributed to a model limit (PRIME-001).

        The rationale may mention 'model limit' when explicitly DENYING it
        (e.g. '...not a model limit'), which is correct.  The forbidden pattern
        is attributing the fallback TO the model without denial.
        """
        reg = _gemma_only_registry()
        decision = route({"is_repo_task": True}, reg, record=False)
        # The gap marker is the positive signal; just verify it's present
        assert "HARNESS-GAP" in decision["rationale"]
        # Must NOT use a bare "is a model limit" or "model ceiling" attribution
        rationale_lower = decision["rationale"].lower()
        assert "is a model limit" not in rationale_lower
        assert "model ceiling" not in rationale_lower

    def test_empty_registry_always_returns_default(self):
        """Even with zero loaded profiles, route() returns the default id."""
        reg = ModelRegistry(profiles=[], default_id="gemma-4-e2b")
        decision = route({"source": "do something"}, reg, record=False)

        assert decision["model_id"] == "gemma-4-e2b"
        assert isinstance(decision["model_id"], str)
        assert len(decision["model_id"]) > 0

    def test_uncovered_failure_class_default_fallbacks_and_records_gap(self):
        """A new failure-signal class with no tally entry falls back to default + HARNESS-GAP."""
        reg = _gemma_only_registry()  # no profile for 'missing-method-or-attr'
        decision = route(
            {"traceback": "AttributeError: 'Foo' has no attribute 'bar'"},
            reg,
            record=False,  # stay side-effect-free in tests
        )
        # class is resolved via failure signal
        assert decision["problem_class"] == "missing-method-or-attr"
        # no tally entry -> HARNESS-GAP fallback
        assert decision["model_id"] == "gemma-4-e2b"
        assert decision["confidence"] <= 0.3
        assert "HARNESS-GAP" in decision["rationale"]


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
# (d) route() is purely deterministic -- no llm param, no model-as-judge
# ---------------------------------------------------------------------------

class TestRouteDeterministic:
    """Acceptance criterion (d): route() is deterministic, no LLM path."""

    def test_route_signature_has_no_llm_param(self):
        """route() must NOT accept a positional or keyword 'llm' argument."""
        import inspect
        sig = inspect.signature(route)
        assert "llm" not in sig.parameters, (
            "route() must not have an llm param -- LLM-classification path removed (REQ-2)"
        )

    def test_same_problem_always_same_result(self):
        """No randomness: same problem always produces the same decision."""
        reg = _two_model_registry()
        problem = {"source": ">>> foo(1)\n1", "has_examples": True}
        r1 = route(problem, reg)
        r2 = route(problem, reg)
        assert r1 == r2

    def test_non_dict_problem_handled_gracefully(self):
        """A plain string or object as problem does not raise."""
        reg = _gemma_only_registry()
        # Plain string -- _to_dict falls back to {}
        result = route("fix the bug in foo.py", reg)
        assert isinstance(result, dict)
        assert "model_id" in result

    def test_empty_problem_handled(self):
        """An empty dict produces a valid decision."""
        reg = _gemma_only_registry()
        result = route({}, reg)
        assert isinstance(result, dict)
        assert result["model_id"] == reg.default_model()

    def test_repo_root_key_implies_repo_task(self):
        """Presence of repo_root (no explicit flag) classifies as repo task."""
        reg = _two_model_registry()
        result = route({"repo_root": "/home/user/myproject"}, reg)
        assert result["problem_class"] == "multi-step-repo"
        assert result["model_id"] == "strong-model-7b"

    def test_files_list_implies_multi_file(self):
        """files=[a, b] with no explicit flag derives is_multi_file=True."""
        reg = _two_model_registry()
        result = route({"files": ["a.py", "b.py"]}, reg)
        assert result["problem_class"] == "multi-step-repo"
        assert result["model_id"] == "strong-model-7b"

    def test_single_file_no_examples_is_repair(self):
        """No examples, not repo, single file -> single-file-repair class."""
        reg = _gemma_only_registry()
        result = route({"source": "def foo(): pass", "has_examples": False}, reg)
        assert result["problem_class"] == "single-file-repair"

    def test_rationale_contains_method_label(self):
        """Rationale must expose which classification method was used."""
        reg = _gemma_only_registry()
        result = route({"source": "def foo(): pass"}, reg)
        assert "method=" in result["rationale"]


# ---------------------------------------------------------------------------
# (e) _failure_signal parses Python error types from traceback fields
# ---------------------------------------------------------------------------

class TestFailureSignal:
    """Acceptance criterion (e): _failure_signal deterministically parses tracebacks."""

    def test_returns_none_when_no_failure_signal(self):
        """A plain docstring-only problem has no failure signal."""
        assert _failure_signal({"source": "def add(a, b):\n    >>> add(1,2)\n    3"}) is None

    def test_returns_none_for_empty_dict(self):
        assert _failure_signal({}) is None

    def test_parses_attribute_error_from_traceback_field(self):
        tb = (
            "Traceback (most recent call last):\n"
            "  File 'test_foo.py', line 5, in test_bar\n"
            "    obj.baz()\n"
            "AttributeError: 'Foo' has no attribute 'baz'"
        )
        sig = _failure_signal({"traceback": tb})
        assert sig is not None
        assert sig["error_type"] == "AttributeError"

    def test_extracts_symbol_from_attribute_error(self):
        tb = "AttributeError: 'MyClass' has no attribute 'compute'"
        sig = _failure_signal({"traceback": tb})
        assert sig is not None
        assert sig.get("symbol") == "compute"

    def test_parses_assertion_error(self):
        tb = "AssertionError: assert 1 == 2"
        sig = _failure_signal({"test_output": tb})
        assert sig is not None
        assert sig["error_type"] == "AssertionError"

    def test_parses_type_error(self):
        tb = "TypeError: foo() takes 1 positional argument but 2 were given"
        sig = _failure_signal({"error": tb})
        assert sig is not None
        assert sig["error_type"] == "TypeError"

    def test_parses_import_error(self):
        tb = "ImportError: cannot import name 'bar' from 'mymodule'"
        sig = _failure_signal({"failing_test": tb})
        assert sig is not None
        assert sig["error_type"] == "ImportError"

    def test_parses_module_not_found_before_import_error(self):
        """ModuleNotFoundError is checked before ImportError (it is a subclass)."""
        tb = "ModuleNotFoundError: No module named 'mylib'"
        sig = _failure_signal({"traceback": tb})
        assert sig is not None
        assert sig["error_type"] == "ModuleNotFoundError"

    def test_parses_name_error(self):
        tb = "NameError: name 'compute_sum' is not defined"
        sig = _failure_signal({"traceback": tb})
        assert sig is not None
        assert sig["error_type"] == "NameError"
        assert sig.get("symbol") == "compute_sum"

    def test_parses_index_error(self):
        tb = "IndexError: list index out of range"
        sig = _failure_signal({"traceback": tb})
        assert sig is not None
        assert sig["error_type"] == "IndexError"

    def test_parses_key_error(self):
        tb = "KeyError: 'missing_key'"
        sig = _failure_signal({"traceback": tb})
        assert sig is not None
        assert sig["error_type"] == "KeyError"

    def test_parses_value_error(self):
        tb = "ValueError: invalid literal for int() with base 10: 'abc'"
        sig = _failure_signal({"traceback": tb})
        assert sig is not None
        assert sig["error_type"] == "ValueError"

    def test_traceback_embedded_in_context_field(self):
        """A 'context' field that contains 'Traceback' is also scanned."""
        context = (
            "Previous run failed:\n"
            "Traceback (most recent call last):\n"
            "  File 'x.py', line 1\n"
            "NameError: name 'missing_fn' is not defined"
        )
        sig = _failure_signal({"context": context})
        assert sig is not None
        assert sig["error_type"] == "NameError"

    def test_context_without_traceback_keyword_ignored(self):
        """A 'context' field without 'Traceback' text is NOT scanned."""
        # context has an error type name but no 'Traceback' keyword
        sig = _failure_signal({"context": "The function raised AttributeError sometimes"})
        assert sig is None

    def test_task_field_with_traceback_is_scanned(self):
        """A 'task' field embedding a traceback is scanned."""
        task = "Fix this error:\nTraceback...\nAssertionError: expected 3 got 4"
        sig = _failure_signal({"task": task})
        assert sig is not None
        assert sig["error_type"] == "AssertionError"


# ---------------------------------------------------------------------------
# (f) Failure signal -> richer prior class; structural path unaffected
# ---------------------------------------------------------------------------

class TestFailureSignalClassification:
    """Acceptance criterion (f): failure signal maps to richer prior class."""

    def test_attribute_error_classifies_missing_method_or_attr(self):
        """AttributeError traceback -> problem_class = 'missing-method-or-attr'."""
        reg = _gemma_only_registry()
        tb = (
            "Traceback (most recent call last):\n"
            "  File 'test_foo.py', line 3\n"
            "AttributeError: 'Foo' has no attribute 'run'"
        )
        decision = route({"traceback": tb}, reg, record=False)
        assert decision["problem_class"] == "missing-method-or-attr"
        assert "failure-signal" in decision["rationale"]

    def test_assertion_error_classifies_logic_or_assertion(self):
        """AssertionError -> 'logic-or-assertion'."""
        reg = _gemma_only_registry()
        decision = route({"test_output": "AssertionError: expected 5 got 3"}, reg, record=False)
        assert decision["problem_class"] == "logic-or-assertion"

    def test_type_error_classifies_signature_or_type(self):
        """TypeError -> 'signature-or-type'."""
        reg = _gemma_only_registry()
        decision = route(
            {"error": "TypeError: foo() missing 1 required positional argument: 'x'"},
            reg,
            record=False,
        )
        assert decision["problem_class"] == "signature-or-type"

    def test_import_error_classifies_missing_import(self):
        """ImportError -> 'missing-import'."""
        reg = _gemma_only_registry()
        decision = route(
            {"failing_test": "ImportError: cannot import name 'util' from 'mymodule'"},
            reg,
            record=False,
        )
        assert decision["problem_class"] == "missing-import"

    def test_module_not_found_classifies_missing_import(self):
        """ModuleNotFoundError -> 'missing-import'."""
        reg = _gemma_only_registry()
        decision = route(
            {"traceback": "ModuleNotFoundError: No module named 'mylib'"},
            reg,
            record=False,
        )
        assert decision["problem_class"] == "missing-import"

    def test_name_error_classifies_undefined_name(self):
        """NameError -> 'undefined-name'."""
        reg = _gemma_only_registry()
        decision = route(
            {"traceback": "NameError: name 'missing_fn' is not defined"},
            reg,
            record=False,
        )
        assert decision["problem_class"] == "undefined-name"

    def test_index_error_classifies_bounds_or_key(self):
        """IndexError -> 'bounds-or-key'."""
        reg = _gemma_only_registry()
        decision = route(
            {"traceback": "IndexError: list index out of range"},
            reg,
            record=False,
        )
        assert decision["problem_class"] == "bounds-or-key"

    def test_key_error_classifies_bounds_or_key(self):
        """KeyError -> 'bounds-or-key'."""
        reg = _gemma_only_registry()
        decision = route({"traceback": "KeyError: 'my_key'"}, reg, record=False)
        assert decision["problem_class"] == "bounds-or-key"

    def test_docstring_only_problem_classifies_standalone_fn_gen(self):
        """A plain docstring / has_examples problem still goes through structural path."""
        reg = _two_model_registry()
        decision = route(
            {"source": "def add(a, b):\n    >>> add(1, 2)\n    3", "has_examples": True},
            reg,
        )
        assert decision["problem_class"] == "standalone-fn-gen"
        assert "structural" in decision["rationale"]

    def test_no_failure_signal_uses_structural_method(self):
        """Without a failure signal, rationale reports 'structural' method."""
        reg = _gemma_only_registry()
        decision = route({"source": "def foo(): pass"}, reg)
        assert "structural" in decision["rationale"]

    def test_failure_signal_method_label_in_rationale(self):
        """With a failure signal, rationale reports 'failure-signal' method."""
        reg = _gemma_only_registry()
        decision = route(
            {"traceback": "AttributeError: 'X' has no attribute 'y'"},
            reg,
            record=False,
        )
        assert "failure-signal" in decision["rationale"]
