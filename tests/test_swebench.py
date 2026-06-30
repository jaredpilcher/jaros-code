"""Offline tests for harness/swebench.py (EXT-034).

ALL tests are OFFLINE:
  - fixture JSONL in tmp_path (no dataset download)
  - mock apply_fn / test_fn (no Docker)
  - no live Jetson / LLM calls

Tests cover:
  (a) load_instances: parses fixture, skips malformed line, honours n limit
  (b) build_solve_input: includes problem_statement + repo, EXCLUDES gold patch (honesty assertion)
  (c) score_resolved: resolved=True/False logic for FAIL_TO_PASS and PASS_TO_PASS
  (d) test_fn sole-arbiter: mock patch "claims" success but test_fn returns fail -> not resolved
  (e) swebench_eval: aggregates resolved-rate over a 2-instance fixture
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# #EXT-034-REQ-1 Start
# #EXT-034-REQ-2 Start
from harness.swebench import (
    build_solve_input,
    load_instances,
    score_resolved,
    swebench_eval,
)
# #EXT-034-REQ-2 End
# #EXT-034-REQ-1 End

# ---------------------------------------------------------------------------
# Fixture data — two realistic SWE-bench-Lite instance dicts
# ---------------------------------------------------------------------------

_INSTANCE_A: dict = {
    "instance_id": "django__django-12345",
    "repo": "django/django",
    "base_commit": "abc001deadbeef",
    "problem_statement": "Fix a bug in the ORM where filter() with nullable FK fails.",
    "FAIL_TO_PASS": ["tests/test_orm.py::TestFilterNullableFK::test_filter_nullable_fk"],
    "PASS_TO_PASS": ["tests/test_orm.py::TestFilterBasic::test_filter_basic"],
    "test_patch": (
        "diff --git a/tests/test_orm.py b/tests/test_orm.py\n"
        "--- a/tests/test_orm.py\n+++ b/tests/test_orm.py\n"
        "@@ -1,0 +1,5 @@\n+class TestFilterNullableFK:\n+    def test_filter_nullable_fk(self):\n+        pass\n"
    ),
    "patch": (
        "diff --git a/django/db/models/sql/query.py b/django/db/models/sql/query.py\n"
        "--- a/django/db/models/sql/query.py\n+++ b/django/db/models/sql/query.py\n"
        "@@ -1 +1,2 @@\n # existing line\n+# gold fix for nullable FK\n"
    ),
}

_INSTANCE_B: dict = {
    "instance_id": "sympy__sympy-67890",
    "repo": "sympy/sympy",
    "base_commit": "def002cafebabe",
    "problem_statement": "Symbolic integration fails for piecewise functions.",
    "FAIL_TO_PASS": ["sympy/integrals/tests/test_integrals.py::test_piecewise_integrate"],
    "PASS_TO_PASS": ["sympy/integrals/tests/test_integrals.py::test_basic_integrate"],
    "test_patch": "diff --git a/sympy/integrals/tests/test_integrals.py ...",
    "patch": "diff --git a/sympy/integrals/integrals.py ...",
}


def _write_fixture_jsonl(
    path: Path,
    instances: list[dict],
    *,
    include_malformed: bool = False,
) -> None:
    """Write instances to a JSONL fixture file. Optionally inject a malformed line."""
    lines = [json.dumps(inst) for inst in instances]
    if include_malformed:
        # Insert a malformed line between the first and second valid instances
        lines.insert(1, "{this is: not valid JSON }")
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_apply_fn():
    """Return a no-op apply_fn that records (base_commit, candidate_patch, test_patch) calls."""
    calls: list[tuple] = []

    def apply_fn(*, base_commit: str, candidate_patch: str, test_patch: str) -> None:
        calls.append((base_commit, candidate_patch, test_patch))

    apply_fn.calls = calls  # type: ignore[attr-defined]
    return apply_fn


# ---------------------------------------------------------------------------
# (a) load_instances
# ---------------------------------------------------------------------------

# #EXT-034-REQ-1 Start
def test_load_instances_basic(tmp_path: Path) -> None:
    """load_instances returns all valid instances from a 2-instance fixture JSONL."""
    p = tmp_path / "swebench_lite.jsonl"
    _write_fixture_jsonl(p, [_INSTANCE_A, _INSTANCE_B])
    instances = load_instances(p)
    assert len(instances) == 2
    assert instances[0]["instance_id"] == "django__django-12345"
    assert instances[1]["instance_id"] == "sympy__sympy-67890"


def test_load_instances_skips_malformed(tmp_path: Path) -> None:
    """load_instances skips malformed lines and returns only the valid ones."""
    p = tmp_path / "swebench_lite.jsonl"
    # 3 lines in total: valid, malformed, valid -> 2 valid returned
    _write_fixture_jsonl(p, [_INSTANCE_A, _INSTANCE_B], include_malformed=True)
    instances = load_instances(p)
    assert len(instances) == 2
    assert instances[0]["instance_id"] == "django__django-12345"
    assert instances[1]["instance_id"] == "sympy__sympy-67890"


def test_load_instances_limit(tmp_path: Path) -> None:
    """load_instances respects the n=1 limit."""
    p = tmp_path / "swebench_lite.jsonl"
    _write_fixture_jsonl(p, [_INSTANCE_A, _INSTANCE_B])
    instances = load_instances(p, n=1)
    assert len(instances) == 1
    assert instances[0]["instance_id"] == "django__django-12345"


def test_load_instances_required_fields(tmp_path: Path) -> None:
    """Loaded instances contain all 8 required SWE-bench-Lite fields."""
    p = tmp_path / "swebench_lite.jsonl"
    _write_fixture_jsonl(p, [_INSTANCE_A])
    inst = load_instances(p)[0]
    for field in (
        "instance_id", "repo", "base_commit", "problem_statement",
        "FAIL_TO_PASS", "PASS_TO_PASS", "test_patch", "patch",
    ):
        assert field in inst, f"Missing required field: {field}"


# ---------------------------------------------------------------------------
# (b) build_solve_input — honesty assertions
# ---------------------------------------------------------------------------

def test_build_solve_input_includes_problem_statement() -> None:
    """build_solve_input includes the problem_statement from the instance."""
    si = build_solve_input(_INSTANCE_A)
    assert si["problem_statement"] == _INSTANCE_A["problem_statement"]


def test_build_solve_input_includes_repo() -> None:
    """build_solve_input includes the repo identifier from the instance."""
    si = build_solve_input(_INSTANCE_A)
    assert si["repo"] == _INSTANCE_A["repo"]


def test_build_solve_input_excludes_gold_patch() -> None:
    """HONESTY: build_solve_input NEVER includes the gold patch content (Tenet 3)."""
    si = build_solve_input(_INSTANCE_A)
    gold_patch = _INSTANCE_A["patch"]
    si_str = json.dumps(si)
    assert gold_patch not in si_str, (
        "Gold patch must NOT appear anywhere in the solve input — Tenet 3 violation"
    )


def test_build_solve_input_excludes_patch_key() -> None:
    """HONESTY: the 'patch' key must not exist in the solve input dict."""
    si = build_solve_input(_INSTANCE_A)
    assert "patch" not in si, "'patch' key must not be in solve input (oracle-only)"


def test_build_solve_input_excludes_test_patch() -> None:
    """HONESTY: build_solve_input does not include the hidden test_patch."""
    si = build_solve_input(_INSTANCE_A)
    assert "test_patch" not in si, "'test_patch' (hidden) must not be in solve input"


def test_build_solve_input_repo_context_injected() -> None:
    """build_solve_input injects the caller-provided repo_context into 'context'."""
    ctx = "# relevant repo context\n"
    si = build_solve_input(_INSTANCE_A, repo_context=ctx)
    assert "# relevant repo context" in si["context"]
# #EXT-034-REQ-1 End


# ---------------------------------------------------------------------------
# (c) score_resolved — resolve logic
# ---------------------------------------------------------------------------

# #EXT-034-REQ-2 Start
def test_score_resolved_true_when_all_pass() -> None:
    """resolved=True when ALL FAIL_TO_PASS pass AND ALL PASS_TO_PASS pass."""
    all_pass = {
        "tests/test_orm.py::TestFilterNullableFK::test_filter_nullable_fk",
        "tests/test_orm.py::TestFilterBasic::test_filter_basic",
    }
    result = score_resolved(
        _INSTANCE_A,
        "--- candidate patch ---",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: {t for t in tests if t in all_pass},
    )
    assert result["resolved"] is True
    assert "tests/test_orm.py::TestFilterNullableFK::test_filter_nullable_fk" in result["fail_to_pass_passed"]
    assert "tests/test_orm.py::TestFilterBasic::test_filter_basic" in result["pass_to_pass_passed"]


def test_score_resolved_false_when_ftp_fails() -> None:
    """resolved=False when any FAIL_TO_PASS test still fails."""
    # Only PASS_TO_PASS tests pass; FAIL_TO_PASS does not
    only_ptp = {"tests/test_orm.py::TestFilterBasic::test_filter_basic"}
    result = score_resolved(
        _INSTANCE_A,
        "--- broken patch ---",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: {t for t in tests if t in only_ptp},
    )
    assert result["resolved"] is False
    assert result["fail_to_pass_passed"] == []


def test_score_resolved_false_when_ptp_breaks() -> None:
    """resolved=False when any PASS_TO_PASS test regresses."""
    # FAIL_TO_PASS passes but PASS_TO_PASS breaks
    only_ftp = {"tests/test_orm.py::TestFilterNullableFK::test_filter_nullable_fk"}
    result = score_resolved(
        _INSTANCE_A,
        "--- regressing patch ---",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: {t for t in tests if t in only_ftp},
    )
    assert result["resolved"] is False
    assert result["pass_to_pass_passed"] == []


def test_score_resolved_both_required() -> None:
    """resolved=True only when BOTH FAIL_TO_PASS and PASS_TO_PASS fully pass."""
    all_pass = {
        "tests/test_orm.py::TestFilterNullableFK::test_filter_nullable_fk",
        "tests/test_orm.py::TestFilterBasic::test_filter_basic",
    }
    result = score_resolved(
        _INSTANCE_A,
        "--- complete patch ---",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: {t for t in tests if t in all_pass},
    )
    assert result["resolved"] is True


def test_score_resolved_returns_reason() -> None:
    """score_resolved always includes a 'reason' string."""
    result = score_resolved(
        _INSTANCE_A,
        "any patch",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: set(),
    )
    assert "reason" in result
    assert isinstance(result["reason"], str)
    assert len(result["reason"]) > 0


def test_score_resolved_apply_fn_exception_returns_false() -> None:
    """score_resolved returns resolved=False if apply_fn raises."""
    def bad_apply_fn(*, base_commit, candidate_patch, test_patch):
        raise RuntimeError("Docker not available")

    result = score_resolved(
        _INSTANCE_A,
        "any patch",
        apply_fn=bad_apply_fn,
        test_fn=lambda tests: set(tests),  # would return all pass, but never reached
    )
    assert result["resolved"] is False
    assert "apply_fn raised" in result["reason"]


# ---------------------------------------------------------------------------
# (d) test_fn is sole arbiter
# ---------------------------------------------------------------------------

def test_score_resolved_test_fn_is_sole_arbiter() -> None:
    """test_fn is sole arbiter: even if solve 'claims' success, if test_fn says
    a FAIL_TO_PASS still fails, resolved must be False."""
    # apply_fn succeeds (no exception), but test_fn returns empty set
    result = score_resolved(
        _INSTANCE_A,
        candidate_patch="--- model believes this fixes everything ---",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: set(),  # all tests fail per test_fn
    )
    assert result["resolved"] is False
    assert result["fail_to_pass_passed"] == []
    assert result["pass_to_pass_passed"] == []


def test_score_resolved_apply_fn_is_called_with_correct_args() -> None:
    """apply_fn is called with the correct (base_commit, candidate_patch, test_patch)."""
    apply_fn = _make_apply_fn()
    score_resolved(
        _INSTANCE_A,
        "--- my candidate patch ---",
        apply_fn=apply_fn,
        test_fn=lambda tests: set(tests),
    )
    assert len(apply_fn.calls) == 1
    base_commit, candidate_patch, test_patch = apply_fn.calls[0]
    assert base_commit == _INSTANCE_A["base_commit"]
    assert candidate_patch == "--- my candidate patch ---"
    assert test_patch == _INSTANCE_A["test_patch"]


# ---------------------------------------------------------------------------
# (e) swebench_eval — resolved-rate aggregation
# ---------------------------------------------------------------------------

def test_swebench_eval_aggregates_resolved_rate() -> None:
    """swebench_eval correctly aggregates resolved-rate over a 2-instance fixture.
    Instance A resolves; Instance B does not -> rate = 0.5."""
    instances = [_INSTANCE_A, _INSTANCE_B]

    # Test functions keyed to each instance's FAIL_TO_PASS/PASS_TO_PASS
    _a_pass = set(_INSTANCE_A["FAIL_TO_PASS"] + _INSTANCE_A["PASS_TO_PASS"])
    call_count = [0]

    def test_fn(tests: list[str]) -> set:
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            # Instance A: all tests pass
            return {t for t in tests if t in _a_pass}
        else:
            # Instance B: all tests fail (not resolved)
            return set()

    result = swebench_eval(
        instances,
        solve_fn=lambda si: "--- stub patch ---",
        apply_fn=_make_apply_fn(),
        test_fn=test_fn,
    )

    assert result["n"] == 2
    assert result["resolved"] == 1
    assert abs(result["resolved_rate"] - 0.5) < 1e-9
    lo, hi = result["wilson95"]
    assert 0.0 <= lo <= hi <= 1.0
    assert "per_instance" in result
    assert len(result["per_instance"]) == 2


def test_swebench_eval_all_resolved() -> None:
    """swebench_eval reports resolved_rate=1.0 when all instances resolve."""
    all_pass = set(_INSTANCE_A["FAIL_TO_PASS"] + _INSTANCE_A["PASS_TO_PASS"])
    result = swebench_eval(
        [_INSTANCE_A],
        solve_fn=lambda si: "--- perfect patch ---",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: {t for t in tests if t in all_pass},
    )
    assert result["resolved"] == 1
    assert result["resolved_rate"] == 1.0


def test_swebench_eval_none_resolved() -> None:
    """swebench_eval reports resolved_rate=0.0 when no instances resolve."""
    result = swebench_eval(
        [_INSTANCE_A, _INSTANCE_B],
        solve_fn=lambda si: "--- useless patch ---",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: set(),  # all tests fail
    )
    assert result["resolved"] == 0
    assert result["resolved_rate"] == 0.0


def test_swebench_eval_result_keys() -> None:
    """swebench_eval result dict contains all required keys."""
    result = swebench_eval(
        [_INSTANCE_A],
        solve_fn=lambda si: "patch",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: set(),
    )
    for key in ("n", "resolved", "resolved_rate", "wilson95", "per_instance"):
        assert key in result, f"Missing required key in swebench_eval result: {key}"


def test_swebench_eval_per_instance_has_instance_id() -> None:
    """Each per_instance entry has an instance_id for traceability."""
    result = swebench_eval(
        [_INSTANCE_A, _INSTANCE_B],
        solve_fn=lambda si: "patch",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: set(),
    )
    ids = [r["instance_id"] for r in result["per_instance"]]
    assert "django__django-12345" in ids
    assert "sympy__sympy-67890" in ids


def test_swebench_eval_wilson95_is_valid_interval() -> None:
    """Wilson95 CI is a valid (lo, hi) interval with 0 <= lo <= hi <= 1."""
    result = swebench_eval(
        [_INSTANCE_A, _INSTANCE_B],
        solve_fn=lambda si: "patch",
        apply_fn=_make_apply_fn(),
        test_fn=lambda tests: set(),
    )
    lo, hi = result["wilson95"]
    assert 0.0 <= lo
    assert lo <= hi
    assert hi <= 1.0
# #EXT-034-REQ-2 End


def test_load_instances_normalizes_json_string_test_fields(tmp_path):
    """Regression (real-data validation 2026-06-29): real SWE-bench-Lite encodes
    FAIL_TO_PASS / PASS_TO_PASS as JSON STRINGS, not lists; load_instances must
    normalize them to list[str] so score_resolved iterates test names, not chars."""
    from harness.swebench import load_instances as _load
    inst = {
        "instance_id": "x__y-1", "repo": "x/y", "base_commit": "abc",
        "problem_statement": "fix it",
        "FAIL_TO_PASS": '["pkg/test.py::test_a", "pkg/test.py::test_b"]',
        "PASS_TO_PASS": '["pkg/test.py::test_c"]',
        "test_patch": "", "patch": "GOLD",
    }
    f = tmp_path / "real.jsonl"
    f.write_text(json.dumps(inst) + "\n", encoding="utf-8")
    got = _load(str(f))
    assert len(got) == 1
    assert got[0]["FAIL_TO_PASS"] == ["pkg/test.py::test_a", "pkg/test.py::test_b"]
    assert got[0]["PASS_TO_PASS"] == ["pkg/test.py::test_c"]
