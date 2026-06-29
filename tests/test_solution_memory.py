"""Tests for harness/solution_memory.py -- EXT-027 REQ-1.

All tests are OFFLINE (no Jetson, no LLM, no real .jaros-data directory).
tmp_path fixtures are used throughout so nothing touches production artifacts.

Acceptance criteria covered:
- record_verified appends a parseable JSONL entry with all required fields.
- recall_similar returns the stored code for a same-class / similar-signature
  problem; returns None for a dissimilar class; returns None when the only
  same-class match is the SAME task (honesty invariant).
- inject_verified_example produces a worked-example block containing the
  recalled code, prepended before the original context; returns the original
  unchanged when recalled is None or has no usable code.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.solution_memory import (
    inject_verified_example,
    recall_similar,
    record_verified,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _standalone_problem(source: str = "def add(x, y):\n    return x + y") -> dict:
    """A typical standalone-fn-gen problem (has_examples -> standalone class)."""
    return {"source": source, "language": "python", "has_examples": True}


def _repo_problem(source: str = "def fix_repo(): pass") -> dict:
    """A typical multi-step-repo problem."""
    return {"source": source, "is_repo_task": True, "language": "python"}


# ---------------------------------------------------------------------------
# record_verified
# ---------------------------------------------------------------------------


class TestRecordVerified:
    """record_verified appends a parseable JSONL entry with the required schema."""

    def test_appends_parseable_entry(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        record_verified(_standalone_problem(), "def add(x, y): return x + y", path=p)
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        for field in ("ts", "signature", "problem_class", "code", "task_sample"):
            assert field in rec, f"expected field {field!r} missing from record"

    def test_stored_code_is_exact(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        code = "def add(x, y):\n    return x + y\n"
        record_verified(_standalone_problem(), code, path=p)
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        assert rec["code"] == code

    def test_multiple_calls_append_multiple_lines(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        for i in range(3):
            record_verified(
                _standalone_problem(f"def fn{i}(): pass"),
                f"def fn{i}(): return {i}",
                path=p,
            )
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    def test_task_sample_truncated_to_200(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        long_source = "x" * 500
        record_verified(
            {"source": long_source, "language": "python"},
            "def f(): pass",
            path=p,
        )
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        assert len(rec["task_sample"]) <= 200

    def test_problem_class_inferred_standalone(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        record_verified(
            {"source": ">>> add(1, 2)\n3", "has_examples": True},
            "def add(a, b): return a+b",
            path=p,
        )
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        assert rec["problem_class"] == "standalone-fn-gen"

    def test_problem_class_inferred_repo(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        record_verified(
            {"source": "fix something", "is_repo_task": True},
            "def fix(): pass",
            path=p,
        )
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        assert rec["problem_class"] == "multi-step-repo"

    def test_explicit_problem_class_wins(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        record_verified(
            {
                "source": "fix something",
                "is_repo_task": True,
                "problem_class": "custom-class",
            },
            "def fix(): pass",
            path=p,
        )
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        assert rec["problem_class"] == "custom-class"

    def test_ts_is_iso_format(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        record_verified(_standalone_problem(), "def f(): pass", path=p)
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        ts = rec["ts"]
        assert "T" in ts
        assert ts.endswith("Z")

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "sol.jsonl"
        record_verified(_standalone_problem(), "def f(): pass", path=p)
        assert p.exists()

    def test_never_raises_on_none_problem(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        # Must not raise; best-effort write (may or may not produce a record)
        record_verified(None, "def f(): pass", path=p)

    def test_never_raises_on_int_problem(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        record_verified(42, "def g(): pass", path=p)

    def test_signature_has_all_expected_keys(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        record_verified(_standalone_problem(), "def f(): pass", path=p)
        rec = json.loads(p.read_text(encoding="utf-8").strip())
        sig = rec["signature"]
        for key in (
            "language",
            "is_repo_task",
            "is_multi_file",
            "has_examples",
            "fn_len_bucket",
            "source_len_bucket",
            "error_signal",
        ):
            assert key in sig, f"signature missing key: {key!r}"


# ---------------------------------------------------------------------------
# recall_similar
# ---------------------------------------------------------------------------


class TestRecallSimilar:
    """recall_similar returns the best same-class match or None."""

    def test_returns_none_when_store_absent(self, tmp_path):
        result = recall_similar(_standalone_problem(), path=tmp_path / "no.jsonl")
        assert result is None

    def test_returns_stored_code_for_same_class_similar_problem(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        code = "def add(x, y): return x + y\n"
        # Store a verified solution for problem A
        record_verified(
            {"source": "def A(x): return x", "has_examples": True, "language": "python"},
            code,
            path=p,
        )
        # Recall for a similar but DIFFERENT problem B (different source)
        result = recall_similar(
            {"source": "def B(y): return y", "has_examples": True, "language": "python"},
            path=p,
        )
        assert result is not None
        assert result["code"] == code

    def test_returns_none_for_dissimilar_class(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        # Store a repo-task solution
        record_verified(
            {"source": "fix repo", "is_repo_task": True},
            "def fix(): pass",
            path=p,
        )
        # Recall for a standalone problem -- different class, must be None
        result = recall_similar(
            {"source": ">>> add(1, 2)\n3", "has_examples": True},
            path=p,
        )
        assert result is None

    def test_returns_none_when_only_match_is_same_task(self, tmp_path):
        """Honesty invariant: never recall the target's own verified answer."""
        p = tmp_path / "sol.jsonl"
        source = "def add(x, y): return x + y"
        problem = {"source": source, "has_examples": True}
        record_verified(problem, "def add(x, y): return x + y\n", path=p)
        # Recall for the IDENTICAL problem -- must return None
        result = recall_similar(problem, path=p)
        assert result is None

    def test_excludes_same_task_but_returns_other(self, tmp_path):
        """When two same-class records exist, self-match excluded, other returned."""
        p = tmp_path / "sol.jsonl"
        target_src = "def target(x): pass"
        other_src = "def other(y): pass"
        record_verified(
            {"source": target_src, "has_examples": True, "language": "python"},
            "def target(x): return x\n",
            path=p,
        )
        record_verified(
            {"source": other_src, "has_examples": True, "language": "python"},
            "def other(y): return y\n",
            path=p,
        )
        # Recall for the target task -- should get OTHER's solution, not its own
        result = recall_similar(
            {"source": target_src, "has_examples": True, "language": "python"},
            path=p,
        )
        assert result is not None
        assert result["code"] == "def other(y): return y\n"

    def test_result_has_required_keys(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        record_verified(
            {"source": "def A(x): x", "has_examples": True},
            "def A(x): return x\n",
            path=p,
        )
        result = recall_similar(
            {"source": "def B(y): y", "has_examples": True},
            path=p,
        )
        assert result is not None
        assert "code" in result
        assert "signature" in result
        assert "problem_class" in result

    def test_same_class_cross_language_excluded_by_lower_score(self, tmp_path):
        """Same class but different language has lower similarity score;
        same class + same language wins when both exist."""
        p = tmp_path / "sol.jsonl"
        # Store two same-class records: one Python, one 'rust'
        record_verified(
            {"source": "def py_fn(): pass", "has_examples": True, "language": "python"},
            "def py_fn(): return 1\n",
            path=p,
        )
        record_verified(
            {"source": "fn rust_fn() {}", "has_examples": True, "language": "rust"},
            "fn rust_fn() { 1 }\n",
            path=p,
        )
        # Recall for a Python standalone problem -- should prefer the Python record
        result = recall_similar(
            {"source": "def query(): pass", "has_examples": True, "language": "python"},
            path=p,
        )
        assert result is not None
        assert result["code"] == "def py_fn(): return 1\n"

    def test_never_raises_on_corrupt_store(self, tmp_path):
        p = tmp_path / "sol.jsonl"
        p.write_text("NOT-JSON\n", encoding="utf-8")
        # Must not raise; result is None or a dict
        result = recall_similar(_standalone_problem(), path=p)
        assert result is None or isinstance(result, dict)

    def test_repo_class_recalled_for_repo_problem(self, tmp_path):
        """Repo-task solutions are recalled for repo-task queries."""
        p = tmp_path / "sol.jsonl"
        record_verified(
            {"source": "fix_alpha", "is_repo_task": True, "language": "python"},
            "def fix_alpha(): return True\n",
            path=p,
        )
        result = recall_similar(
            {"source": "fix_beta", "is_repo_task": True, "language": "python"},
            path=p,
        )
        assert result is not None
        assert result["code"] == "def fix_alpha(): return True\n"


# ---------------------------------------------------------------------------
# inject_verified_example
# ---------------------------------------------------------------------------


class TestInjectVerifiedExample:
    """inject_verified_example produces the right augmented prompt."""

    def test_returns_original_when_recalled_is_none(self):
        spec = "Implement foo(x) that returns x + 1."
        result = inject_verified_example(spec, None)
        assert result == spec

    def test_returns_original_when_recalled_is_empty_dict(self):
        spec = "Implement foo(x)."
        result = inject_verified_example(spec, {})
        assert result == spec

    def test_returns_original_when_code_is_empty(self):
        recalled = {"code": "", "signature": {}, "problem_class": "standalone-fn-gen"}
        spec = "Implement foo(x)."
        result = inject_verified_example(spec, recalled)
        assert result == spec

    def test_returns_original_when_code_is_whitespace(self):
        recalled = {"code": "   \n", "signature": {}, "problem_class": "standalone-fn-gen"}
        spec = "Implement foo(x)."
        result = inject_verified_example(spec, recalled)
        assert result == spec

    def test_block_contains_recalled_code(self):
        recalled = {
            "code": "def add(x, y): return x + y\n",
            "signature": {"language": "python"},
            "problem_class": "standalone-fn-gen",
        }
        spec = "Implement bar(a, b)."
        result = inject_verified_example(spec, recalled)
        assert "def add(x, y): return x + y" in result

    def test_block_contains_verified_solution_header(self):
        recalled = {
            "code": "def f(): return 1\n",
            "signature": {},
            "problem_class": "standalone-fn-gen",
        }
        result = inject_verified_example("spec", recalled)
        assert "VERIFIED SOLUTION MEMORY" in result

    def test_block_prepended_before_spec(self):
        recalled = {
            "code": "def f(): return 1\n",
            "signature": {},
            "problem_class": "standalone-fn-gen",
        }
        spec = "UNIQUE_SPEC_MARKER_XYZ"
        result = inject_verified_example(spec, recalled)
        idx_block = result.index("VERIFIED SOLUTION MEMORY")
        idx_spec = result.index("UNIQUE_SPEC_MARKER_XYZ")
        assert idx_block < idx_spec, "worked-example block must come before the spec"

    def test_original_spec_preserved_verbatim(self):
        recalled = {
            "code": "def f(): return 1\n",
            "signature": {},
            "problem_class": "standalone-fn-gen",
        }
        spec = "UNIQUE_SPEC_TEXT_12345"
        result = inject_verified_example(spec, recalled)
        assert spec in result

    def test_problem_class_included_in_block(self):
        recalled = {
            "code": "def fix(): pass\n",
            "signature": {},
            "problem_class": "multi-step-repo",
        }
        result = inject_verified_example("spec", recalled)
        assert "multi-step-repo" in result

    def test_honesty_label_present(self):
        """Block must state clearly that this is NOT this task's answer."""
        recalled = {
            "code": "def g(): return 2\n",
            "signature": {},
            "problem_class": "standalone-fn-gen",
        }
        result = inject_verified_example("spec", recalled)
        assert "NOT this task" in result


# ---------------------------------------------------------------------------
# AST parse smoke-test (offline, no LLM)
# ---------------------------------------------------------------------------


def test_solution_memory_module_parses():
    """The harness/solution_memory.py module is syntactically valid Python."""
    src = (Path(__file__).parent.parent / "harness" / "solution_memory.py").read_text(
        encoding="utf-8"
    )
    ast.parse(src)  # raises SyntaxError if broken
