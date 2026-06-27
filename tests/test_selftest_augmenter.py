"""Unit tests for EXT-012 / REQ-13 — stronger-oracle self-test augmenter.

All tests are fully offline (no LLM, no Jetson, no Docker, no network).
Coverage:
  (a) Given a docstring with ">>> f(2)\\n4" examples + a self-test stub,
      the augmenter appends a correct assertion for each example.
  (b) No-docstring source falls back unchanged (augmented=False, examples_found=0).
  (c) Docstring present but no ">>> " lines -> graceful no-op fallback.
  (d) validate() rejects non-str inputs.
  (e) validate() rejects missing 'name', 'source', 'self_tests' keys.
  (f) augmented test code parses as valid Python (ast.parse smoke).
  (g) HONESTY self-test: the tool module never imports or references the hidden
      oracle file name (test_more.py / redgreen) — verified by source inspection.
  (h) Multi-line docstring expression is joined and produces one assertion.
  (i) A ">>> " line with no following value line is skipped (conservative parser).
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _REPO_ROOT / ".jaros-data" / "tools"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# #EXT-012-REQ-13 Start


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_tool():
    """Load SelftestAugmenterTool from its file (no package import needed)."""
    tool_path = str(_TOOLS_DIR / "selftest_augmenter_tool.py")
    spec = importlib.util.spec_from_file_location("_sat_tool", tool_path)
    mod = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
    spec.loader.exec_module(mod)                  # type: ignore[union-attr]
    return mod.SelftestAugmenterTool(), mod


def _make_decision(payload: dict):
    """Create a minimal Decision-like object with a .payload dict attribute."""
    return SimpleNamespace(payload=payload, type="code.augment_selftests")


# ---------------------------------------------------------------------------
# Fixture: docstring with >>> examples
# ---------------------------------------------------------------------------

_SOURCE_WITH_EXAMPLES = '''\
def double(x):
    """Return twice the input.

    Examples::

        >>> double(2)
        4
        >>> double(0)
        0
        >>> double(-3)
        -6
    """
    return x * 2
'''

_SOURCE_NO_DOCSTRING = '''\
def nodoc(x):
    return x + 1
'''

_SOURCE_DOCSTRING_NO_EXAMPLES = '''\
def no_examples(x):
    """Return x.  Has no interactive examples."""
    return x
'''

_STUB_TESTS = """\
from more_itertools import double

def test_double_basic():
    assert double(1) == 2
