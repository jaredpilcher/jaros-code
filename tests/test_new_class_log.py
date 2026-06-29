"""Tests for harness/new_class_log.py -- EXT-021 REQ-7 DISCOVER.

All tests are OFFLINE (no Jetson, no LLM, no real .jaros-data directory).
``tmp_path`` fixtures are used throughout so nothing touches the production
``.jaros-data/artifacts/new_classes.jsonl`` at test time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import harness.new_class_log as ncl
from harness.new_class_log import record_unhandled, review_new_classes
from harness.model_registry import ModelProfile, ModelRegistry
from harness.model_router import route


# ---------------------------------------------------------------------------
# Helpers: stub registry (mirrors test_model_router.py pattern)
# ---------------------------------------------------------------------------

def _make_profile(model_id: str, class_names: list[str]) -> ModelProfile:
    classes = [
        {"name": n, "bar": "test-bar", "score": "99%", "date": "2026-01-01"}
        for n in class_names
    ]
    return ModelProfile(id=model_id, alias=model_id, classes=classes, adaptation={})


def _make_registry(profiles, default_id: str) -> ModelRegistry:
    return ModelRegistry(profiles=profiles, default_id=default_id)


_GEMMA_PROFILE = _make_profile("gemma-4-e2b", ["standalone-fn-gen", "single-file-repair"])
_STRONG_PROFILE = _make_profile("strong-model-7b", ["multi-step-repo"])


def _uncovered_reg() -> ModelRegistry:
    """Gemma-only; repo class not covered -> HARNESS-GAP."""
    return _make_registry([_GEMMA_PROFILE], default_id="gemma-4-e2b")


def _covered_reg() -> ModelRegistry:
    """Two models: repo -> strong, standalone -> gemma; no gaps for those classes."""
    return _make_registry([_GEMMA_PROFILE, _STRONG_PROFILE], default_id="gemma-4-e2b")


def _gap_decision(model_id: str = "gemma-4-e2b", cls: str = "multi-step-repo") -> dict:
    return {
        "model_id": model_id,
        "problem_class": cls,
        "confidence": 0.2,
        "rationale": "HARNESS-GAP: no coverage",
    }


# ---------------------------------------------------------------------------
# record_unhandled: basic write
# ---------------------------------------------------------------------------

class TestRecordUnhandled:

    def test_appends_parseable_json_line(self, tmp_path):
        log = tmp_path / "new_classes.jsonl"
        record_unhandled(
            {"is_repo_task": True, "source": "fix the repo"},
            _gap_decision(),
            path=log,
        )
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert "ts" in rec
        assert rec["chosen_default"] == "gemma-4-e2b"
        assert rec["confidence"] == 0.2

    def test_signature_contains_required_fields(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled(
            {"is_repo_task": True, "has_examples": False},
            _gap_decision(),
            path=log,
        )
        sig = json.loads(log.read_text().strip())["signature"]
        for field in ("is_repo_task", "is_multi_file", "has_examples",
                      "fn_len_bucket", "language", "error_signal"):
            assert field in sig, f"signature missing field: {field}"

    def test_signature_is_repo_task_true(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled({"is_repo_task": True}, _gap_decision(), path=log)
        sig = json.loads(log.read_text().strip())["signature"]
        assert sig["is_repo_task"] is True

    def test_signature_is_repo_task_false_default(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled({"source": "plain fn"}, _gap_decision(), path=log)
        sig = json.loads(log.read_text().strip())["signature"]
        assert sig["is_repo_task"] is False

    def test_task_sample_truncated_to_200_chars(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled({"source": "x" * 1000}, _gap_decision(), path=log)
        rec = json.loads(log.read_text().strip())
        assert len(rec["task_sample"]) <= 200

    def test_task_sample_empty_for_no_source(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled({}, _gap_decision(), path=log)
        rec = json.loads(log.read_text().strip())
        assert isinstance(rec["task_sample"], str)

    def test_multiple_calls_append_multiple_lines(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        for i in range(3):
            record_unhandled({"source": f"task {i}"}, _gap_decision(), path=log)
        lines = log.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_missing_decision_fields_handled_defensively(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled({}, {"model_id": "x"}, path=log)  # no confidence/rationale
        assert log.exists()
        rec = json.loads(log.read_text().strip())
        assert "signature" in rec
        assert rec["chosen_default"] == "x"
        assert rec["confidence"] == 0.0  # safe default

    def test_non_dict_problem_handled(self, tmp_path):
        """A plain string problem does not raise; produces a valid record."""
        log = tmp_path / "nc.jsonl"
        record_unhandled("some raw task string", _gap_decision(), path=log)
        assert log.exists()

    def test_error_signal_extracted_from_traceback(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        problem = {
            "source": "def foo(): pass",
            "traceback": (
                "Traceback (most recent call last):\n"
                "  ...\n"
                "AttributeError: 'NoneType' has no attribute 'bar'"
            ),
        }
        record_unhandled(problem, _gap_decision(), path=log)
        sig = json.loads(log.read_text().strip())["signature"]
        assert "AttributeError" in sig["error_signal"]

    def test_language_detected_from_py_files(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled(
            {"files": ["foo.py", "bar.py"], "source": ""},
            _gap_decision(),
            path=log,
        )
        sig = json.loads(log.read_text().strip())["signature"]
        assert sig["language"] == "python"

    def test_language_detected_from_source_patterns(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled(
            {"source": "def add(a, b):\n    return a + b"},
            _gap_decision(),
            path=log,
        )
        sig = json.loads(log.read_text().strip())["signature"]
        assert sig["language"] == "python"

    def test_language_explicit_field_wins(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled(
            {"language": "rust", "source": "def foo(): pass"},
            _gap_decision(),
            path=log,
        )
        sig = json.loads(log.read_text().strip())["signature"]
        assert sig["language"] == "rust"

    def test_parent_dirs_created_automatically(self, tmp_path):
        """record_unhandled creates nested parent directories if missing."""
        log = tmp_path / "nested" / "deep" / "nc.jsonl"
        record_unhandled({}, _gap_decision(), path=log)
        assert log.exists()

    def test_record_contains_problem_class(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled({}, _gap_decision(cls="multi-step-repo"), path=log)
        rec = json.loads(log.read_text().strip())
        assert rec["problem_class"] == "multi-step-repo"

    def test_record_ts_is_iso_format(self, tmp_path):
        """Timestamp ends with 'Z' and contains 'T' (ISO 8601)."""
        log = tmp_path / "nc.jsonl"
        record_unhandled({}, _gap_decision(), path=log)
        rec = json.loads(log.read_text().strip())
        ts = rec["ts"]
        assert "T" in ts
        assert ts.endswith("Z")

    def test_has_examples_heuristic_from_source(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled(
            {"source": ">>> add(1, 2)\n3"},
            _gap_decision(),
            path=log,
        )
        sig = json.loads(log.read_text().strip())["signature"]
        assert sig["has_examples"] is True

    def test_fn_len_bucket_small(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        # 5 lines -> "small"
        record_unhandled({"source": "\n".join(["line"] * 5)}, _gap_decision(), path=log)
        sig = json.loads(log.read_text().strip())["signature"]
        assert sig["fn_len_bucket"] == "small"

    def test_fn_len_bucket_empty_for_no_source(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled({}, _gap_decision(), path=log)
        sig = json.loads(log.read_text().strip())["signature"]
        assert sig["fn_len_bucket"] == "empty"


# ---------------------------------------------------------------------------
# review_new_classes: grouping and summary
# ---------------------------------------------------------------------------

class TestReviewNewClasses:

    def test_empty_log_returns_zero_total(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        result = review_new_classes(path=log)
        assert result["total"] == 0
        assert result["groups"] == {}
        assert result["top_signatures"] == []

    def test_nonexistent_file_returns_zero_total(self, tmp_path):
        result = review_new_classes(path=tmp_path / "does_not_exist.jsonl")
        assert result["total"] == 0

    def test_total_count_matches_records(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        for _ in range(5):
            record_unhandled({"is_repo_task": True}, _gap_decision(), path=log)
        result = review_new_classes(path=log)
        assert result["total"] == 5

    def test_recurring_signatures_grouped_into_one_group(self, tmp_path):
        """Same structural signature repeated N times -> one group, count N."""
        log = tmp_path / "nc.jsonl"
        same = {"is_repo_task": True, "is_multi_file": False,
                "has_examples": False, "source": "fix repo"}
        for _ in range(4):
            record_unhandled(same, _gap_decision(), path=log)
        result = review_new_classes(path=log)
        assert result["total"] == 4
        assert len(result["groups"]) == 1
        assert result["top_signatures"][0][1] == 4

    def test_different_signatures_form_separate_groups(self, tmp_path):
        """Problems with different is_repo_task flags group separately."""
        log = tmp_path / "nc.jsonl"
        dec = _gap_decision()
        record_unhandled({"is_repo_task": True, "has_examples": False}, dec, path=log)
        record_unhandled({"is_repo_task": True, "has_examples": False}, dec, path=log)
        record_unhandled({"is_repo_task": False, "has_examples": True,
                          "source": ">>> foo()\n1"}, dec, path=log)
        result = review_new_classes(path=log)
        assert result["total"] == 3
        assert len(result["groups"]) == 2  # two distinct signatures

    def test_top_signatures_sorted_descending_by_count(self, tmp_path):
        """Group with more occurrences appears first."""
        log = tmp_path / "nc.jsonl"
        dec = _gap_decision()
        for _ in range(3):
            record_unhandled({"is_repo_task": True, "source": "repo"}, dec, path=log)
        record_unhandled({"has_examples": True, "source": ">>> foo()\n1"}, dec, path=log)
        result = review_new_classes(path=log)
        counts = [c for _, c in result["top_signatures"]]
        assert counts == sorted(counts, reverse=True)
        assert counts[0] >= counts[-1]

    def test_return_has_all_required_keys(self, tmp_path):
        result = review_new_classes(path=tmp_path / "nc.jsonl")
        assert "total" in result
        assert "groups" in result
        assert "top_signatures" in result

    def test_groups_values_contain_full_records(self, tmp_path):
        log = tmp_path / "nc.jsonl"
        record_unhandled({"is_repo_task": True}, _gap_decision(), path=log)
        result = review_new_classes(path=log)
        # There should be one group
        assert len(result["groups"]) == 1
        group_records = list(result["groups"].values())[0]
        assert len(group_records) == 1
        assert "ts" in group_records[0]
        assert "chosen_default" in group_records[0]

    def test_top_signatures_key_is_string(self, tmp_path):
        """top_signatures keys must be strings (JSON-safe)."""
        log = tmp_path / "nc.jsonl"
        record_unhandled({"is_repo_task": True}, _gap_decision(), path=log)
        result = review_new_classes(path=log)
        for key, count in result["top_signatures"]:
            assert isinstance(key, str)
            assert isinstance(count, int)


# ---------------------------------------------------------------------------
# Integration: route wiring — covered does NOT record; uncovered DOES record
# ---------------------------------------------------------------------------

class TestRouteRecordIntegration:

    def test_covered_class_does_not_record(self, tmp_path, monkeypatch):
        """A route to a covered class must NOT write to the new-class log."""
        log = tmp_path / "nc.jsonl"
        monkeypatch.setattr(ncl, "_DEFAULT_LOG_PATH", log)
        reg = _covered_reg()
        # repo task is covered by strong-model-7b
        route({"is_repo_task": True}, reg, record=True)
        assert not log.exists(), "covered-class route must not write the new-class log"

    def test_standalone_covered_class_does_not_record(self, tmp_path, monkeypatch):
        """Standalone-fn-gen is covered by gemma; must not record."""
        log = tmp_path / "nc.jsonl"
        monkeypatch.setattr(ncl, "_DEFAULT_LOG_PATH", log)
        reg = _covered_reg()
        route({"has_examples": True, "source": ">>> add(1,2)\n3"}, reg, record=True)
        assert not log.exists()

    def test_uncovered_route_with_record_true_writes_log(self, tmp_path, monkeypatch):
        """HARNESS-GAP route with record=True must write exactly one log entry."""
        log = tmp_path / "nc.jsonl"
        monkeypatch.setattr(ncl, "_DEFAULT_LOG_PATH", log)
        reg = _uncovered_reg()  # gemma-only; no multi-step-repo coverage
        route({"is_repo_task": True}, reg, record=True)
        assert log.exists(), "HARNESS-GAP route must write the new-class log"
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["chosen_default"] == "gemma-4-e2b"
        assert "HARNESS-GAP" in rec["rationale"]

    def test_uncovered_route_with_record_false_does_not_write(self, tmp_path, monkeypatch):
        """record=False suppresses writing even for HARNESS-GAP routes."""
        log = tmp_path / "nc.jsonl"
        monkeypatch.setattr(ncl, "_DEFAULT_LOG_PATH", log)
        reg = _uncovered_reg()
        route({"is_repo_task": True}, reg, record=False)
        assert not log.exists(), "record=False must not write the new-class log"

    def test_multiple_uncovered_routes_append_multiple_lines(self, tmp_path, monkeypatch):
        """Two HARNESS-GAP routes -> two log entries."""
        log = tmp_path / "nc.jsonl"
        monkeypatch.setattr(ncl, "_DEFAULT_LOG_PATH", log)
        reg = _uncovered_reg()
        route({"is_repo_task": True, "source": "task A"}, reg, record=True)
        route({"is_repo_task": True, "source": "task B"}, reg, record=True)
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_recorded_entry_has_correct_signature_features(self, tmp_path, monkeypatch):
        """The recorded entry's signature reflects the problem's features."""
        log = tmp_path / "nc.jsonl"
        monkeypatch.setattr(ncl, "_DEFAULT_LOG_PATH", log)
        reg = _uncovered_reg()
        route({"is_repo_task": True, "is_multi_file": False}, reg, record=True)
        rec = json.loads(log.read_text().strip())
        sig = rec["signature"]
        assert sig["is_repo_task"] is True
        assert sig["is_multi_file"] is False

    def test_route_return_value_unchanged_by_recording(self, tmp_path, monkeypatch):
        """The decision dict returned by route() is identical regardless of record flag."""
        log = tmp_path / "nc.jsonl"
        monkeypatch.setattr(ncl, "_DEFAULT_LOG_PATH", log)
        reg = _uncovered_reg()
        problem = {"is_repo_task": True, "source": "fix repo"}
        d_record_on = route(problem, reg, record=True)
        d_record_off = route(problem, reg, record=False)
        assert d_record_on == d_record_off

    def test_review_sees_recorded_entries(self, tmp_path, monkeypatch):
        """Entries written by route() are visible in review_new_classes summary."""
        log = tmp_path / "nc.jsonl"
        monkeypatch.setattr(ncl, "_DEFAULT_LOG_PATH", log)
        reg = _uncovered_reg()
        route({"is_repo_task": True}, reg, record=True)
        route({"is_repo_task": True}, reg, record=True)
        result = review_new_classes(path=log)
        assert result["total"] == 2
        assert result["top_signatures"][0][1] == 2
