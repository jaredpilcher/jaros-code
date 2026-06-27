"""Deterministic unit tests for EXT-012 / REQ-12 — generate-and-test selector.

All tests use fake/stub data.  No real LLM, no Jetson, no Docker.

Coverage:
  (a) validate() rejects an empty candidates list.
  (b) validate() rejects a non-list candidates payload.
  (c) execute() picks the first all-pass candidate.
  (d) execute() picks the highest-pass-count candidate when no all-pass exists;
      lowest index wins on tie.
  (e) generate_and_test_solve wires generate->selftest->select and returns the
      best candidate without any real model or Docker call.
  (f) ast.parse smoke — both new source files must parse as valid Python.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _REPO_ROOT / ".jaros-data" / "tools"
_AGENTS_DIR = _REPO_ROOT / ".jaros-data" / "agents"

for _d in (str(_REPO_ROOT), str(_TOOLS_DIR), str(_AGENTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

# #EXT-012-REQ-12 Start


# ---------------------------------------------------------------------------
# Helpers: load tool and harness module without importing everything
# ---------------------------------------------------------------------------

def _load_tool():
    """Load GenerateAndTestTool from its file."""
    tool_path = str(_TOOLS_DIR / "generate_and_test_tool.py")
    spec = importlib.util.spec_from_file_location("_gat_tool", tool_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.GenerateAndTestTool()


def _load_generate_test_solve():
    """Load generate_and_test_solve from harness/generate_test_solve.py."""
    solve_path = str(_REPO_ROOT / "harness" / "generate_test_solve.py")
    spec = importlib.util.spec_from_file_location("_gts_mod", solve_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.generate_and_test_solve


def _make_decision(candidates, results, total_tests=None):
    """Build a minimal Decision-like object for tool testing."""
    from jaros.core import create_decision

    payload: dict = {"candidates": candidates, "results": results}
    if total_tests is not None:
        payload["total_tests"] = total_tests
    return create_decision(
        id="test-gat-001",
        source="test",
        type="code.generate_and_test",
        payload=payload,
    )


# ---------------------------------------------------------------------------
# (f) ast.parse smoke — new files must be syntactically valid
# ---------------------------------------------------------------------------

def test_tool_file_parses():
    src = (_TOOLS_DIR / "generate_and_test_tool.py").read_text(encoding="utf-8")
    ast.parse(src)  # raises SyntaxError if broken


def test_harness_file_parses():
    src = (_REPO_ROOT / "harness" / "generate_test_solve.py").read_text(encoding="utf-8")
    ast.parse(src)  # raises SyntaxError if broken


# ---------------------------------------------------------------------------
# (a) validate() rejects empty candidates list
# ---------------------------------------------------------------------------

def test_validate_rejects_empty_candidates():
    tool = _load_tool()
    dec = _make_decision([], [])
    result = tool.validate(dec)
    assert not result.ok, "empty candidates must be rejected"
    assert "non-empty" in result.reason.lower() or "candidates" in result.reason.lower()


# ---------------------------------------------------------------------------
# (b) validate() rejects non-list candidates
# ---------------------------------------------------------------------------

def test_validate_rejects_non_list_candidates():
    tool = _load_tool()
    dec = _make_decision("not a list", [])  # type: ignore[arg-type]
    result = tool.validate(dec)
    assert not result.ok, "non-list candidates must be rejected"


def test_validate_rejects_non_str_candidate():
    tool = _load_tool()
    dec = _make_decision([42], [1])  # candidate is int, not str
    result = tool.validate(dec)
    assert not result.ok, "non-str candidate must be rejected"


def test_validate_rejects_mismatched_results_length():
    tool = _load_tool()
    dec = _make_decision(["def f(): pass"], [1, 2])  # length mismatch
    result = tool.validate(dec)
    assert not result.ok, "mismatched results length must be rejected"


def test_validate_accepts_valid_payload():
    tool = _load_tool()
    dec = _make_decision(["def f(): pass", "def f(): return 1"], [0, 1])
    result = tool.validate(dec)
    assert result.ok, f"valid payload must be accepted; got: {result.reason}"


# ---------------------------------------------------------------------------
# (c) execute() picks the first all-pass candidate
# ---------------------------------------------------------------------------

def test_execute_picks_all_pass_candidate():
    """When multiple candidates all-pass, the FIRST one is chosen."""
    tool = _load_tool()
    candidates = [
        "def f(x): return x + 1",   # 0 passes — fails
        "def f(x): return x",       # 3 passes — all-pass (first)
        "def f(x): return x * 2",   # 3 passes — all-pass (second)
    ]
    results = [0, 3, 3]
    dec = _make_decision(candidates, results, total_tests=3)
    out = tool.execute(dec)
    assert out["index"] == 1, f"expected index=1 (first all-pass), got {out['index']}"
    assert out["chosen"] == candidates[1]
    assert out["pass_count"] == 3


def test_execute_picks_first_all_pass_not_highest_count():
    """Index 0 all-passes (count=2); index 1 has count=3 but different total_tests.
    When total_tests=2, index 0 is chosen first as it is the first all-pass."""
    tool = _load_tool()
    candidates = ["def f(): return 0", "def f(): return 1", "def f(): return 2"]
    results = [2, 3, 1]
    # total_tests=2 means index 0 (count=2) all-passes; index 1 (count=3) exceeds it
    dec = _make_decision(candidates, results, total_tests=2)
    out = tool.execute(dec)
    assert out["index"] == 0, f"first all-pass (index 0) must win; got {out['index']}"


# ---------------------------------------------------------------------------
# (d) No all-pass: picks highest-pass-count, lowest index on tie
# ---------------------------------------------------------------------------

def test_execute_no_allpass_picks_highest():
    """No candidate all-passes — pick the one with the most passing tests."""
    tool = _load_tool()
    candidates = ["def f(): pass", "def f(): return 1", "def f(): return 2"]
    results = [0, 2, 1]
    dec = _make_decision(candidates, results, total_tests=5)
    out = tool.execute(dec)
    assert out["index"] == 1, f"highest pass_count (index 1) must win; got {out['index']}"
    assert out["pass_count"] == 2


def test_execute_no_allpass_tie_broken_by_lowest_index():
    """Tie in pass_count — the LOWEST index must win (stable/deterministic)."""
    tool = _load_tool()
    candidates = ["def f(): return 0", "def f(): return 1", "def f(): return 2"]
    results = [2, 2, 1]
    dec = _make_decision(candidates, results, total_tests=5)
    out = tool.execute(dec)
    assert out["index"] == 0, (
        f"on tie, lowest index (0) must win; got {out['index']}"
    )
    assert out["pass_count"] == 2


def test_execute_all_zero_returns_index_zero():
    """When all candidates pass 0 tests, index 0 is returned (stable)."""
    tool = _load_tool()
    candidates = ["def f(): pass", "def f(): raise", "def f(): ..."]
    results = [0, 0, 0]
    dec = _make_decision(candidates, results, total_tests=3)
    out = tool.execute(dec)
    assert out["index"] == 0


# ---------------------------------------------------------------------------
# (e) generate_and_test_solve wires generate->selftest->select
# ---------------------------------------------------------------------------

class _FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLlm:
    """Stub LLM that returns a different canned completion per seed.

    NOTE: code_agent.py extracts the ``def`` block and strips trailing whitespace,
    so the actual candidate string will NOT have a trailing newline.  The _RESPONSES
    and pass_map keys below must match what code_agent actually produces.
    """

    # Each seed maps to a distinct implementation (no trailing newline — code_agent strips it)
    _RESPONSES = {
        0: "def solve(x):\n    return x + 999",   # wrong — 0 passing tests
        1: "def solve(x):\n    return x",          # correct — 3 passing tests
        2: "def solve(x):\n    return x - 1",      # wrong — 1 passing test
        3: "def solve(x):\n    return x + 1",      # wrong — 2 passing tests
    }

    def __init__(self) -> None:
        self.calls: list[int] = []

    def complete(self, request) -> _FakeCompletion:
        # Extract seed from request.params if present
        seed = getattr(request, "params", {}).get("seed", 0)
        self.calls.append(seed)
        return _FakeCompletion(self._RESPONSES.get(seed, "def solve(x): pass"))


class _StubRuntime:
    """Minimal Runtime stub that accepts Decisions without writing files."""
    def apply(self, decision):
        return {"applied": True}


def _make_selftests_stub(pass_map: dict):
    """Return a run_selftests callable that returns a scripted pass count.

    *pass_map* maps candidate source string -> int pass count.
    Any source not in the map gets 0.
    """
    def _run(code: str) -> int:
        return pass_map.get(code, 0)
    return _run


def test_generate_and_test_solve_picks_best_candidate():
    """generate_and_test_solve generates 4 candidates and picks the all-pass one."""
    solve = _load_generate_test_solve()
    llm = _FakeLlm()

    # Keys must match what code_agent produces (no trailing newline — it strips the def block)
    pass_map = {
        "def solve(x):\n    return x + 999": 0,
        "def solve(x):\n    return x": 3,         # all-pass (3/3)
        "def solve(x):\n    return x - 1": 1,
        "def solve(x):\n    return x + 1": 2,
    }
    run_selftests = _make_selftests_stub(pass_map)

    result = solve(
        intent="return identity",
        name="solve",
        current_src=None,
        context="",
        pkg="mymod",
        runtime=_StubRuntime(),
        run_selftests=run_selftests,
        n=4,
        base_seed=0,
        llm=llm,
        gherkin="Given solve(x) returns x",
    )

    # Should pick seed=1 candidate (3 passes, all-pass)
    assert result["chosen"] == "def solve(x):\n    return x", (
        f"wrong chosen candidate: {result['chosen']!r}"
    )
    assert result["index"] == 1
    assert result["pass_count"] == 3
    assert len(result["candidates"]) == 4
    assert len(result["results"]) == 4
    # All 4 seeds must have been used
    assert len(llm.calls) == 4


def test_generate_and_test_solve_no_allpass_picks_best():
    """When no candidate all-passes, the highest-pass-count is returned."""
    solve = _load_generate_test_solve()
    llm = _FakeLlm()

    # Override the stub so no candidate gets 3 (total_tests is 3 -- none all-pass)
    # Keys must match what code_agent produces (no trailing newline)
    pass_map = {
        "def solve(x):\n    return x + 999": 0,
        "def solve(x):\n    return x": 2,         # best but not all-pass
        "def solve(x):\n    return x - 1": 1,
        "def solve(x):\n    return x + 1": 2,     # tie -- higher index loses
    }
    run_selftests = _make_selftests_stub(pass_map)

    result = solve(
        intent="return identity",
        name="solve",
        current_src=None,
        context="",
        pkg="mymod",
        runtime=_StubRuntime(),
        run_selftests=run_selftests,
        n=4,
        base_seed=0,
        llm=llm,
        gherkin="Given solve(x) returns x",
    )

    # seed=1 has pass_count=2 and is the FIRST of the tied pair -> wins
    assert result["pass_count"] == 2
    assert result["index"] == 1  # lowest index with max count


# ---------------------------------------------------------------------------
# (g) commit_replay wiring: attempt_gherkin_jaros_gen + run_gherkin_jaros_gen
#     are importable and correctly call generate_and_test_solve with n=N.
#     Uses monkeypatching to avoid any real Docker or LLM call.
# ---------------------------------------------------------------------------

def test_commit_replay_gen_functions_importable():
    """attempt_gherkin_jaros_gen and run_gherkin_jaros_gen must be importable from commit_replay."""
    import importlib
    mod = importlib.import_module("harness.commit_replay")
    assert hasattr(mod, "attempt_gherkin_jaros_gen"), (
        "attempt_gherkin_jaros_gen must be exported from harness.commit_replay"
    )
    assert hasattr(mod, "run_gherkin_jaros_gen"), (
        "run_gherkin_jaros_gen must be exported from harness.commit_replay"
    )


def test_commit_replay_file_parses():
    """harness/commit_replay.py must be syntactically valid after the --gen wiring."""
    src = (_REPO_ROOT / "harness" / "commit_replay.py").read_text(encoding="utf-8")
    ast.parse(src)


def test_run_gherkin_jaros_gen_calls_gen_and_test(monkeypatch):
    """run_gherkin_jaros_gen must call attempt_gherkin_jaros_gen for each task.

    HONESTY: the stub never touches the hidden oracle — it just verifies the call chain.
    """
    import importlib
    mod = importlib.import_module("harness.commit_replay")

    calls: list[dict] = []

    def _fake_attempt(repo, task, branch, timeout=180, n_gen=4):
        calls.append({"task": task, "n_gen": n_gen})
        return "pass"

    monkeypatch.setattr(mod, "attempt_gherkin_jaros_gen", _fake_attempt)

    tasks = [
        {"sha": "aaaa1111", "parent": "pppp0000", "subject": "test task A",
         "redgreen": [], "code_files": [], "test_files": []},
        {"sha": "bbbb2222", "parent": "aaaa1111", "subject": "test task B",
         "redgreen": [], "code_files": [], "test_files": []},
    ]
    from pathlib import Path
    result = mod.run_gherkin_jaros_gen(Path("/fake/repo"), "main", tasks, n_gen=3)

    assert len(calls) == 2, f"expected 2 calls to attempt_gherkin_jaros_gen, got {len(calls)}"
    assert all(c["n_gen"] == 3 for c in calls), (
        f"n_gen must be forwarded to attempt_gherkin_jaros_gen; got {[c['n_gen'] for c in calls]}"
    )
    assert result.get("pass") == 2, f"expected 2 pass, got {result}"


# #EXT-012-REQ-12 End
