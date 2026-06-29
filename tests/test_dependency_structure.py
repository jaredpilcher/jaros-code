"""tests/test_dependency_structure.py — EXT-028 offline unit tests.

No LLM, no network, no Docker required.  Exercises method_dependencies and
dependency_brief against synthetic Python module strings.
"""
from __future__ import annotations

import ast

import pytest

from harness.dependency_structure import dependency_brief, method_dependencies

# ── Sample module ─────────────────────────────────────────────────────────────
#
# Structure:
#   COUNTER = 0          <- module-level state
#   helper(x)            <- callee of f
#   f(n)                 <- target: calls helper(), uses COUNTER via global
#   g(n)                 <- caller of f
#   reset()              <- also uses COUNTER via global -> sibling sharing state
#   unrelated(x)         <- neither calls f nor touches COUNTER

_MODULE = """\
import os

COUNTER = 0

def helper(x):
    return x + 1

def f(n):
    global COUNTER
    COUNTER += 1
    return helper(n)

def g(n):
    return f(n) * 2

def reset():
    global COUNTER
    COUNTER = 0

def unrelated(x):
    return x * x
"""


# ── TestMethodDependencies ────────────────────────────────────────────────────

class TestMethodDependencies:

    def test_callees_contains_helper(self):
        deps = method_dependencies(_MODULE, "f")
        callee_names = [c["name"] for c in deps["callees"]]
        assert "helper" in callee_names

    def test_callers_contains_g(self):
        deps = method_dependencies(_MODULE, "f")
        assert "g" in deps["callers"]

    def test_module_state_used_contains_counter(self):
        deps = method_dependencies(_MODULE, "f")
        assert "COUNTER" in deps["module_state_used"]

    def test_callee_has_signature_string(self):
        """Each callee entry must have a 'signature' key with 'def helper' text."""
        deps = method_dependencies(_MODULE, "f")
        helper_entry = next(
            (c for c in deps["callees"] if c["name"] == "helper"), None
        )
        assert helper_entry is not None
        assert "def helper" in helper_entry["signature"]

    def test_helper_is_not_a_caller(self):
        """helper() doesn't call f(), so it must not appear in callers."""
        deps = method_dependencies(_MODULE, "f")
        assert "helper" not in deps["callers"]

    def test_target_not_in_own_callees(self):
        """f() does not call itself — must not appear in callees."""
        deps = method_dependencies(_MODULE, "f")
        callee_names = [c["name"] for c in deps["callees"]]
        assert "f" not in callee_names

    def test_siblings_sharing_state_contains_reset(self):
        """reset() also uses COUNTER via global — must appear in siblings."""
        deps = method_dependencies(_MODULE, "f")
        assert "reset" in deps["siblings_sharing_state"]

    def test_unrelated_not_in_siblings(self):
        """unrelated() does not touch COUNTER — must not appear in siblings."""
        deps = method_dependencies(_MODULE, "f")
        assert "unrelated" not in deps["siblings_sharing_state"]

    def test_parse_error_returns_partial_no_crash(self):
        """Malformed source must return the base dict without raising."""
        deps = method_dependencies("def broken(: invalid syntax!!!", "broken")
        assert deps["target"] == "broken"
        assert deps["callees"] == []
        assert deps["callers"] == []
        assert deps["module_state_used"] == []
        assert deps["siblings_sharing_state"] == []

    def test_target_not_found_returns_partial(self):
        """Requesting a name not in the module returns empty lists."""
        deps = method_dependencies(_MODULE, "nonexistent")
        assert deps["target"] == "nonexistent"
        assert deps["callees"] == []
        assert deps["callers"] == []

    def test_return_structure_has_all_keys(self):
        """Result must always contain the five expected keys."""
        deps = method_dependencies(_MODULE, "f")
        for key in (
            "target", "callees", "callers", "module_state_used", "siblings_sharing_state"
        ):
            assert key in deps, f"missing key: {key}"

    def test_callers_of_helper(self):
        """From helper's perspective, f() is its caller."""
        deps = method_dependencies(_MODULE, "helper")
        assert "f" in deps["callers"]

    def test_no_module_state_for_pure_function(self):
        src = """\
def add(a, b):
    return a + b

def mul(a, b):
    return a * b
"""
        deps = method_dependencies(src, "add")
        assert deps["module_state_used"] == []
        assert deps["siblings_sharing_state"] == []

    def test_results_are_sorted(self):
        """All list outputs must be sorted (deterministic)."""
        # Build a module with multiple callers / callees
        src = """\
X = 0

def alpha(x):
    return x

def beta(x):
    return x

def target(n):
    global X
    alpha(n)
    beta(n)

def zulu(n):
    target(n)

def anna(n):
    target(n)
"""
        deps = method_dependencies(src, "target")
        callee_names = [c["name"] for c in deps["callees"]]
        assert callee_names == sorted(callee_names)
        assert deps["callers"] == sorted(deps["callers"])
        assert deps["module_state_used"] == sorted(deps["module_state_used"])

    def test_empty_source_no_crash(self):
        deps = method_dependencies("", "anything")
        assert isinstance(deps, dict)
        assert deps["callees"] == []

    def test_module_importable_no_side_effects(self):
        """The module's own source must parse cleanly."""
        import harness.dependency_structure as ds
        src = open(ds.__file__, encoding="utf-8").read()
        ast.parse(src)  # must not raise


# ── TestDependencyBrief ───────────────────────────────────────────────────────

class TestDependencyBrief:

    def _deps_f(self) -> dict:
        return method_dependencies(_MODULE, "f")

    def test_brief_contains_target_name(self):
        brief = dependency_brief(self._deps_f())
        assert "f" in brief

    def test_brief_contains_caller_names(self):
        brief = dependency_brief(self._deps_f())
        assert "g" in brief

    def test_brief_contains_callee_names(self):
        brief = dependency_brief(self._deps_f())
        assert "helper" in brief

    def test_brief_contains_state_names(self):
        brief = dependency_brief(self._deps_f())
        assert "COUNTER" in brief

    def test_brief_contains_sibling_names(self):
        brief = dependency_brief(self._deps_f())
        assert "reset" in brief

    def test_brief_has_suggested_order_section(self):
        brief = dependency_brief(self._deps_f())
        assert "order" in brief.lower()

    def test_brief_is_nonempty_string(self):
        brief = dependency_brief(self._deps_f())
        assert isinstance(brief, str)
        assert len(brief) > 0

    def test_brief_empty_deps_no_crash(self):
        """All-empty deps dict must produce a valid string without crashing."""
        empty = {
            "target": "foo",
            "callees": [],
            "callers": [],
            "module_state_used": [],
            "siblings_sharing_state": [],
        }
        brief = dependency_brief(empty)
        assert "foo" in brief
        assert isinstance(brief, str)

    def test_brief_missing_keys_no_crash(self):
        """Even an entirely empty dict must not raise."""
        brief = dependency_brief({})
        assert isinstance(brief, str)
