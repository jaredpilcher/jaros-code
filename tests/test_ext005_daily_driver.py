"""Tests for the daily-driver parity-suite runner (EXT-005 / REQ-13).

Fully offline: no Jetson / model is called. The only model-calling piece of the
runner (``answer_fn``) is a plain injected stub, and the pytest-oracle path's
``fix_loop`` is monkeypatched so no live model call happens in these tests either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.daily_driver import (
    CATEGORY_WEIGHTS,
    check_answer,
    check_state,
    load_daily_tasks,
    run_daily,
)
from jaros.core import create_decision

DAILY_ROOT = Path(__file__).resolve().parents[1] / "evals" / "daily_driver"

# #EXT-005-REQ-13 Start
# ---------------------------------------------------------------------------
# load_daily_tasks
# ---------------------------------------------------------------------------

def test_load_daily_tasks_loads_seed_dev_tasks():
    # NOTE: the dev/ suite has since grown (more fix/edit/build-module tasks added by
    # later work) — assert the two ORIGINAL seeds are present with the right category,
    # not an exact/closed set (a pre-existing staleness bug fixed in passing; unrelated
    # to build-module routing).
    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    by_id = {t["id"]: t for t in tasks}
    assert {"nav_callers_of_load_config", "edit_clamp_bounds"} <= set(by_id)
    assert by_id["edit_clamp_bounds"]["category"] == "edit"
    assert by_id["nav_callers_of_load_config"]["category"] == "navigate"
    # sorted by (category, id): "edit" < "navigate" alphabetically
    assert tasks.index(by_id["edit_clamp_bounds"]) < tasks.index(by_id["nav_callers_of_load_config"])


def test_load_daily_tasks_default_root_loads_both_seed_tasks():
    tasks = load_daily_tasks()  # default root=evals/daily_driver, both splits
    ids = {t["id"] for t in tasks}
    assert {"nav_callers_of_load_config", "edit_clamp_bounds"} <= ids


def test_load_daily_tasks_tolerates_missing_holdout_dir(tmp_path):
    root = tmp_path / "daily"
    (root / "dev").mkdir(parents=True)
    (root / "dev" / "a.json").write_text(json.dumps({
        "id": "a", "category": "navigate", "split": "dev",
        "instruction": "x", "files": {},
        "oracle": {"type": "answer", "match": "exact", "expect": "ok"},
    }), encoding="utf-8")
    # no holdout/ dir at all — must not raise
    tasks = load_daily_tasks(root=root)
    assert len(tasks) == 1
    assert tasks[0]["id"] == "a"


def test_load_daily_tasks_can_restrict_to_a_single_split(tmp_path):
    root = tmp_path / "daily"
    (root / "dev").mkdir(parents=True)
    (root / "holdout").mkdir(parents=True)
    (root / "dev" / "a.json").write_text(json.dumps({
        "id": "a", "category": "navigate", "split": "dev", "instruction": "x",
        "files": {}, "oracle": {"type": "answer", "match": "exact", "expect": "ok"},
    }), encoding="utf-8")
    (root / "holdout" / "b.json").write_text(json.dumps({
        "id": "b", "category": "navigate", "split": "holdout", "instruction": "y",
        "files": {}, "oracle": {"type": "answer", "match": "exact", "expect": "ok"},
    }), encoding="utf-8")
    dev_only = load_daily_tasks(root=root, split="dev")
    assert [t["id"] for t in dev_only] == ["a"]


# ---------------------------------------------------------------------------
# check_answer — set-match oracle (the navigate seed task)
# ---------------------------------------------------------------------------

def _nav_oracle() -> dict:
    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    nav = next(t for t in tasks if t["category"] == "navigate")
    return nav["oracle"]


def test_check_answer_set_match_true_on_names_plus_connector_word():
    oracle = _nav_oracle()
    assert check_answer("start and reload", oracle) is True


def test_check_answer_set_match_false_when_a_name_is_missing():
    oracle = _nav_oracle()
    assert check_answer("start", oracle) is False


def test_check_answer_set_match_false_when_an_extra_name_is_present():
    oracle = _nav_oracle()
    assert check_answer("start reload helper", oracle) is False


def test_check_answer_exact_match_normalized():
    oracle = {"type": "answer", "match": "exact", "expect": "ok"}
    assert check_answer("  OK  ", oracle) is True
    assert check_answer("nope", oracle) is False


def test_check_answer_regex_match_requires_every_pattern():
    oracle = {"type": "answer", "match": "regex", "expect": [r"line\s*12", r"util\.py"]}
    assert check_answer("see util.py at line 12", oracle) is True
    assert check_answer("see util.py", oracle) is False


def test_check_answer_unknown_match_type_raises():
    with pytest.raises(ValueError):
        check_answer("x", {"type": "answer", "match": "fuzzy", "expect": "x"})


# ---------------------------------------------------------------------------
# check_state — deterministic state oracle (dispatch, no ops seed yet)
# ---------------------------------------------------------------------------

def test_check_state_file_exists(tmp_path):
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    assert check_state(tmp_path, {"check": "file_exists", "path": "marker.txt"}) is True
    assert check_state(tmp_path, {"check": "file_exists", "path": "missing.txt"}) is False


def test_check_state_file_contains(tmp_path):
    (tmp_path / "out.txt").write_text("hello world", encoding="utf-8")
    assert check_state(tmp_path, {"check": "file_contains", "path": "out.txt",
                                  "expect": "world"}) is True
    assert check_state(tmp_path, {"check": "file_contains", "path": "out.txt",
                                  "expect": "nope"}) is False


def test_check_state_unknown_check_type_raises(tmp_path):
    with pytest.raises(ValueError):
        check_state(tmp_path, {"check": "no_such_check"})


# ---------------------------------------------------------------------------
# routing: the edit seed is a pytest-oracle task
# ---------------------------------------------------------------------------

def test_edit_seed_routes_to_pytest_path():
    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    edit = next(t for t in tasks if t["category"] == "edit")
    assert edit.get("test_cmd")
    assert "oracle" not in edit


def test_navigate_seed_routes_to_answer_oracle():
    tasks = load_daily_tasks(root=DAILY_ROOT, split="dev")
    nav = next(t for t in tasks if t["category"] == "navigate")
    assert not nav.get("test_cmd")
    assert nav["oracle"]["type"] == "answer"


# ---------------------------------------------------------------------------
# run_daily — offline: fix_loop faked (no live model), answer_fn injected
# ---------------------------------------------------------------------------

def test_run_daily_scorecard_has_weighted_and_per_category_and_split_fields(monkeypatch):
    from harness.coding_loop import LoopResult

    def _fake_fix_loop(target, instruction, test_cmd, **kwargs):
        return LoopResult(success=True, attempts=1, final_output="faked")

    monkeypatch.setattr("harness.coding_loop.fix_loop", _fake_fix_loop)
    # Isolate the real flywheel store (EXT-027 REQ-3 test hygiene): this test fakes a
    # passing solve, which would otherwise append fixture noise to the real corpus.
    monkeypatch.setattr("harness.daily_driver.record_verified", lambda *a, **kw: None)

    # NOTE: filter to the two ORIGINAL seeds by id — the dev/ suite has since grown
    # (more fix/edit/build-module tasks added by later work); a pre-existing staleness
    # bug fixed in passing, unrelated to build-module routing.
    tasks = [t for t in load_daily_tasks(root=DAILY_ROOT, split="dev")
             if t["id"] in ("nav_callers_of_load_config", "edit_clamp_bounds")]

    def _stub_answer(task: dict) -> str:
        return "start and reload"

    scorecard = run_daily(tasks, answer_fn=_stub_answer, max_iters=2)

    assert scorecard["total"] == 2
    assert scorecard["solved"] == 2
    assert set(scorecard["perCategory"]) == {"edit", "navigate"}
    for cat in ("edit", "navigate"):
        stats = scorecard["perCategory"][cat]
        assert stats == {"passed": 1, "total": 1, "rate": 1.0,
                         "wilson": stats["wilson"]}
        assert 0.0 <= stats["wilson"]["low"] <= stats["rate"] <= stats["wilson"]["high"] <= 1.0
    assert scorecard["weighted"] == pytest.approx(1.0)
    assert scorecard["bySplit"] == {"dev": {"passed": 2, "total": 2, "rate": 1.0}}
    assert CATEGORY_WEIGHTS["navigate"] == 20 and CATEGORY_WEIGHTS["edit"] == 20


def test_run_daily_default_answer_fn_is_an_offline_stub(monkeypatch):
    """No answer_fn given -> the default stub returns "" (no model/CLI call) and the
    navigate task is correctly scored unsolved."""
    from harness.coding_loop import LoopResult

    def _fake_fix_loop(target, instruction, test_cmd, **kwargs):
        return LoopResult(success=False, attempts=1, final_output="faked")

    monkeypatch.setattr("harness.coding_loop.fix_loop", _fake_fix_loop)
    # Isolate the real flywheel store (EXT-027 REQ-3 test hygiene) even though this
    # test's fake solve is unsolved (no capture expected) -- keep it robust to change.
    monkeypatch.setattr("harness.daily_driver.record_verified", lambda *a, **kw: None)

    # NOTE: filter to the two ORIGINAL seeds by id — the dev/ suite has since grown
    # (more fix/edit/build-module tasks added by later work); a pre-existing staleness
    # bug fixed in passing, unrelated to build-module routing. (build-module tasks need
    # their own build_from_intent mock — see the dedicated build-module tests below —
    # so they must not leak into this navigate/edit-only test.)
    tasks = [t for t in load_daily_tasks(root=DAILY_ROOT, split="dev")
             if t["id"] in ("nav_callers_of_load_config", "edit_clamp_bounds")]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["perCategory"]["navigate"]["passed"] == 0
    assert scorecard["perCategory"]["edit"]["passed"] == 0
    assert scorecard["weighted"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# build-module routing (generative build_from_intent + held-out oracle_test)
# ---------------------------------------------------------------------------

# Known-CORRECT solutions for the two build seeds (test data, not model output) — used
# to prove the routing/grading is genuine (a real held-out oracle run), not rubber-stamped.
_KNOWN_SOLUTIONS = {
    "stack.py": (
        "class Stack:\n"
        "    def __init__(self):\n"
        "        self._items = []\n\n"
        "    def push(self, x):\n"
        "        self._items.append(x)\n\n"
        "    def pop(self):\n"
        "        if not self._items:\n"
        "            raise IndexError('empty')\n"
        "        return self._items.pop()\n\n"
        "    def peek(self):\n"
        "        if not self._items:\n"
        "            raise IndexError('empty')\n"
        "        return self._items[-1]\n\n"
        "    def is_empty(self):\n"
        "        return len(self._items) == 0\n\n"
        "    def __len__(self):\n"
        "        return len(self._items)\n"
    ),
    "wf.py": (
        "import re\n\n\n"
        "def word_frequencies(text):\n"
        "    freq = {}\n"
        "    for w in re.findall(r'[A-Za-z]+', text):\n"
        "        w = w.lower()\n"
        "        freq[w] = freq.get(w, 0) + 1\n"
        "    return freq\n"
    ),
}

# A deliberately WRONG "solution" (compiles, some methods missing/broken) used to prove
# the held-out oracle grading is genuine, not rubber-stamped.
_WRONG_STACK = "class Stack:\n    def __init__(self):\n        self._items = []\n"


def _build_seed_tasks():
    return [t for t in load_daily_tasks(root=DAILY_ROOT, split="dev")
            if t["category"] == "build-module"]


class _FakeTestWriter:
    """Stand-in for the real test-writer agent: no model call, just hands back a
    trivially-passing self-test so build_from_intent's fix_loop step has something to
    run against (fix_loop itself is also faked below, so the content is never executed)."""

    def __init__(self, captured: list) -> None:
        self._captured = captured

    def decide(self, payload):
        self._captured.append(dict(payload))
        return [create_decision(
            id="tw-fake", source="test-writer", type="code.write_file",
            payload={"path": payload["test_path"],
                     "content": "def test_placeholder():\n    assert True\n"})]


def _install_offline_build_from_intent(monkeypatch, *, solutions: dict, fix_loop_calls: list,
                                       writer_calls: list):
    """Monkeypatch the two MODEL-FACING touchpoints build_from_intent calls internally
    (the test-writer agent and fix_loop) so the real, unmodified build_from_intent runs
    end-to-end with NO live model call, while its own post-build ``_run_oracle`` step
    still genuinely grades the written solution against the REAL held-out oracle_test.
    """
    from harness.coding_loop import LoopResult

    def _fake_load_agent(filename, llm):
        assert filename == "test_writer_agent.py"
        return _FakeTestWriter(writer_calls)

    def _fake_fix_loop(target, instruction, test_cmd, **kwargs):
        fix_loop_calls.append({"instruction": instruction, "test_cmd": test_cmd, **kwargs})
        name = Path(target).name
        Path(target).write_text(solutions[name], encoding="utf-8")
        return LoopResult(success=True, attempts=1, final_output="known-correct (test fixture)")

    monkeypatch.setattr("harness.intent_loop._load_agent", _fake_load_agent)
    monkeypatch.setattr("harness.intent_loop.build_llm", lambda: None)
    monkeypatch.setattr("harness.intent_loop.fix_loop", _fake_fix_loop)


def test_load_daily_tasks_loads_build_module_seed_tasks():
    build_tasks = _build_seed_tasks()
    assert {t["id"] for t in build_tasks} == {"build_stack", "build_word_freq"}
    for t in build_tasks:
        assert t["category"] == "build-module"
        for field in ("intent", "target", "func", "signature", "test_cmd", "oracle_test"):
            assert field in t and t[field]


def test_build_module_task_not_misrouted_to_the_pytest_path(monkeypatch):
    """Build-module tasks also carry test_cmd (needed for the oracle's own run), but must
    route through the generative build path — never eval_runner.setup_task/fix_loop's
    Task-based pytest path, which would KeyError on the missing 'instruction'/'files'."""
    def _boom(*a, **kw):
        raise AssertionError("build-module task misrouted to eval_runner.setup_task")

    monkeypatch.setattr("harness.eval_runner.setup_task", _boom)

    from harness.intent_loop import IntentResult
    monkeypatch.setattr(
        "harness.intent_loop.build_from_intent",
        lambda task, max_iters=3, verbose=False: IntentResult(task["id"], True, True, 1))
    # Isolate the real flywheel store (EXT-027 REQ-3 test hygiene): this fake solve is
    # solved, which would otherwise append fixture noise to the real corpus.
    monkeypatch.setattr("harness.daily_driver.record_verified", lambda *a, **kw: None)

    tasks = _build_seed_tasks()
    scorecard = run_daily(tasks, max_iters=1)
    assert scorecard["solved"] == len(tasks) == 2


def test_build_module_tasks_route_through_build_from_intent_and_score_by_held_out_oracle(monkeypatch):
    """Offline: real build_from_intent, its two model-facing calls faked to write a
    KNOWN-correct solution (no live model). Proves routing + genuine held-out grading,
    plus the anti-leak invariant: oracle_test content never reaches the model-facing
    calls (test-writer / fix_loop) build_from_intent makes."""
    writer_calls: list = []
    fix_loop_calls: list = []
    _install_offline_build_from_intent(monkeypatch, solutions=_KNOWN_SOLUTIONS,
                                       fix_loop_calls=fix_loop_calls, writer_calls=writer_calls)
    # Isolate the real flywheel store (EXT-027 REQ-3 test hygiene): both build seeds
    # solve here, which would otherwise append fixture noise to the real corpus.
    monkeypatch.setattr("harness.daily_driver.record_verified", lambda *a, **kw: None)

    tasks = _build_seed_tasks()
    scorecard = run_daily(tasks, max_iters=2)

    assert scorecard["total"] == 2
    assert scorecard["solved"] == 2  # the known-correct solutions genuinely pass the oracle
    assert "build-module" in scorecard["perCategory"]
    bm = scorecard["perCategory"]["build-module"]
    assert bm["passed"] == 2 and bm["total"] == 2 and bm["rate"] == 1.0
    assert scorecard["bySplit"]["dev"]["total"] >= 2

    # ANTI-LEAK (Tenet 3): oracle_test content is not in the args passed to the
    # model-facing calls build_from_intent makes (test-writer / fix_loop) — the ONLY
    # place it appears in run_daily's call graph is inside build_from_intent's own
    # separate, post-build, non-model _run_oracle step (proven in test_ext008_intent.py),
    # never in a prompt or in the build dir while building.
    assert writer_calls, "the fake test-writer must have been invoked"
    assert fix_loop_calls, "the fake fix_loop must have been invoked"
    for task in tasks:
        oracle_text = task["oracle_test"]
        for call in writer_calls:
            assert oracle_text not in json.dumps(call)
        for call in fix_loop_calls:
            assert oracle_text not in json.dumps(call)


def test_build_module_task_scored_unsolved_when_the_built_solution_fails_the_oracle(monkeypatch):
    """Proves the grading is a GENUINE held-out check, not rubber-stamped: a wrong/
    incomplete solution scores unsolved."""
    writer_calls: list = []
    fix_loop_calls: list = []
    _install_offline_build_from_intent(
        monkeypatch, solutions={"stack.py": _WRONG_STACK},
        fix_loop_calls=fix_loop_calls, writer_calls=writer_calls)
    # Isolate the real flywheel store (EXT-027 REQ-3 test hygiene) even though this
    # test's fake solve is unsolved (no capture expected) -- keep it robust to change.
    monkeypatch.setattr("harness.daily_driver.record_verified", lambda *a, **kw: None)

    tasks = [t for t in _build_seed_tasks() if t["id"] == "build_stack"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["build-module"]["passed"] == 0
# #EXT-005-REQ-13 End


# ---------------------------------------------------------------------------
# multi-file routing (TASK-4: harness.multi_file.multi_file_fix wired in)
# ---------------------------------------------------------------------------
# #EXT-005-REQ-13 Start

def _multi_file_seed_tasks():
    return [t for t in load_daily_tasks(root=DAILY_ROOT, split="dev")
            if t["category"] == "multi-file"]


def test_load_daily_tasks_loads_multi_file_seed_tasks():
    tasks = _multi_file_seed_tasks()
    assert {t["id"] for t in tasks} == {"mfx_geometry_area", "mfx_cart_discount"}
    for t in tasks:
        assert t["category"] == "multi-file"
        assert t.get("test_cmd")
        assert len(t.get("files", {})) >= 2
        # the failing test lives in a DIFFERENT file than the fault (real cross-file tasks)
        assert any(name.startswith("test") for name in t["files"])


def test_multi_file_task_not_misrouted_to_the_single_file_fix_loop_path(monkeypatch):
    """Multi-file tasks also carry test_cmd (the grader for multi_file_fix's own internal
    run), so without the dedicated branch they would fall into the generic pytest/fix_loop
    branch below -- which builds a Task with no 'target' and can't cross-file-localize."""
    def _boom(*a, **kw):
        raise AssertionError("multi-file task misrouted to the single-file fix_loop path")

    monkeypatch.setattr("harness.coding_loop.fix_loop", _boom)

    def _fake_multi_file_fix(cwd, test_cmd, instruction, test_file, *, max_iters=3, verbose=False):
        return {"solved": True, "file": "geometry.py", "tried": ["geometry.py"], "fixed": ["geometry.py"]}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", _fake_multi_file_fix)
    monkeypatch.setattr("harness.daily_driver.record_verified", lambda *a, **kw: None)

    tasks = _multi_file_seed_tasks()
    scorecard = run_daily(tasks, max_iters=1)
    assert scorecard["solved"] == len(tasks) == 2


def test_multi_file_tasks_route_through_multi_file_fix_and_score_it(monkeypatch):
    """Offline: multi_file_fix faked to a KNOWN result (no live model / no real
    localization+fix run) -- proves run_daily wires the multi-file branch, writes the
    task's files into an isolated dir first, and the weighted/per-category scorecard
    carries a 'multi-file' row."""
    calls: list = []

    def _fake_multi_file_fix(cwd, test_cmd, instruction, test_file, *, max_iters=3, verbose=False):
        calls.append({"cwd": cwd, "test_cmd": test_cmd, "instruction": instruction,
                      "test_file": test_file, "max_iters": max_iters})
        # the task's files must already be materialized in cwd before this is called
        assert (Path(cwd) / Path(test_file).name).is_file()
        return {"solved": True, "file": "geometry.py", "tried": [], "fixed": ["geometry.py"]}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", _fake_multi_file_fix)
    monkeypatch.setattr("harness.daily_driver.record_verified", lambda *a, **kw: None)

    tasks = [t for t in _multi_file_seed_tasks() if t["id"] == "mfx_geometry_area"]
    scorecard = run_daily(tasks, max_iters=2)

    assert scorecard["total"] == 1
    assert scorecard["solved"] == 1
    assert "multi-file" in scorecard["perCategory"]
    mf = scorecard["perCategory"]["multi-file"]
    assert mf == {"passed": 1, "total": 1, "rate": 1.0, "wilson": mf["wilson"]}
    assert scorecard["weighted"] == pytest.approx(1.0)

    assert len(calls) == 1
    assert calls[0]["test_file"].endswith("test_shapes.py")
    assert calls[0]["test_cmd"] == "python -m pytest -q"
    assert calls[0]["max_iters"] == 2


def test_multi_file_task_scored_unsolved_when_multi_file_fix_does_not_reach_green(monkeypatch):
    """Proves the grading is genuine -- an unsolved multi_file_fix result scores unsolved."""
    def _fake_multi_file_fix(cwd, test_cmd, instruction, test_file, *, max_iters=3, verbose=False):
        return {"solved": False, "file": None, "tried": ["geometry.py"], "fixed": []}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", _fake_multi_file_fix)
    monkeypatch.setattr("harness.daily_driver.record_verified", lambda *a, **kw: None)

    tasks = [t for t in _multi_file_seed_tasks() if t["id"] == "mfx_cart_discount"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["multi-file"]["passed"] == 0
# #EXT-005-REQ-13 End


# ---------------------------------------------------------------------------
# refactor routing (TASK-5: two-plane -- model extracts (old,new), the REAL
# harness.refactor.rename_symbol applies it, deterministically graded)
# ---------------------------------------------------------------------------
# #EXT-005-REQ-13 Start

def _refactor_seed_tasks():
    return [t for t in load_daily_tasks(root=DAILY_ROOT, split="dev")
            if t["category"] == "refactor"]


def test_load_daily_tasks_loads_refactor_seed_tasks():
    tasks = _refactor_seed_tasks()
    assert {t["id"] for t in tasks} == {"refactor_calc_total", "refactor_check_stock"}
    for t in tasks:
        assert t["category"] == "refactor"
        assert t.get("test_cmd")
        assert t.get("target")
        assert len(t.get("files", {})) >= 2


def test_refactor_task_not_misrouted_to_the_single_file_fix_loop_path(monkeypatch):
    """Refactor tasks also carry test_cmd (the behavior-preservation grader), so without
    the dedicated branch they would fall into the generic pytest/fix_loop branch below --
    which has no rename-extraction step and no structural oracle."""
    def _boom(*a, **kw):
        raise AssertionError("refactor task misrouted to the single-file fix_loop path")

    monkeypatch.setattr("harness.coding_loop.fix_loop", _boom)
    monkeypatch.setattr(
        "harness.daily_driver._extract_rename",
        lambda instruction: ("_calc", "_compute_total"))

    tasks = [t for t in _refactor_seed_tasks() if t["id"] == "refactor_calc_total"]
    scorecard = run_daily(tasks, max_iters=1)
    assert scorecard["solved"] == 1


def test_refactor_task_applies_the_real_rename_and_scores_it(monkeypatch):
    """OFFLINE: only the model-extraction step is faked (a known (old,new) pair); the REAL
    ``harness.refactor.rename_symbol`` runs deterministically end-to-end. Proves routing,
    a genuine structural rename, AND that the public entry point the test calls (unrelated
    to the renamed internal helper) stays green -- both oracle parts pass."""
    monkeypatch.setattr(
        "harness.daily_driver._extract_rename",
        lambda instruction: ("_calc", "_compute_total"))

    tasks = [t for t in _refactor_seed_tasks() if t["id"] == "refactor_calc_total"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["total"] == 1
    assert scorecard["solved"] == 1
    assert "refactor" in scorecard["perCategory"]
    rf = scorecard["perCategory"]["refactor"]
    assert rf == {"passed": 1, "total": 1, "rate": 1.0, "wilson": rf["wilson"]}


def test_refactor_second_seed_also_solves_with_its_own_pair(monkeypatch):
    monkeypatch.setattr(
        "harness.daily_driver._extract_rename",
        lambda instruction: ("_chk", "_check_stock"))

    tasks = [t for t in _refactor_seed_tasks() if t["id"] == "refactor_check_stock"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 1


def test_refactor_extraction_failure_scores_unsolved_never_crashes(monkeypatch):
    """The model abstains / drifts (no parseable OLD->NEW pair) -> solved=False, no crash."""
    monkeypatch.setattr("harness.daily_driver._extract_rename", lambda instruction: None)

    tasks = [t for t in _refactor_seed_tasks() if t["id"] == "refactor_calc_total"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["refactor"]["passed"] == 0


def test_refactor_no_op_rename_scores_unsolved_two_part_oracle_catches_it(monkeypatch):
    """HONESTY (Tenet 3): the model names a symbol that doesn't exist in the code --
    rename_symbol finds 0 occurrences, the (unchanged) suite stays trivially green, but
    NOTHING was actually renamed. Behavior-only grading would wrongly call this solved;
    the structural half of the two-part oracle must catch it."""
    monkeypatch.setattr(
        "harness.daily_driver._extract_rename",
        lambda instruction: ("_does_not_exist", "_compute_total"))

    tasks = [t for t in _refactor_seed_tasks() if t["id"] == "refactor_calc_total"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["refactor"]["passed"] == 0


def test_extract_rename_degeneracy_guard_rejects_identical_old_and_new():
    from harness.daily_driver import _RENAME_PAIR_RE
    m = _RENAME_PAIR_RE.search("_calc->_calc")
    assert m is not None and m.group(1) == m.group(2)
    # the guard itself lives inside _extract_rename (requires a live/stubbed llm to reach);
    # the regex-level fixture above documents the case the identity check in
    # _extract_rename rejects (old == new) after a successful parse.


def test_extract_rename_returns_none_on_unparseable_reply(monkeypatch):
    """Degeneracy guard: a reply with no OLD->NEW arrow form never crashes -- it is treated
    as extraction failure (None), independent of any live model/network."""
    class _FakeResponse:
        text = "I cannot determine a rename here."

    class _FakeLlm:
        def complete(self, request):
            return _FakeResponse()

    monkeypatch.setattr("harness.coding_loop.build_llm", lambda: _FakeLlm())
    from harness.daily_driver import _extract_rename
    assert _extract_rename("rename the helper") is None
# #EXT-005-REQ-13 End


# ---------------------------------------------------------------------------
# write-tests routing (TASK-6: model generates test content, graded by the
# MUTATION ORACLE -- passes on the reference AND kills every seeded mutant)
# ---------------------------------------------------------------------------
# #EXT-005-REQ-13 Start

def _write_tests_seed_tasks():
    return [t for t in load_daily_tasks(root=DAILY_ROOT, split="dev")
            if t["category"] == "write-tests"]


def test_load_daily_tasks_loads_write_tests_seed_tasks():
    tasks = _write_tests_seed_tasks()
    assert {t["id"] for t in tasks} == {"wt_is_prime", "wt_count_vowels"}
    for t in tasks:
        assert t["category"] == "write-tests"
        assert t.get("test_cmd")
        assert t.get("target", "").startswith("test")
        assert t.get("files")
        assert t.get("mutants")  # every seed carries at least one behavior-changing mutant


def test_write_tests_task_not_misrouted_to_the_single_file_fix_loop_path(monkeypatch):
    """write-tests tasks also carry test_cmd (the mutation-oracle grader), so without the
    dedicated branch they would fall into the generic pytest/fix_loop branch below -- which
    has no test-generation step and no mutation oracle."""
    def _boom(*a, **kw):
        raise AssertionError("write-tests task misrouted to the single-file fix_loop path")

    monkeypatch.setattr("harness.coding_loop.fix_loop", _boom)
    monkeypatch.setattr(
        "harness.daily_driver._generate_tests",
        lambda instruction, files: "def test_placeholder():\n    assert True\n")

    tasks = [t for t in _write_tests_seed_tasks() if t["id"] == "wt_is_prime"]
    scorecard = run_daily(tasks, max_iters=1)
    # routed correctly (no crash from the boomed fix_loop); degenerate test kills no
    # mutant so it is correctly unsolved -- see the dedicated oracle tests below.
    assert scorecard["total"] == 1
    assert "write-tests" in scorecard["perCategory"]


# A KNOWN-GOOD test (test data, not model output) for the is_prime seed: passes the
# reference AND kills BOTH seeded mutants (n%i==0 -> n%i!=0, and range(2,n) -> range(3,n)).
_KNOWN_GOOD_PRIME_TEST = (
    "from primes import is_prime\n\n\n"
    "def test_is_prime():\n"
    "    assert is_prime(2) is True\n"
    "    assert is_prime(3) is True\n"
    "    assert is_prime(7) is True\n"
    "    assert is_prime(4) is False\n"
    "    assert is_prime(1) is False\n"
    "    assert is_prime(0) is False\n"
)

_DEGENERATE_TEST = "def test_degenerate():\n    assert True\n"


def test_write_tests_known_good_test_passes_reference_and_kills_every_mutant(monkeypatch):
    """OFFLINE: the model-generation step is faked to return a KNOWN-GOOD test (real
    behavior, no live model) -- proves the mutation oracle genuinely runs the reference AND
    every seeded mutant, and scores solved=True only when both are satisfied."""
    monkeypatch.setattr(
        "harness.daily_driver._generate_tests",
        lambda instruction, files: _KNOWN_GOOD_PRIME_TEST)

    tasks = [t for t in _write_tests_seed_tasks() if t["id"] == "wt_is_prime"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["total"] == 1
    assert scorecard["solved"] == 1
    assert scorecard["perCategory"]["write-tests"] == {
        "passed": 1, "total": 1, "rate": 1.0,
        "wilson": scorecard["perCategory"]["write-tests"]["wilson"]}


def test_write_tests_degenerate_test_scores_unsolved_mutation_oracle_catches_it(monkeypatch):
    """HONESTY (Tenet 3 -- the whole point): a degenerate ``assert True`` test PASSES on the
    reference code but kills NO mutant. Grading on reference-pass alone would wrongly call
    this solved; the mutation half of the oracle must catch it."""
    monkeypatch.setattr(
        "harness.daily_driver._generate_tests",
        lambda instruction, files: _DEGENERATE_TEST)

    tasks = [t for t in _write_tests_seed_tasks() if t["id"] == "wt_is_prime"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["write-tests"]["passed"] == 0


def test_write_tests_second_seed_also_scores_with_its_own_known_good_test(monkeypatch):
    """The count_vowels seed's two mutants (dropped .lower(), missing 'u') are both killed
    by a test that exercises an uppercase vowel and a 'u' vowel."""
    known_good = (
        "from vowels import count_vowels\n\n\n"
        "def test_count_vowels():\n"
        "    assert count_vowels('Apple') == 2\n"
        "    assert count_vowels('fruit') == 2\n"
        "    assert count_vowels('sky') == 0\n"
    )
    monkeypatch.setattr("harness.daily_driver._generate_tests",
                        lambda instruction, files: known_good)

    tasks = [t for t in _write_tests_seed_tasks() if t["id"] == "wt_count_vowels"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 1


def test_write_tests_no_usable_test_code_scores_unsolved_never_crashes(monkeypatch):
    """The model is unreachable / emits no parseable test code -> solved=False, no crash."""
    monkeypatch.setattr("harness.daily_driver._generate_tests",
                        lambda instruction, files: "")

    tasks = [t for t in _write_tests_seed_tasks() if t["id"] == "wt_is_prime"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["write-tests"]["passed"] == 0


def test_write_tests_prompt_never_shows_the_model_a_mutant_or_reference_test(monkeypatch):
    """ANTI-LEAK (Tenet 3): the prompt built for the model contains only the instruction +
    reference code -- never a mutant's content."""
    from harness.daily_driver import _generate_tests

    captured = {}

    class _FakeResponse:
        text = _KNOWN_GOOD_PRIME_TEST

    class _FakeLlm:
        def complete(self, request):
            captured["prompt"] = request.prompt
            return _FakeResponse()

    monkeypatch.setattr("harness.coding_loop.build_llm", lambda: _FakeLlm())

    tasks = _write_tests_seed_tasks()
    task = next(t for t in tasks if t["id"] == "wt_is_prime")
    _generate_tests(task["instruction"], task["files"])

    assert "prompt" in captured
    for mutant in task["mutants"]:
        assert mutant["content"] not in captured["prompt"]
    assert "n % i == 0" in captured["prompt"]  # the reference code IS shown
# #EXT-005-REQ-13 End


# ---------------------------------------------------------------------------
# write-tests SELF-REPAIR loop (TASK-8: bounded self-repair when the generated tests
# FAIL on the REFERENCE code -- validated by .jaros-data/writetests_repair_probe.py to
# lift a measured miss FAIL->SOLVED; strictly non-degrading, no live model)
# ---------------------------------------------------------------------------
# #EXT-005-REQ-13 Start

_WRONG_ASSERTION_PRIME_TEST = (
    "from primes import is_prime\n\n\n"
    "def test_is_prime():\n"
    "    assert is_prime(2) is True\n"
    "    assert is_prime(4) is True\n"  # WRONG: 4 is not prime -- fails on the reference
    "    assert is_prime(1) is False\n"
)


def test_write_tests_self_repair_fixes_wrong_assertion_and_scores_solved(monkeypatch):
    """OFFLINE (TASK-8): the first generation returns a test with a WRONG assertion that
    FAILS on the reference code; the repair call (fed only the reference-run pytest
    failure -- never the mutant) returns the corrected known-good test. Assert the repair
    loop runs, the corrected tests are graded by the UNCHANGED mutation oracle, and the
    task scores solved=True."""
    repair_calls = []
    monkeypatch.setattr(
        "harness.daily_driver._generate_tests",
        lambda instruction, files: _WRONG_ASSERTION_PRIME_TEST)

    def _fake_repair(modules, tests, failure):
        assert tests == _WRONG_ASSERTION_PRIME_TEST
        assert failure  # fed the reference-run pytest failure output
        repair_calls.append((modules, tests, failure))
        return _KNOWN_GOOD_PRIME_TEST

    monkeypatch.setattr("harness.daily_driver._repair_generated_tests", _fake_repair)

    tasks = [t for t in _write_tests_seed_tasks() if t["id"] == "wt_is_prime"]
    scorecard = run_daily(tasks, max_iters=1)

    assert len(repair_calls) == 1  # one repair call sufficed
    assert scorecard["total"] == 1
    assert scorecard["solved"] == 1
    assert scorecard["perCategory"]["write-tests"]["passed"] == 1


def test_write_tests_self_repair_cannot_fix_stays_unsolved_non_degrading(monkeypatch):
    """OFFLINE (TASK-8): repair is invoked up to max_repair times but never returns a test
    that passes the reference -- the task stays solved=False exactly as it would WITHOUT
    the repair loop (non-degrading), and the loop is BOUNDED (does not call the model
    forever)."""
    repair_calls = []
    monkeypatch.setattr(
        "harness.daily_driver._generate_tests",
        lambda instruction, files: _WRONG_ASSERTION_PRIME_TEST)

    def _fake_repair(modules, tests, failure):
        repair_calls.append(1)
        return _WRONG_ASSERTION_PRIME_TEST  # "fix" that fixes nothing -- still wrong

    monkeypatch.setattr("harness.daily_driver._repair_generated_tests", _fake_repair)

    tasks = [t for t in _write_tests_seed_tasks() if t["id"] == "wt_is_prime"]
    scorecard = run_daily(tasks, max_iters=1)

    assert len(repair_calls) == 2  # bounded at the default max_repair=2, never infinite
    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["write-tests"]["passed"] == 0


def test_write_tests_self_repair_skipped_when_already_passing_reference(monkeypatch):
    """NON-DEGRADING: a task whose generated tests already pass on the reference never
    calls the repair model at all -- repair is pure upside, never extra risk."""
    repair_calls = []
    monkeypatch.setattr(
        "harness.daily_driver._generate_tests",
        lambda instruction, files: _KNOWN_GOOD_PRIME_TEST)
    monkeypatch.setattr(
        "harness.daily_driver._repair_generated_tests",
        lambda *a, **kw: repair_calls.append(1) or _KNOWN_GOOD_PRIME_TEST)

    tasks = [t for t in _write_tests_seed_tasks() if t["id"] == "wt_is_prime"]
    scorecard = run_daily(tasks, max_iters=1)

    assert repair_calls == []
    assert scorecard["solved"] == 1
# #EXT-005-REQ-13 End


# ---------------------------------------------------------------------------
# ops routing (TASK-7: the LAST category, model generates the artifact CONTENT,
# graded by the already-built check_state oracle -> 100/100 weighted coverage)
# ---------------------------------------------------------------------------
# #EXT-005-REQ-13 Start

def _ops_seed_tasks():
    return [t for t in load_daily_tasks(root=DAILY_ROOT, split="dev")
            if t["category"] == "ops"]


def test_load_daily_tasks_loads_ops_seed_tasks():
    tasks = _ops_seed_tasks()
    assert {t["id"] for t in tasks} == {"ops_gitignore", "ops_setup_cfg"}
    for t in tasks:
        assert t["category"] == "ops"
        assert t.get("oracle", {}).get("type") == "state"
        assert not t.get("test_cmd")  # state-oracle, not pytest
        assert len(t["oracle"]["expect"]) >= 2  # MULTI-pattern, not a single trivial echo


_KNOWN_GOOD_GITIGNORE = "__pycache__/\n*.pyc\n.env\n"
_WRONG_GITIGNORE = "*.log\n"


def test_ops_task_no_model_step_scores_unsolved_never_silently_passes(monkeypatch):
    """HONESTY (Tenet 3): the back-compat state-oracle path (write GIVEN files, no model
    step) must NOT silently pass an ops task -- ops tasks carry no pre-given artifact, so
    without the dedicated branch/model step the oracle would just check empty state."""
    monkeypatch.setattr("harness.daily_driver._generate_ops_files", lambda task: {})

    tasks = [t for t in _ops_seed_tasks() if t["id"] == "ops_gitignore"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["total"] == 1
    assert scorecard["solved"] == 0
    assert "ops" in scorecard["perCategory"]
    assert scorecard["perCategory"]["ops"]["passed"] == 0


def test_ops_known_good_artifact_scores_solved(monkeypatch):
    """OFFLINE: the model-generation step is faked to return a KNOWN-GOOD artifact (real
    behavior, no live model) -- proves the file is actually written and check_state grades
    the REAL produced state."""
    monkeypatch.setattr(
        "harness.daily_driver._generate_ops_files",
        lambda task: {task["target"]: _KNOWN_GOOD_GITIGNORE})

    tasks = [t for t in _ops_seed_tasks() if t["id"] == "ops_gitignore"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["total"] == 1
    assert scorecard["solved"] == 1
    assert scorecard["perCategory"]["ops"] == {
        "passed": 1, "total": 1, "rate": 1.0,
        "wilson": scorecard["perCategory"]["ops"]["wilson"]}


def test_ops_wrong_artifact_scores_unsolved(monkeypatch):
    """A wrong artifact (does not contain the required patterns) must fail -- never a
    trivially-echoed single-string pass."""
    monkeypatch.setattr(
        "harness.daily_driver._generate_ops_files",
        lambda task: {task["target"]: _WRONG_GITIGNORE})

    tasks = [t for t in _ops_seed_tasks() if t["id"] == "ops_gitignore"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["ops"]["passed"] == 0


def test_ops_empty_artifact_scores_unsolved_never_crashes(monkeypatch):
    """The model is unreachable / emits nothing usable -> solved=False, no crash."""
    monkeypatch.setattr("harness.daily_driver._generate_ops_files", lambda task: {})

    tasks = [t for t in _ops_seed_tasks() if t["id"] == "ops_setup_cfg"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 0
    assert scorecard["perCategory"]["ops"]["passed"] == 0


def test_ops_second_seed_known_good_setup_cfg_scores_solved(monkeypatch):
    good = "[flake8]\nmax-line-length = 100\n"
    monkeypatch.setattr(
        "harness.daily_driver._generate_ops_files",
        lambda task: {task["target"]: good})

    tasks = [t for t in _ops_seed_tasks() if t["id"] == "ops_setup_cfg"]
    scorecard = run_daily(tasks, max_iters=1)

    assert scorecard["solved"] == 1


def test_ops_generate_files_accepts_a_multi_file_json_map(monkeypatch):
    """The model may also reply with a filename->content JSON map (multi-file ops); the
    generator must honor that map rather than always writing a single ``target`` file."""
    from harness.daily_driver import _generate_ops_files

    class _FakeResponse:
        text = json.dumps({".gitignore": _KNOWN_GOOD_GITIGNORE})

    class _FakeLlm:
        def complete(self, request):
            return _FakeResponse()

    monkeypatch.setattr("harness.coding_loop.build_llm", lambda: _FakeLlm())

    tasks = _ops_seed_tasks()
    task = next(t for t in tasks if t["id"] == "ops_gitignore")
    generated = _generate_ops_files(task)

    assert generated == {".gitignore": _KNOWN_GOOD_GITIGNORE}


def test_ops_prompt_never_leaks_the_oracle_expected_patterns(monkeypatch):
    """ANTI-LEAK (Tenet 3): the prompt built for the model carries only the instruction --
    never the oracle's exact regex/expected content (checked via the regex-escaped forms,
    which never occur in ordinary prose)."""
    from harness.daily_driver import _generate_ops_files

    captured = {}

    class _FakeResponse:
        text = _KNOWN_GOOD_GITIGNORE

    class _FakeLlm:
        def complete(self, request):
            captured["prompt"] = request.prompt
            return _FakeResponse()

    monkeypatch.setattr("harness.coding_loop.build_llm", lambda: _FakeLlm())

    tasks = _ops_seed_tasks()
    task = next(t for t in tasks if t["id"] == "ops_gitignore")
    _generate_ops_files(task)

    assert "prompt" in captured
    # Only the REGEX-ESCAPED patterns (backslash form) are a genuine "leak" signal -- a
    # plain substring like "__pycache__" legitimately also appears in ordinary prose (the
    # instruction itself names the artifacts it wants ignored), so only patterns containing
    # regex metacharacters are checked here.
    for pattern in task["oracle"]["expect"]:
        if "\\" in pattern:
            assert pattern not in captured["prompt"]
    assert json.dumps(task["oracle"]) not in captured["prompt"]  # the raw oracle dict never appears
    assert task["instruction"] in captured["prompt"]  # the instruction IS shown
# #EXT-005-REQ-13 End
