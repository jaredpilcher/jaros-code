"""Offline tests for harness/eval_qwen_mbpp.py — correct MBPP fn_name handling.

All tests are OFFLINE: qwen_code is injected as a fake callable.
_run_with_treekill is either injected (for score-path tests) or kept real (for
solution-assembly / importability tests that run pytest in a subprocess).

Core correctness property under test
=====================================
MBPP's CRITICAL difference from HumanEval: the function name comes from the
TEST ASSERTS (e.g. ``assert add_two_numbers(1, 2) == 3`` → fn_name =
``add_two_numbers``), NOT from a ``def``-stub default or any generic "solution"
fallback.  A naive HumanEval copy that passes fn_name="solution" to qwen_code
would generate ``def solution(...)`` while the test does
``from solution import add_two_numbers`` → ImportError → every task fails → a
FALSE-low number.  These tests prove the correct path is taken.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.eval_qwen_mbpp import run_qwen_mbpp, _gather_needed_imports
from harness.mbpp import _entry_point


# ---------------------------------------------------------------------------
# Stub MBPP problems
# ---------------------------------------------------------------------------

def _make_problem(task_id: int, text: str, fn_name: str, test_list: list[str],
                  test_setup_code: str = "") -> dict:
    """Create a minimal MBPP problem dict (mirrors the real mbpp.jsonl schema)."""
    return {
        "task_id": task_id,
        "text": text,
        "test_list": test_list,
        "test_setup_code": test_setup_code,
    }


# A trivial passing problem: add_two_numbers(1, 2) == 3
_PROB_ADD = _make_problem(
    task_id=9001,
    text="Write a function to add two numbers.",
    fn_name="add_two_numbers",
    test_list=[
        "assert add_two_numbers(1, 2) == 3",
        "assert add_two_numbers(0, 0) == 0",
        "assert add_two_numbers(-1, 1) == 0",
    ],
)

# A problem where a naive fn_name="solution" would fail the import
_PROB_SQUARE = _make_problem(
    task_id=9002,
    text="Write a function to square a number.",
    fn_name="square_num",
    test_list=["assert square_num(3) == 9", "assert square_num(0) == 0"],
)

# A problem needing math import
_PROB_SQRT = _make_problem(
    task_id=9003,
    text="Write a function to compute the integer square root.",
    fn_name="int_sqrt",
    test_list=["assert int_sqrt(9) == 3", "assert int_sqrt(4) == 2"],
)

# A problem whose qwen output will be WRONG (subtract returns sum -> fail)
_PROB_SUBTRACT = _make_problem(
    task_id=9004,
    text="Write a function to subtract two numbers.",
    fn_name="subtract_numbers",
    test_list=["assert subtract_numbers(5, 3) == 2", "assert subtract_numbers(10, 4) == 6"],
)


# ---------------------------------------------------------------------------
# Tests: _entry_point (the MBPP fn_name extractor)
# ---------------------------------------------------------------------------

class TestEntryPoint:
    """_entry_point parses fn_name from test assert expressions."""

    def test_extracts_name_from_single_assert(self) -> None:
        """Standard assert: fn_name is the callable before the first '('."""
        assert _entry_point(["assert add_two_numbers(1, 2) == 3"]) == "add_two_numbers"

    def test_extracts_name_with_prefix_whitespace(self) -> None:
        """Whitespace after `assert` is tolerated."""
        assert _entry_point(["  assert   my_func(x) == 1"]) == "my_func"

    def test_uses_first_matching_assert(self) -> None:
        """Multiple asserts: first callable wins (consistent with mbpp.py)."""
        result = _entry_point([
            "assert foo(1) == 1",
            "assert bar(2) == 2",
        ])
        assert result == "foo"

    def test_returns_none_for_empty_list(self) -> None:
        """No test_list → None (caller should skip the problem)."""
        assert _entry_point([]) is None

    def test_returns_none_for_no_callable_assert(self) -> None:
        """A bare assert without a call → None."""
        assert _entry_point(["assert True"]) is None

    def test_name_differs_from_solution(self) -> None:
        """The extracted name is never the generic fallback "solution"."""
        name = _entry_point(["assert my_special_fn(x) == x"])
        assert name is not None
        assert name != "solution"
        assert name == "my_special_fn"


# ---------------------------------------------------------------------------
# Tests: _gather_needed_imports
# ---------------------------------------------------------------------------

class TestGatherNeededImports:
    """_gather_needed_imports detects stdlib module usage from attribute access."""

    def test_detects_math_dot_usage(self) -> None:
        code = "def f(x):\n    return math.sqrt(x)\n"
        result = _gather_needed_imports(code)
        assert "import math" in result

    def test_detects_re_dot_usage(self) -> None:
        code = "def f(s):\n    return re.match(r'\\d+', s)\n"
        result = _gather_needed_imports(code)
        assert "import re" in result

    def test_no_imports_for_plain_code(self) -> None:
        code = "def f(a, b):\n    return a + b\n"
        result = _gather_needed_imports(code)
        assert result == ""

    def test_detects_collections_usage(self) -> None:
        code = "def f(lst):\n    return collections.Counter(lst)\n"
        result = _gather_needed_imports(code)
        assert "import collections" in result

    def test_no_false_positive_for_variable_name(self) -> None:
        """A variable like 'math_value' should not trigger 'import math'."""
        code = "def f():\n    math_value = 42\n    return math_value\n"
        result = _gather_needed_imports(code)
        # 'math' does NOT appear as 'math.' so should not be imported
        assert "import math" not in result


# ---------------------------------------------------------------------------
# Tests: fn_name correctness in run_qwen_mbpp
# ---------------------------------------------------------------------------

class TestFnNameExtraction:
    """run_qwen_mbpp uses the CORRECT fn_name from test asserts, not 'solution'."""

    def test_fn_name_passed_to_qwen_is_entry_point(self) -> None:
        """qwen_code receives the real fn_name (add_two_numbers), not 'solution'."""
        captured: list[str] = []

        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            captured.append(fn_name)
            return f"def {fn_name}(a, b):\n    return 0\n"

        def fake_run(cmd: str, cwd: str, timeout: int) -> bool:
            return True

        run_qwen_mbpp(
            n=1,
            _problems_override=[_PROB_ADD],
            _qwen_code_fn=fake_qwen,
            _run_fn=fake_run,
        )

        assert captured, "qwen_code was never called"
        assert captured[0] == "add_two_numbers", (
            f"Expected fn_name='add_two_numbers', got {captured[0]!r}. "
            "MBPP fn_name must come from test_list asserts, NOT a def-stub default."
        )

    def test_fn_name_is_never_solution(self) -> None:
        """The generic fallback 'solution' is never passed as fn_name to qwen_code."""
        captured: list[str] = []

        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            captured.append(fn_name)
            return f"def {fn_name}():\n    pass\n"

        def fake_run(cmd: str, cwd: str, timeout: int) -> bool:
            return True

        problems = [
            _PROB_ADD,    # fn=add_two_numbers
            _PROB_SQUARE, # fn=square_num
        ]
        run_qwen_mbpp(
            n=2,
            _problems_override=problems,
            _qwen_code_fn=fake_qwen,
            _run_fn=fake_run,
        )

        assert "solution" not in captured, (
            f"'solution' appeared as fn_name: {captured}. "
            "MBPP fn_name must come from test_list asserts."
        )
        assert "add_two_numbers" in captured
        assert "square_num" in captured

    def test_different_problems_get_different_fn_names(self) -> None:
        """Each problem gets ITS OWN fn_name (not a shared default)."""
        captured: list[str] = []

        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            captured.append(fn_name)
            return f"def {fn_name}():\n    pass\n"

        def fake_run(cmd: str, cwd: str, timeout: int) -> bool:
            return True

        run_qwen_mbpp(
            n=2,
            _problems_override=[_PROB_ADD, _PROB_SQUARE],
            _qwen_code_fn=fake_qwen,
            _run_fn=fake_run,
        )

        assert len(captured) == 2
        assert captured[0] != captured[1], "Two distinct problems should yield two distinct fn_names"


# ---------------------------------------------------------------------------
# Tests: solution assembly (importable + correct fn_name in the file)
# ---------------------------------------------------------------------------

class TestSolutionAssembly:
    """The assembled solution.py is importable and has the correct function name."""

    def test_solution_py_contains_correct_fn_name(self, tmp_path: Path) -> None:
        """solution.py written to disk has the real fn_name defined (not 'solution')."""
        written_solutions: list[str] = []

        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            return f"def {fn_name}(a, b):\n    return a + b\n"

        def fake_run(cmd: str, cwd: str, timeout: int) -> bool:
            sol = Path(cwd) / "solution.py"
            if sol.is_file():
                written_solutions.append(sol.read_text(encoding="utf-8"))
            return True

        run_qwen_mbpp(
            n=1,
            _problems_override=[_PROB_ADD],
            _qwen_code_fn=fake_qwen,
            _run_fn=fake_run,
        )

        assert written_solutions, "solution.py was never written"
        src = written_solutions[0]
        # Must define the real function, not a generic stub
        assert "def add_two_numbers" in src, f"Expected 'def add_two_numbers' in:\n{src}"

    def test_solution_py_is_parseable_python(self, tmp_path: Path) -> None:
        """The assembled solution.py is valid Python (ast.parse succeeds)."""
        sources: list[str] = []

        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            # Simulate qwen returning a function that uses math
            return f"def {fn_name}(n):\n    return math.sqrt(n)\n"

        def fake_run(cmd: str, cwd: str, timeout: int) -> bool:
            sol = Path(cwd) / "solution.py"
            if sol.is_file():
                sources.append(sol.read_text(encoding="utf-8"))
            return True

        run_qwen_mbpp(
            n=1,
            _problems_override=[_PROB_SQRT],
            _qwen_code_fn=fake_qwen,
            _run_fn=fake_run,
        )

        assert sources, "solution.py was never written"
        src = sources[0]
        ast.parse(src)  # raises SyntaxError on broken indentation / invalid syntax

    def test_solution_py_has_import_for_math_usage(self, tmp_path: Path) -> None:
        """When qwen code uses math.sqrt, solution.py gets 'import math' prepended."""
        sources: list[str] = []

        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            return f"def {fn_name}(n):\n    return math.sqrt(n)\n"

        def fake_run(cmd: str, cwd: str, timeout: int) -> bool:
            sol = Path(cwd) / "solution.py"
            if sol.is_file():
                sources.append(sol.read_text(encoding="utf-8"))
            return True

        run_qwen_mbpp(
            n=1,
            _problems_override=[_PROB_SQRT],
            _qwen_code_fn=fake_qwen,
            _run_fn=fake_run,
        )

        assert sources
        src = sources[0]
        assert "import math" in src, f"Expected 'import math' in:\n{src}"
        # import must appear BEFORE the def
        assert src.index("import math") < src.index("def int_sqrt"), (
            "import math should appear before the function def"
        )


# ---------------------------------------------------------------------------
# Tests: scoring (passing vs failing)
# ---------------------------------------------------------------------------

class TestScoring:
    """run_qwen_mbpp scores correctly for passing and failing implementations.

    These tests use the REAL _run_with_treekill (no injection) to execute pytest
    in a subprocess.  They are still OFFLINE (no Jetson) — only pytest runs locally.
    """

    def test_correct_implementation_scores_pass(self) -> None:
        """A correct add_two_numbers implementation → passed=1, total=1."""
        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            # Return the correct implementation for the fn_name given
            if fn_name == "add_two_numbers":
                return "def add_two_numbers(a, b):\n    return a + b\n"
            return f"def {fn_name}(*args):\n    raise NotImplementedError\n"

        result = run_qwen_mbpp(
            n=1,
            _problems_override=[_PROB_ADD],
            _qwen_code_fn=fake_qwen,
            # _run_fn not injected → uses real _run_with_treekill + pytest
        )

        assert result["total"] == 1
        assert result["passed"] == 1
        assert result["score_pct"] == 100.0

    def test_wrong_implementation_scores_fail(self) -> None:
        """A wrong subtract_numbers (returns sum instead of diff) → passed=0, total=1."""
        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            if fn_name == "subtract_numbers":
                # Deliberately wrong: adds instead of subtracts
                return "def subtract_numbers(a, b):\n    return a + b\n"
            return f"def {fn_name}(*args):\n    raise NotImplementedError\n"

        result = run_qwen_mbpp(
            n=1,
            _problems_override=[_PROB_SUBTRACT],
            _qwen_code_fn=fake_qwen,
            # _run_fn not injected → uses real _run_with_treekill + pytest
        )

        assert result["total"] == 1
        assert result["passed"] == 0
        assert result["score_pct"] == 0.0

    def test_mixed_results_score_correctly(self) -> None:
        """One pass + one fail → passed=1, total=2, score_pct=50.0."""
        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            if fn_name == "add_two_numbers":
                return "def add_two_numbers(a, b):\n    return a + b\n"  # correct
            if fn_name == "subtract_numbers":
                return "def subtract_numbers(a, b):\n    return a + b\n"  # wrong
            return f"def {fn_name}(*args):\n    raise NotImplementedError\n"

        result = run_qwen_mbpp(
            n=2,
            _problems_override=[_PROB_ADD, _PROB_SUBTRACT],
            _qwen_code_fn=fake_qwen,
        )

        assert result["total"] == 2
        assert result["passed"] == 1
        assert result["score_pct"] == 50.0


# ---------------------------------------------------------------------------
# Tests: return value contract
# ---------------------------------------------------------------------------

class TestReturnContract:
    """run_qwen_mbpp always returns a dict with passed, total, score_pct."""

    def test_returns_required_keys(self) -> None:
        def fake_qwen(spec: str, fn_name: str, context: str = "") -> str:
            return f"def {fn_name}():\n    pass\n"

        def fake_run(cmd: str, cwd: str, timeout: int) -> bool:
            return True

        result = run_qwen_mbpp(
            n=1,
            _problems_override=[_PROB_SQUARE],
            _qwen_code_fn=fake_qwen,
            _run_fn=fake_run,
        )

        assert "passed" in result
        assert "total" in result
        assert "score_pct" in result
        assert isinstance(result["passed"], int)
        assert isinstance(result["total"], int)
        assert isinstance(result["score_pct"], float)

    def test_empty_problems_returns_zeros(self) -> None:
        """No problems → passed=0, total=0, score_pct=0.0 (no division by zero)."""
        result = run_qwen_mbpp(
            n=0,
            _problems_override=[],
            _qwen_code_fn=lambda s, n, c="": f"def {n}():\n    pass\n",
            _run_fn=lambda cmd, cwd, timeout: True,
        )

        assert result == {"passed": 0, "total": 0, "score_pct": 0.0}
