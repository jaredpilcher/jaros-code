"""EXT-003 loop helper tests (deterministic, no model calls)."""

from __future__ import annotations

from harness.coding_loop import python_syntax_error


def test_syntax_error_none_for_valid():
    assert python_syntax_error("def f():\n    return 1\n") is None


def test_syntax_error_caught_for_dropped_quote():
    # The exact class of failure observed on greet_format: a dropped closing quote.
    err = python_syntax_error('def greet(name):\n    return "Hello, " + name + "!\n')
    assert err is not None
    assert "line" in err
