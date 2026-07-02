"""Tests for EXT-027 REQ-3: auto-capture of verified daily-driver solves into the
verified-solution store (the flywheel corpus).

Fully offline: no Jetson / model is called. ``fix_loop`` and ``build_from_intent`` are
monkeypatched (the same pattern as ``tests/test_ext005_daily_driver.py``), and
``harness.daily_driver.record_verified`` is monkeypatched to collect calls instead of
touching the real ``.jaros-data/artifacts/solution_memory.jsonl`` store.

CRITICAL invariant this suite proves: capture-only. ``run_daily`` must call
``record_verified`` for every SOLVED code-producing task (edit/fix/build-module/
multi-file) and MUST NOT call it for navigate/answer tasks (no code artifact) or for
UNSOLVED tasks. It must never wire ``recall_similar``/``inject_verified_example`` into
any solve prompt (that stays gated by REQ-2's kill-test).
"""

from __future__ import annotations

from pathlib import Path

from harness.daily_driver import run_daily

# #EXT-027-REQ-3 Start
_ORIGINAL_EDIT_SOURCE = "ORIGINAL-EDIT-SOURCE\n"
_ORIGINAL_FIX_SOURCE = "ORIGINAL-FIX-SOURCE\n"
_ORIGINAL_MULTI_SOURCE = "ORIGINAL-MULTI-SOURCE\n"
_BUILD_INTENT = "Build a thing that does X."


def _capture_tasks() -> list[dict]:
    return [
        {
            "id": "cap_edit_solved",
            "category": "edit",
            "split": "dev",
            "instruction": "fix the edit target",
            "target": "edit_target.py",
            "test_cmd": "python -m pytest -q",
            "files": {"edit_target.py": _ORIGINAL_EDIT_SOURCE},
        },
        {
            "id": "cap_fix_unsolved",
            "category": "fix",
            "split": "dev",
            "instruction": "fix the bug",
            "target": "fix_target.py",
            "test_cmd": "python -m pytest -q",
            "files": {"fix_target.py": _ORIGINAL_FIX_SOURCE},
        },
        {
            "id": "cap_multifile_solved",
            "category": "multi-file",
            "split": "dev",
            "instruction": "fix across files",
            "target": "multi_target.py",
            "test_cmd": "python -m pytest -q",
            "files": {"multi_target.py": _ORIGINAL_MULTI_SOURCE, "helper.py": "def h(): pass\n"},
        },
        {
            "id": "cap_build_solved",
            "category": "build-module",
            "split": "dev",
            "intent": _BUILD_INTENT,
            "target": "thing.py",
            "func": "thing",
            "signature": "def thing():",
            "test_cmd": "python -m pytest -q",
            "oracle_test": "def test_x():\n    assert True\n",
        },
        {
            "id": "cap_navigate_solved",
            "category": "navigate",
            "split": "dev",
            "instruction": "who calls X?",
            "files": {},
            "oracle": {"type": "answer", "match": "exact", "expect": "ok"},
        },
    ]


def _install_stubs(monkeypatch):
    """Stub the two model-facing touchpoints (fix_loop, build_from_intent) so run_daily
    executes fully offline, plus monkeypatch record_verified to collect calls."""
    from harness.coding_loop import LoopResult
    from harness.intent_loop import IntentResult

    def _fake_fix_loop(target, instruction, test_cmd, **kwargs):
        name = Path(target).name
        if name == "fix_target.py":
            return LoopResult(success=False, attempts=1, final_output="still failing")
        Path(target).write_text(f"FIXED::{name}\n", encoding="utf-8")
        return LoopResult(success=True, attempts=1, final_output="fixed")

    def _fake_build_from_intent(task, max_iters=3, verbose=False):
        return IntentResult(task["id"], True, True, 1, code=f"BUILT::{task['target']}")

    monkeypatch.setattr("harness.coding_loop.fix_loop", _fake_fix_loop)
    monkeypatch.setattr("harness.intent_loop.build_from_intent", _fake_build_from_intent)

    calls: list[dict] = []

    def _fake_record_verified(problem, code, **kwargs):
        calls.append({"problem": problem, "code": code})

    monkeypatch.setattr("harness.daily_driver.record_verified", _fake_record_verified)
    return calls


def test_autocapture_fires_only_for_solved_code_producing_tasks(monkeypatch):
    calls = _install_stubs(monkeypatch)

    scorecard = run_daily(_capture_tasks(), answer_fn=lambda task: "ok", max_iters=1)

    # Sanity: the scorecard itself is unaffected by capture (4 solved, 1 unsolved).
    assert scorecard["total"] == 5
    assert scorecard["solved"] == 4
    assert scorecard["perCategory"]["fix"]["passed"] == 0

    # record_verified fired exactly for the 3 SOLVED code-producing tasks
    # (edit, multi-file, build-module) — NOT for the unsolved fix task, and NOT for the
    # solved navigate task (no code artifact).
    assert len(calls) == 3

    by_source = {c["problem"].get("source"): c for c in calls}

    edit_call = by_source[_ORIGINAL_EDIT_SOURCE]
    assert edit_call["problem"]["problem_class"] == "standalone-fn-gen"
    assert edit_call["code"] == "FIXED::edit_target.py\n"

    multi_call = by_source[_ORIGINAL_MULTI_SOURCE]
    assert multi_call["problem"]["problem_class"] == "multi-file"
    assert multi_call["code"] == "FIXED::multi_target.py\n"

    build_call = by_source[_BUILD_INTENT]
    assert build_call["problem"]["problem_class"] == "standalone-fn-gen"
    assert build_call["code"] == "BUILT::thing.py"

    # Every captured call has both a non-empty code and problem_class.
    for call in calls:
        assert call["code"]
        assert call["problem"]["problem_class"]

    # Neither the unsolved fix source nor an empty/navigate source was captured.
    assert _ORIGINAL_FIX_SOURCE not in by_source


def test_autocapture_never_wires_recall_or_inject(monkeypatch):
    """CAPTURE ONLY (REQ-3): recall_similar / inject_verified_example must never be
    called by run_daily -- injection stays gated by REQ-2's (unrun) kill-test."""
    _install_stubs(monkeypatch)

    recall_calls: list = []
    inject_calls: list = []
    monkeypatch.setattr(
        "harness.solution_memory.recall_similar",
        lambda *a, **kw: recall_calls.append((a, kw)) or None,
    )
    monkeypatch.setattr(
        "harness.solution_memory.inject_verified_example",
        lambda *a, **kw: inject_calls.append((a, kw)) or (a[0] if a else ""),
    )

    run_daily(_capture_tasks(), answer_fn=lambda task: "ok", max_iters=1)

    assert recall_calls == []
    assert inject_calls == []
# #EXT-027-REQ-3 End
