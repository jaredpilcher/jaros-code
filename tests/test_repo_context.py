"""tests/test_repo_context.py — EXT-017 offline unit tests for enriched_file_context.

No LLM, no network, no Docker required.
"""

import ast

import pytest

# Verifies the module is importable without any side-effects.
from harness.repo_context import enriched_file_context  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture: a small synthetic module
# ---------------------------------------------------------------------------

_MODULE_SRC = """\
import os

CONST = 42

def helper_a(x):
    return x + 1

def helper_b(x, y):
    return x * y

def unrelated_c(z):
    return z - 100

def target_fn(n):
    a = helper_a(n)
    b = helper_b(a, n)
    return b
"""

# A module where the target calls a LARGE helper (> 10 lines).
_MODULE_LARGE_HELPER = """\
import sys

def large_helper(x):
    # line 1
    # line 2
    # line 3
    # line 4
    # line 5
    # line 6
    # line 7
    # line 8
    # line 9
    return x + 1

def target_fn(n):
    return large_helper(n)
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEnrichedFileContext:
    def test_includes_direct_dependency_a(self):
        result = enriched_file_context(_MODULE_SRC, "target_fn")
        assert "def helper_a" in result

    def test_includes_direct_dependency_b(self):
        result = enriched_file_context(_MODULE_SRC, "target_fn")
        assert "def helper_b" in result

    def test_excludes_unrelated(self):
        result = enriched_file_context(_MODULE_SRC, "target_fn")
        assert "def unrelated_c" not in result

    def test_includes_preamble_import(self):
        result = enriched_file_context(_MODULE_SRC, "target_fn")
        assert "import os" in result

    def test_includes_preamble_constant(self):
        result = enriched_file_context(_MODULE_SRC, "target_fn")
        assert "CONST = 42" in result

    def test_bounded_by_max_chars(self):
        result = enriched_file_context(_MODULE_SRC, "target_fn", max_chars=50)
        assert len(result) <= 50

    def test_fallback_unknown_name(self):
        result = enriched_file_context(_MODULE_SRC, "nonexistent")
        # Should return preamble — non-empty and no exception.
        assert len(result) > 0
        assert "import os" in result

    def test_fallback_bad_src(self):
        result = enriched_file_context("not valid python :::", "target_fn")
        # Must not raise; may be empty or just the broken preamble.
        assert isinstance(result, str)

    def test_large_helper_signature_only(self):
        result = enriched_file_context(_MODULE_LARGE_HELPER, "target_fn")
        # The signature line must appear.
        assert "def large_helper" in result
        # But not an interior body line like "# line 9".
        assert "# line 9" not in result

    def test_default_max_chars_respected(self):
        """Default cap is 1500; result must never exceed it."""
        result = enriched_file_context(_MODULE_SRC, "target_fn")
        assert len(result) <= 1500

    def test_module_importable(self):
        """Smoke-test: ast.parse on the module itself must succeed."""
        import harness.repo_context as rc  # noqa: F401
        src = open(rc.__file__, encoding="utf-8").read()
        ast.parse(src)  # must not raise

    def test_empty_src(self):
        """Empty source must not raise; return empty string."""
        result = enriched_file_context("", "target_fn")
        assert isinstance(result, str)

    def test_target_with_no_helper_calls(self):
        """Target that calls no module-level helpers returns preamble only."""
        src = """\
import math

def solo(x):
    return x * x
"""
        result = enriched_file_context(src, "solo")
        assert "import math" in result
        assert "# Direct dependencies:" not in result
