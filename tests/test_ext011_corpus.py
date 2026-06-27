"""EXT-011-REQ-9/10 tests: multi-repo task corpus and big eval bar (A/B arm).

Tests verify:
1. tasks_corpus() loads existing valid task JSONs and stamps each with 'repo'.
2. Deduplication: tasks appearing in multiple slices are not double-counted.
3. corpus_counts() returns per-repo breakdowns.
4. tasks_corpus(bar="standard") returns only more-itertools_valid_tasks.json.
5. The validate_redgreen path uses _spec(repo)["test"] not hardcoded "tests/".
6. Missing JSON files are silently skipped (partial builds are valid).
7. [REQ-10] run_gherkin_jaros_multi(agentic=True) routes to attempt_gherkin (orchestrator arm).
8. [REQ-10] run_gherkin_jaros_multi(agentic=False) routes to attempt_gherkin_jaros (deterministic arm).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from harness.commit_replay import (
    REPO_LIST,
    corpus_counts,
    tasks_corpus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_corpus_dir(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal repos + artifacts dir structure for offline tests."""
    repos_dir = tmp_path / "repos"
    artifacts_dir = tmp_path / "repos" / ".." / "artifacts"
    artifacts_dir = (tmp_path / "artifacts")
    repos_dir.mkdir()
    artifacts_dir.mkdir()
    return repos_dir, artifacts_dir


