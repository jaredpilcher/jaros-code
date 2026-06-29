"""Offline tests for harness/profile_qwen.py — EXT-021 REQ-4/REQ-5.

All tests are OFFLINE: serve_fn, get_current_fn, restore_fn, humaneval_eval_fn,
and repo_eval_fn are injected stubs.  No live Jetson, no Docker, no real LLM calls.

Acceptance criteria covered
----------------------------
(a) A class that CLEARS the bar (passed_bool=True) is written into the profile JSON
    with recorded evidence {name, bar, score, date}.
(b) A class BELOW the bar (passed_bool=False) is NOT added to the profile JSON
    (honest failure — Tenet 3: never claim a class without proof).
(c) The original served model is ALWAYS restored in the finally block, even when
    an eval function raises an exception.
(d) Classes already recorded in the profile are skipped (idempotent).
(e) _parse_fail_shas extracts [fail] SHA prefixes correctly from bigbar result text.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.profile_qwen import run_profile_qwen, _parse_fail_shas


# ---------------------------------------------------------------------------
# Helpers: write a minimal qwen profile to tmp_path
# ---------------------------------------------------------------------------

def _write_qwen_profile(tmp_path: Path, classes: Optional[list] = None) -> Path:
    """Write a minimal qwen profile JSON to tmp_path/qwen2.5-coder-3b.json."""
    profile = {
        "id": "qwen2.5-coder-3b",
        "alias": "qwen2.5-coder-3b",
        "serve": {"gguf": "/home/jared/gemma-server/qwen.gguf", "ctx": 4096,
                  "ngl": 99, "fits_jetson": True},
        "classes": classes if classes is not None else [],
        "adaptation": {"prompts": "qwen-instruct-direct"},
    }
    path = tmp_path / "qwen2.5-coder-3b.json"
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return path


def _stub_pass_evals() -> tuple:
    """Return (humaneval_eval_fn, repo_eval_fn) stubs that both PASS the bar."""
    he = lambda n: {"passed": 12, "total": 20, "score": "~12/20 (60%)", "passed_bool": True}
    repo = lambda m: {"cracked": 2, "total": 8, "score": "2/8", "passed_bool": True}
    return he, repo


def _stub_fail_evals() -> tuple:
    """Return (humaneval_eval_fn, repo_eval_fn) stubs that both FAIL the bar."""
    he = lambda n: {"passed": 5, "total": 20, "score": "~5/20 (25%)", "passed_bool": False}
    repo = lambda m: {"cracked": 0, "total": 8, "score": "0/8", "passed_bool": False}
    return he, repo


# ---------------------------------------------------------------------------
# Tests: class earned when bar cleared
# ---------------------------------------------------------------------------

def test_cleared_class_written_to_profile(tmp_path: Path) -> None:
    """A class that clears the bar is appended to the profile JSON with evidence."""
    _write_qwen_profile(tmp_path)
    he_fn, repo_fn = _stub_pass_evals()

    result = run_profile_qwen(
        n=20, m=8,
        models_dir=tmp_path,
        serve_fn=lambda: None,
        get_current_fn=lambda: "gemma-4-e2b",
        restore_fn=lambda mid: None,
        humaneval_eval_fn=he_fn,
        repo_eval_fn=repo_fn,
        now=lambda: "2026-06-28",
    )

    assert "standalone-fn-gen" in result["added"]
    assert "multi-step-repo" in result["added"]
    assert result["rejected"] == []

    # Profile on disk must contain both classes with evidence
    updated = json.loads((tmp_path / "qwen2.5-coder-3b.json").read_text(encoding="utf-8"))
    names = [c["name"] for c in updated["classes"]]
    assert "standalone-fn-gen" in names
    assert "multi-step-repo" in names

    # Evidence fields present
    for cls in updated["classes"]:
        assert "bar" in cls
        assert "score" in cls
        assert "date" in cls
        assert cls["date"] == "2026-06-28"


def test_cleared_class_evidence_matches_eval_score(tmp_path: Path) -> None:
    """The score recorded in the profile matches what the eval function returned."""
    _write_qwen_profile(tmp_path)

    he_fn = lambda n: {"passed": 15, "total": 20, "score": "~15/20 (75%)", "passed_bool": True}
    repo_fn = lambda m: {"cracked": 3, "total": 8, "score": "3/8", "passed_bool": True}

    run_profile_qwen(
        n=20, m=8,
        models_dir=tmp_path,
        serve_fn=lambda: None,
        get_current_fn=lambda: "gemma-4-e2b",
        restore_fn=lambda mid: None,
        humaneval_eval_fn=he_fn,
        repo_eval_fn=repo_fn,
        now=lambda: "2026-06-28",
    )

    updated = json.loads((tmp_path / "qwen2.5-coder-3b.json").read_text(encoding="utf-8"))
    he_entry = next(c for c in updated["classes"] if c["name"] == "standalone-fn-gen")
    repo_entry = next(c for c in updated["classes"] if c["name"] == "multi-step-repo")

    assert "15/20" in he_entry["score"] or "75%" in he_entry["score"]
    assert "3/8" in repo_entry["score"]


# ---------------------------------------------------------------------------
# Tests: class NOT recorded when below bar
# ---------------------------------------------------------------------------

def test_below_bar_class_not_in_profile(tmp_path: Path) -> None:
    """A class below the bar is NOT added to the profile JSON."""
    _write_qwen_profile(tmp_path)
    he_fn, repo_fn = _stub_fail_evals()

    result = run_profile_qwen(
        n=20, m=8,
        models_dir=tmp_path,
        serve_fn=lambda: None,
        get_current_fn=lambda: "gemma-4-e2b",
        restore_fn=lambda mid: None,
        humaneval_eval_fn=he_fn,
        repo_eval_fn=repo_fn,
        now=lambda: "2026-06-28",
    )

    assert result["added"] == []
    assert "standalone-fn-gen" in result["rejected"]
    assert "multi-step-repo" in result["rejected"]

    # Profile on disk unchanged: classes still empty
    updated = json.loads((tmp_path / "qwen2.5-coder-3b.json").read_text(encoding="utf-8"))
    assert updated["classes"] == []


def test_partial_pass_only_earns_passing_class(tmp_path: Path) -> None:
    """Only the class that clears its bar is written; the other stays rejected."""
    _write_qwen_profile(tmp_path)

    he_fn = lambda n: {"passed": 12, "total": 20, "score": "~12/20 (60%)", "passed_bool": True}
    repo_fn = lambda m: {"cracked": 0, "total": 8, "score": "0/8", "passed_bool": False}

    result = run_profile_qwen(
        n=20, m=8,
        models_dir=tmp_path,
        serve_fn=lambda: None,
        get_current_fn=lambda: "gemma-4-e2b",
        restore_fn=lambda mid: None,
        humaneval_eval_fn=he_fn,
        repo_eval_fn=repo_fn,
        now=lambda: "2026-06-28",
    )

    assert result["added"] == ["standalone-fn-gen"]
    assert result["rejected"] == ["multi-step-repo"]

    updated = json.loads((tmp_path / "qwen2.5-coder-3b.json").read_text(encoding="utf-8"))
    names = [c["name"] for c in updated["classes"]]
    assert "standalone-fn-gen" in names
    assert "multi-step-repo" not in names


# ---------------------------------------------------------------------------
# Tests: always-restore (finally block)
# ---------------------------------------------------------------------------

def test_original_model_restored_on_success(tmp_path: Path) -> None:
    """restore_fn is called with the original model id after a successful run."""
    _write_qwen_profile(tmp_path)
    he_fn, repo_fn = _stub_pass_evals()

    restored: list[str] = []

    run_profile_qwen(
        n=20, m=8,
        models_dir=tmp_path,
        serve_fn=lambda: None,
        get_current_fn=lambda: "gemma-4-e2b",
        restore_fn=lambda mid: restored.append(mid),
        humaneval_eval_fn=he_fn,
        repo_eval_fn=repo_fn,
        now=lambda: "2026-06-28",
    )

    assert restored == ["gemma-4-e2b"]


def test_original_model_restored_on_eval_error(tmp_path: Path) -> None:
    """restore_fn is called even when the humaneval_eval_fn raises an exception."""
    _write_qwen_profile(tmp_path)

    restored: list[str] = []

    def _explode(n: int) -> dict:
        raise RuntimeError("eval exploded!")

    with pytest.raises(RuntimeError, match="eval exploded"):
        run_profile_qwen(
            n=20, m=8,
            models_dir=tmp_path,
            serve_fn=lambda: None,
            get_current_fn=lambda: "gemma-4-e2b",
            restore_fn=lambda mid: restored.append(mid),
            humaneval_eval_fn=_explode,
            repo_eval_fn=lambda m: {"cracked": 0, "total": 8, "score": "0/8", "passed_bool": False},
            now=lambda: "2026-06-28",
        )

    assert restored == ["gemma-4-e2b"]


def test_original_model_restored_on_repo_eval_error(tmp_path: Path) -> None:
    """restore_fn is called even when repo_eval_fn raises an exception."""
    _write_qwen_profile(tmp_path)

    restored: list[str] = []
    he_fn = lambda n: {"passed": 12, "total": 20, "score": "~12/20 (60%)", "passed_bool": True}

    def _explode_repo(m: int) -> dict:
        raise RuntimeError("repo eval exploded!")

    with pytest.raises(RuntimeError, match="repo eval exploded"):
        run_profile_qwen(
            n=20, m=8,
            models_dir=tmp_path,
            serve_fn=lambda: None,
            get_current_fn=lambda: "gemma-4-e2b",
            restore_fn=lambda mid: restored.append(mid),
            humaneval_eval_fn=he_fn,
            repo_eval_fn=_explode_repo,
            now=lambda: "2026-06-28",
        )

    assert restored == ["gemma-4-e2b"]


def test_restore_called_with_none_current_model_uses_fallback(tmp_path: Path) -> None:
    """When get_current_fn returns None, restore_fn is called with the fallback 'gemma-4-e2b'."""
    _write_qwen_profile(tmp_path)
    he_fn, repo_fn = _stub_pass_evals()

    restored: list[str] = []

    run_profile_qwen(
        n=20, m=8,
        models_dir=tmp_path,
        serve_fn=lambda: None,
        get_current_fn=lambda: None,   # unknown original model
        restore_fn=lambda mid: restored.append(mid),
        humaneval_eval_fn=he_fn,
        repo_eval_fn=repo_fn,
        now=lambda: "2026-06-28",
    )

    assert restored == ["gemma-4-e2b"]   # fallback applied


# ---------------------------------------------------------------------------
# Tests: idempotency (already-recorded class skipped)
# ---------------------------------------------------------------------------

def test_already_recorded_class_skipped(tmp_path: Path) -> None:
    """A class already in the profile is not duplicated on a second profiling run."""
    _write_qwen_profile(tmp_path, classes=[
        {
            "name": "standalone-fn-gen",
            "bar": "HumanEval pass@1 >=50%",
            "score": "~12/20 (60%)",
            "date": "2026-06-20",
        }
    ])
    he_fn, repo_fn = _stub_pass_evals()

    eval_calls: list[str] = []
    he_fn_tracked = lambda n: (eval_calls.append("he"), he_fn(n))[1]

    result = run_profile_qwen(
        n=20, m=8,
        models_dir=tmp_path,
        serve_fn=lambda: None,
        get_current_fn=lambda: "gemma-4-e2b",
        restore_fn=lambda mid: None,
        humaneval_eval_fn=he_fn_tracked,
        repo_eval_fn=repo_fn,
        now=lambda: "2026-06-28",
    )

    # standalone-fn-gen was already there — eval should not be called for it
    assert "he" not in eval_calls, "eval_fn called for already-recorded class"

    # Only multi-step-repo was newly added
    assert result["added"] == ["multi-step-repo"]

    # Profile has exactly 2 classes now (original + new)
    updated = json.loads((tmp_path / "qwen2.5-coder-3b.json").read_text(encoding="utf-8"))
    assert len(updated["classes"]) == 2


# ---------------------------------------------------------------------------
# Tests: _parse_fail_shas helper
# ---------------------------------------------------------------------------

def test_parse_fail_shas_from_bigbar_format(tmp_path: Path) -> None:
    """_parse_fail_shas extracts [fail] SHA prefixes in order of appearance."""
    bigbar = tmp_path / "bigbar.txt"
    bigbar.write_text(
        "  1/101 [more-itertools] e39ae39c [pass] | task A\n"
        "  2/101 [more-itertools] cca32949 [fail] | task B\n"
        "  3/101 [more-itertools] 6887a7bd [pass] | task C\n"
        "  4/101 [more-itertools] f8ccab22 [fail] | task D\n"
        "  5/101 [more-itertools] 5c8336c5 [capped] | task E\n",
        encoding="utf-8",
    )

    shas = _parse_fail_shas(bigbar)

    assert shas == ["cca32949", "f8ccab22"]


def test_parse_fail_shas_empty_when_no_fail_lines(tmp_path: Path) -> None:
    """_parse_fail_shas returns [] when there are no [fail] lines."""
    bigbar = tmp_path / "bigbar.txt"
    bigbar.write_text(
        "  1/5 e39ae39c [pass] | task A\n"
        "  2/5 6887a7bd [capped] | task B\n",
        encoding="utf-8",
    )

    assert _parse_fail_shas(bigbar) == []


def test_parse_fail_shas_returns_empty_for_missing_file(tmp_path: Path) -> None:
    """_parse_fail_shas returns [] when the file does not exist."""
    missing = tmp_path / "nonexistent.txt"
    assert _parse_fail_shas(missing) == []


# ---------------------------------------------------------------------------
# Tests: profile JSON error handling
# ---------------------------------------------------------------------------

def test_missing_profile_json_raises(tmp_path: Path) -> None:
    """run_profile_qwen raises FileNotFoundError when the profile JSON is absent."""
    # tmp_path has no qwen2.5-coder-3b.json
    with pytest.raises(FileNotFoundError):
        run_profile_qwen(
            n=5, m=3,
            models_dir=tmp_path,
            serve_fn=lambda: None,
            get_current_fn=lambda: "gemma-4-e2b",
            restore_fn=lambda mid: None,
            humaneval_eval_fn=lambda n: {"passed_bool": True, "score": "ok"},
            repo_eval_fn=lambda m: {"passed_bool": True, "cracked": 1, "total": 3, "score": "1/3"},
            now=lambda: "2026-06-28",
        )
