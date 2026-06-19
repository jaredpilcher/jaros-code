"""EXT-003 loop helper tests (deterministic, no model calls)."""

from __future__ import annotations

from harness.coding_loop import distill_failure, python_syntax_error


def test_distill_failure_keeps_assertion_lines():
    out = ("============ test session ===========\n"
           "collected 1 item\n"
           "test_x.py F\n"
           ">       assert add(2, 3) == 5\n"
           "E       assert 6 == 5\n"
           "1 failed in 0.02s\n")
    d = distill_failure(out)
    assert "assert 6 == 5" in d
    assert "test session" not in d


def test_distill_failure_empty():
    assert distill_failure("") == ""


def test_syntax_error_none_for_valid():
    assert python_syntax_error("def f():\n    return 1\n") is None


def test_syntax_error_caught_for_dropped_quote():
    # The exact class of failure observed on greet_format: a dropped closing quote.
    err = python_syntax_error('def greet(name):\n    return "Hello, " + name + "!\n')
    assert err is not None
    assert "line" in err