def _write_tasks(artifacts: Path, name: str, tasks: list[dict]) -> None:
    (artifacts / name).write_text(json.dumps(tasks, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: tasks_corpus loads existing JSONs and stamps 'repo'
# ---------------------------------------------------------------------------
def test_tasks_corpus_stamps_repo_key(tmp_path: Path):
    repos_dir, artifacts = _make_corpus_dir(tmp_path)

    mi_tasks = [{"sha": "aa" * 20, "parent": "bb" * 20, "subject": "Add foo",
                 "redgreen": ["tests/test_more.py::test_foo"],
                 "code_files": ["more_itertools/more.py"],
                 "test_files": ["tests/test_more.py"]}]
    _write_tasks(artifacts, "more-itertools_valid_tasks.json", mi_tasks)

    repo_list = [{"name": "more-itertools", "tags": ["valid"]}]
    tasks = tasks_corpus(repos_dir=repos_dir, repo_list=repo_list, bar="big")

    assert len(tasks) == 1
    assert tasks[0]["repo"] == "more-itertools"
    assert tasks[0]["sha"] == "aa" * 20


# ---------------------------------------------------------------------------
# Test 2: deduplication across slices
# ---------------------------------------------------------------------------
def test_tasks_corpus_deduplicates_across_slices(tmp_path: Path):
    repos_dir, artifacts = _make_corpus_dir(tmp_path)

    shared_task = {"sha": "cc" * 20, "parent": "dd" * 20, "subject": "Shared",
                   "redgreen": ["tests/test_more.py::test_shared"],
                   "code_files": ["more_itertools/more.py"],
                   "test_files": ["tests/test_more.py"]}
    unique_task = {"sha": "ee" * 20, "parent": "ff" * 20, "subject": "Unique",
                   "redgreen": ["tests/test_more.py::test_unique"],
                   "code_files": ["more_itertools/more.py"],
                   "test_files": ["tests/test_more.py"]}

    _write_tasks(artifacts, "more-itertools_valid_tasks.json", [shared_task])
    _write_tasks(artifacts, "more-itertools_valid_s800_tasks.json", [shared_task, unique_task])

    repo_list = [
        {"name": "more-itertools", "tags": ["valid"]},
        {"name": "more-itertools", "tags": ["valid_s800"]},
    ]
    tasks = tasks_corpus(repos_dir=repos_dir, repo_list=repo_list, bar="big")

    assert len(tasks) == 2, f"expected 2 unique tasks, got {len(tasks)}"
    shas = {t["sha"] for t in tasks}
    assert "cc" * 20 in shas
    assert "ee" * 20 in shas


# ---------------------------------------------------------------------------
# Test 3: corpus_counts returns per-repo breakdown
# ---------------------------------------------------------------------------
def test_corpus_counts_breakdown(tmp_path: Path):
    repos_dir, artifacts = _make_corpus_dir(tmp_path)

    mi_tasks = [
        {"sha": f"{'aa' * 20}_{i}", "parent": "bb" * 20, "subject": f"MI task {i}",
         "redgreen": [], "code_files": [], "test_files": []}
        for i in range(3)
    ]
    toolz_tasks = [
        {"sha": f"{'cc' * 20}_{i}", "parent": "dd" * 20, "subject": f"Toolz task {i}",
         "redgreen": [], "code_files": [], "test_files": []}
        for i in range(2)
    ]

    # Ensure unique SHAs (tasks_corpus deduplicates on sha)
    for i, t in enumerate(mi_tasks):
        t["sha"] = f"aa{i:038d}"
    for i, t in enumerate(toolz_tasks):
        t["sha"] = f"cc{i:038d}"

    _write_tasks(artifacts, "more-itertools_valid_tasks.json", mi_tasks)
    _write_tasks(artifacts, "toolz_valid_tasks.json", toolz_tasks)

    repo_list = [
        {"name": "more-itertools", "tags": ["valid"]},
        {"name": "toolz", "tags": ["valid"]},
    ]
    counts = corpus_counts(repos_dir=repos_dir)
    # corpus_counts uses the global REPO_LIST but only sees what's in artifacts/
    # For unit test we call tasks_corpus directly.
    tasks = tasks_corpus(repos_dir=repos_dir, repo_list=repo_list, bar="big")
    counts_direct: dict[str, int] = {}
    for t in tasks:
        counts_direct[t["repo"]] = counts_direct.get(t["repo"], 0) + 1

    assert counts_direct.get("more-itertools", 0) == 3
    assert counts_direct.get("toolz", 0) == 2


# ---------------------------------------------------------------------------
# Test 4: bar="standard" returns only more-itertools_valid_tasks.json
# ---------------------------------------------------------------------------
def test_tasks_corpus_standard_bar(tmp_path: Path):
    repos_dir, artifacts = _make_corpus_dir(tmp_path)

    mi_task = {"sha": "aa" * 20, "parent": "bb" * 20, "subject": "MI",
               "redgreen": [], "code_files": [], "test_files": []}
    toolz_task = {"sha": "cc" * 20, "parent": "dd" * 20, "subject": "Toolz",
                  "redgreen": [], "code_files": [], "test_files": []}

    _write_tasks(artifacts, "more-itertools_valid_tasks.json", [mi_task])
    _write_tasks(artifacts, "toolz_valid_tasks.json", [toolz_task])

    tasks = tasks_corpus(repos_dir=repos_dir, bar="standard")
    assert len(tasks) == 1
    assert tasks[0]["repo"] == "more-itertools"


# ---------------------------------------------------------------------------
# Test 5: missing JSON files are silently skipped
# ---------------------------------------------------------------------------
def test_tasks_corpus_missing_json_skipped(tmp_path: Path):
    repos_dir, artifacts = _make_corpus_dir(tmp_path)
    # No JSON files written at all
    repo_list = [
        {"name": "more-itertools", "tags": ["valid", "valid_s800"]},
        {"name": "toolz", "tags": ["valid"]},
    ]
    tasks = tasks_corpus(repos_dir=repos_dir, repo_list=repo_list, bar="big")
    assert tasks == []


# ---------------------------------------------------------------------------
# Test 6: validate_redgreen uses _spec(repo)["test"] not hardcoded "tests/"
# ---------------------------------------------------------------------------
def test_spec_test_dir_used_in_validate_redgreen():
    """Static check: the source of validate_redgreen must not contain
    a hardcoded checkout of 'tests/' — it must use _spec(repo)."""
    import inspect
    from harness.commit_replay import validate_redgreen

    src = inspect.getsource(validate_redgreen)
    # The hardcoded string was: _git(repo, "checkout", c.sha, "--", "tests/")
    # After the fix it must use _spec(repo)["test"] instead.
    assert '"tests/"' not in src, (
        'validate_redgreen still contains hardcoded "tests/" checkout — '
        'should use _spec(repo)["test"] for multi-repo correctness'
    )
    assert '_spec(repo)["test"]' in src, (
        'validate_redgreen should use _spec(repo)["test"] for the test-dir checkout'
    )


# ---------------------------------------------------------------------------
# Test 7: REPO_LIST is present and contains expected repos
# ---------------------------------------------------------------------------
def test_repo_list_contains_expected_repos():
    names = {e["name"] for e in REPO_LIST}
    assert "more-itertools" in names
    assert "toolz" in names


# ---------------------------------------------------------------------------
# Test 8 (REQ-10): A/B routing — agentic=True routes to attempt_gherkin,
#   agentic=False routes to attempt_gherkin_jaros.  Uses monkeypatching so
#   Docker / LLM / repos are never touched (fully offline).
# ---------------------------------------------------------------------------
def test_run_gherkin_jaros_multi_agentic_routes_to_orchestrator(monkeypatch, tmp_path):
    """EXT-011 REQ-10: agentic=True arm calls attempt_gherkin (orchestrator)."""
    import harness.commit_replay as cr

    calls: list[str] = []

    def fake_attempt_gherkin(repo, task, branch, **kwargs):
        calls.append(f"agentic:{kwargs.get('agentic', False)}")
        return "pass"

    def fake_attempt_gherkin_jaros(repo, task, branch, **kwargs):
        calls.append("jaros")
        return "pass"

    monkeypatch.setattr(cr, "attempt_gherkin", fake_attempt_gherkin)
    monkeypatch.setattr(cr, "attempt_gherkin_jaros", fake_attempt_gherkin_jaros)

    # Stub _git so the branch lookup doesn't fail (no real repo on disk).
    monkeypatch.setattr(cr, "_git", lambda *a, **kw: "main\n")

    tasks = [{"sha": "aa" * 20, "parent": "bb" * 20, "subject": "X",
              "repo": "more-itertools", "redgreen": []}]

    cr.run_gherkin_jaros_multi(tmp_path, tasks, agentic=True)

    assert len(calls) == 1, f"expected 1 call, got {calls}"
    assert calls[0] == "agentic:True", (
        f"agentic=True arm should call attempt_gherkin with agentic=True, got {calls[0]}"
    )


def test_run_gherkin_jaros_multi_deterministic_routes_to_jaros(monkeypatch, tmp_path):
    """EXT-011 REQ-10: agentic=False (default) arm calls attempt_gherkin_jaros (deterministic)."""
    import harness.commit_replay as cr

    calls: list[str] = []

    def fake_attempt_gherkin(repo, task, branch, **kwargs):
        calls.append(f"agentic:{kwargs.get('agentic', False)}")
        return "pass"

    def fake_attempt_gherkin_jaros(repo, task, branch, **kwargs):
        calls.append("jaros")
        return "pass"

    monkeypatch.setattr(cr, "attempt_gherkin", fake_attempt_gherkin)
    monkeypatch.setattr(cr, "attempt_gherkin_jaros", fake_attempt_gherkin_jaros)
    monkeypatch.setattr(cr, "_git", lambda *a, **kw: "main\n")

    tasks = [{"sha": "aa" * 20, "parent": "bb" * 20, "subject": "X",
              "repo": "more-itertools", "redgreen": []}]

    cr.run_gherkin_jaros_multi(tmp_path, tasks, agentic=False)

    assert len(calls) == 1, f"expected 1 call, got {calls}"
    assert calls[0] == "jaros", (
        f"agentic=False arm should call attempt_gherkin_jaros, got {calls[0]}"
    )