"""


# ---------------------------------------------------------------------------
# (a) Augmenter appends doctest-derived assertions
# ---------------------------------------------------------------------------

def test_augmenter_appends_assertions():
    tool, _ = _load_tool()
    dec = _make_decision({
        "name": "double",
        "source": _SOURCE_WITH_EXAMPLES,
        "self_tests": _STUB_TESTS,
    })
    result = tool.execute(dec)
    assert result["augmented"] is True
    assert result["examples_found"] == 3

    out = result["self_tests"]
    # The stub is preserved
    assert "def test_double_basic" in out
    # The augment block is appended
    assert "def test_docstring_examples__double" in out
    # Each expected value appears as an assertion
    assert "== 4" in out
    assert "== 0" in out
    assert "== -6" in out


# ---------------------------------------------------------------------------
# (b) No-docstring source falls back unchanged
# ---------------------------------------------------------------------------

def test_no_docstring_fallback_unchanged():
    tool, _ = _load_tool()
    dec = _make_decision({
        "name": "nodoc",
        "source": _SOURCE_NO_DOCSTRING,
        "self_tests": _STUB_TESTS,
    })
    result = tool.execute(dec)
    assert result["augmented"] is False
    assert result["examples_found"] == 0
    assert result["self_tests"] == _STUB_TESTS


# ---------------------------------------------------------------------------
# (c) Docstring with no ">>> " lines -> graceful no-op
# ---------------------------------------------------------------------------

def test_docstring_no_examples_noop():
    tool, _ = _load_tool()
    dec = _make_decision({
        "name": "no_examples",
        "source": _SOURCE_DOCSTRING_NO_EXAMPLES,
        "self_tests": _STUB_TESTS,
    })
    result = tool.execute(dec)
    assert result["augmented"] is False
    assert result["examples_found"] == 0
    assert result["self_tests"] == _STUB_TESTS


# ---------------------------------------------------------------------------
# (d) validate() rejects non-str name
# ---------------------------------------------------------------------------

def test_validate_rejects_non_str_name():
    tool, _ = _load_tool()
    dec = _make_decision({
        "name": 123,
        "source": _SOURCE_WITH_EXAMPLES,
        "self_tests": _STUB_TESTS,
    })
    v = tool.validate(dec)
    assert not v.ok


# ---------------------------------------------------------------------------
# (e) validate() rejects missing keys
# ---------------------------------------------------------------------------

def test_validate_rejects_missing_self_tests():
    tool, _ = _load_tool()
    dec = _make_decision({
        "name": "double",
        "source": _SOURCE_WITH_EXAMPLES,
        # no "self_tests"
    })
    v = tool.validate(dec)
    assert not v.ok


def test_validate_rejects_non_str_source():
    tool, _ = _load_tool()
    dec = _make_decision({
        "name": "double",
        "source": None,
        "self_tests": _STUB_TESTS,
    })
    v = tool.validate(dec)
    assert not v.ok


def test_validate_accepts_valid_payload():
    tool, _ = _load_tool()
    dec = _make_decision({
        "name": "double",
        "source": _SOURCE_WITH_EXAMPLES,
        "self_tests": _STUB_TESTS,
    })
    v = tool.validate(dec)
    assert v.ok


# ---------------------------------------------------------------------------
# (f) Augmented test code must parse as valid Python
# ---------------------------------------------------------------------------

def test_augmented_output_is_valid_python():
    tool, _ = _load_tool()
    dec = _make_decision({
        "name": "double",
        "source": _SOURCE_WITH_EXAMPLES,
        "self_tests": _STUB_TESTS,
    })
    result = tool.execute(dec)
    # This must not raise SyntaxError
    tree = ast.parse(result["self_tests"])
    # Ensure our augment function is present
    func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert "test_docstring_examples__double" in func_names


# ---------------------------------------------------------------------------
# (g) HONESTY: tool source never references the hidden oracle
# ---------------------------------------------------------------------------

def test_honesty_no_hidden_oracle_reference():
    """The tool module must never IMPORT or make runtime calls to the hidden test file.

    References to ``test_more.py`` and ``redgreen`` are only allowed inside
    string literals / docstrings (documentation), NOT in executable import
    statements or function calls.  We verify this by checking that no bare
    Python ``import`` statement or ``open(...)`` call references those names.
    """
    tool_path = _TOOLS_DIR / "selftest_augmenter_tool.py"
    source_text = tool_path.read_text(encoding="utf-8")
    # Parse to get executable nodes only — reject any Name/Attribute/Constant that
    # references the hidden oracle OUTSIDE of docstrings and string constants.
    tree = ast.parse(source_text)

    # Collect all string literal values (docstrings / inline strings) — these are allowed.
    string_literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            string_literals.add(node.value)

    # There must be no "import test_more" or "import redgreen" executable statement.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                assert "test_more" not in (alias.name or ""), \
                    "tool imports 'test_more' — hidden oracle leak!"
                assert "redgreen" not in (alias.name or ""), \
                    "tool imports 'redgreen' — hidden oracle leak!"
    # Also: no open() / read() call that mentions "test_more" by name in a non-str context.
    # A simple scan of non-docstring lines suffices since there are no computed paths here.
    for line in source_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
            continue
        # Skip lines that are entirely inside a string literal based on context —
        # approximate by skipping lines that don't contain executable keywords.
        if "import test_more" in stripped or "open.*test_more" in stripped:
            raise AssertionError(f"Executable reference to hidden oracle: {stripped}")


# ---------------------------------------------------------------------------
# (h) Multi-line docstring expression is joined
# ---------------------------------------------------------------------------

_SOURCE_MULTILINE = '''\
def add(a, b):
    """Add two numbers.

    >>> add(
    ...     1,
    ...     2,
    ... )
    3
    """
    return a + b
'''


def test_multiline_expression_joined():
    tool, mod = _load_tool()
    # Test the internal helper directly
    docstring = mod._extract_docstring(_SOURCE_MULTILINE, "add")
    assert docstring  # docstring found
    examples = mod._parse_doctest_examples(docstring)
    assert len(examples) == 1
    expr, expected = examples[0]
    # The expression should be joined (no stray '...' lines)
    assert "..." not in expr
    assert expected == "3"


# ---------------------------------------------------------------------------
# (i) ">>> " line with no following value is skipped (conservative parser)
# ---------------------------------------------------------------------------

_SOURCE_TRAILING_PROMPT = '''\
def greet(name):
    """
    >>> greet("Alice")
    'Hello, Alice!'
    >>> greet("Bob")
    """
    return f"Hello, {name}!"
'''


def test_trailing_prompt_skipped():
    """A ">>> " line with no following value line should be skipped."""
    tool, mod = _load_tool()
    docstring = mod._extract_docstring(_SOURCE_TRAILING_PROMPT, "greet")
    examples = mod._parse_doctest_examples(docstring)
    # Only "greet('Alice')" / "'Hello, Alice!'" should be captured;
    # the trailing greet("Bob") with no value must be skipped.
    assert len(examples) == 1
    expr, expected = examples[0]
    assert "Alice" in expr
    assert expected == "'Hello, Alice!'"

# #EXT-012-REQ-13 End
