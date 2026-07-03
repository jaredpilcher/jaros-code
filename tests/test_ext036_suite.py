"""EXT-036 TASK-14: Creation-suite framework + first slice (REQ-20).

OFFLINE -- no live model, no network. ``run_creation_suite`` itself never calls a model (the
suite's whole job is to drive an arbitrary ``build_fn`` and check the result with an INDEPENDENT
black-box CLI oracle); these tests use STUB ``build_fn`` callables that play the role of a real
``harness.system_builder.build_system`` call by writing files directly to ``root``, so they prove
the suite's plumbing (build -> black-box check -> aggregate, never-raise robustness) without
needing a live model.
"""

from __future__ import annotations

from pathlib import Path

from harness.system_suite import CreationTask, FIRST_SLICE, run_creation_suite

SUM_CLI_CODE = (
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    print(sum(int(x) for x in line.split()))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

BROKEN_CLI_CODE = "raise SystemExit(1)\n"

ONE_TASK = [CreationTask(
    name="sum-cli-test", cls="cli-tool", tier="easy",
    sentence="a CLI that sums numbers from stdin",
    checks=[([], "1 2 3\n", "6"), ([], "4 5\n", "9")],
)]


def _good_build_fn(sentence, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(SUM_CLI_CODE, encoding="utf-8")
    return {"modules": {"main.py": SUM_CLI_CODE}, "shipped": True, "done": True,
            "unmet": [], "plan": {"entrypoint": "main.py"}, "note": "DONE"}


def _broken_build_fn(sentence, root):
    """Ships (writes a file, plan names it), but the entrypoint itself is broken -- a real
    non-zero exit on every invocation."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(BROKEN_CLI_CODE, encoding="utf-8")
    return {"modules": {"main.py": BROKEN_CLI_CODE}, "shipped": True, "done": False,
            "unmet": ["x"], "plan": {"entrypoint": "main.py"}, "note": "NOT DONE"}


def _missing_entrypoint_build_fn(sentence, root):
    """The plan CLAIMS an entrypoint that was never actually written to root."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return {"modules": {}, "shipped": True, "done": False, "unmet": [],
            "plan": {"entrypoint": "nope.py"}, "note": "shipped but entrypoint missing"}


def _mixed_build_fn(sentence, root):
    """Raises for a sentinel sentence, otherwise delegates to the good stub -- lets a single
    build_fn drive a mix of crashing/succeeding tasks in one suite run."""
    if sentence == "CRASH":
        raise RuntimeError("simulated build crash")
    return _good_build_fn(sentence, root)


# --- (b) a passing stub system -> accepted=True --------------------------------------------

def test_passing_stub_system_is_accepted():
    result = run_creation_suite(_good_build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["shipped"] is True
    assert rec["accepted"] is True
    assert rec["n_checks_passed"] == 2
    assert rec["n_checks"] == 2


# --- (c) broken / missing-entrypoint stub -> accepted=False, suite does NOT raise ----------

def test_broken_entrypoint_stub_not_accepted_no_raise():
    result = run_creation_suite(_broken_build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["shipped"] is True          # the build itself reported shipped
    assert rec["accepted"] is False        # but the independent oracle catches the broken CLI
    assert rec["n_checks_passed"] == 0


def test_missing_entrypoint_stub_not_accepted_no_raise():
    result = run_creation_suite(_missing_entrypoint_build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["accepted"] is False
    assert rec["n_checks_passed"] == 0


def test_no_plan_never_accepted_no_raise():
    def build_fn(sentence, root):
        return {"modules": {}, "shipped": False, "done": False, "unmet": [],
                "plan": None, "note": "no plan"}
    result = run_creation_suite(build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["shipped"] is False
    assert rec["accepted"] is False


def test_build_fn_returns_non_dict_never_raises():
    def build_fn(sentence, root):
        return None
    result = run_creation_suite(build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["accepted"] is False
    assert rec["shipped"] is False


# --- (d) a build_fn that raises for a task -> accepted=False, suite continues --------------

def test_build_fn_raises_task_continues_and_records_not_accepted():
    tasks = [
        CreationTask(name="crash-task", cls="cli-tool", tier="easy", sentence="CRASH",
                     checks=[([], "1 2\n", "3")]),
        CreationTask(name="ok-task", cls="cli-tool", tier="easy",
                     sentence="a CLI that sums numbers from stdin",
                     checks=[([], "1 2 3\n", "6")]),
    ]
    result = run_creation_suite(_mixed_build_fn, tasks=tasks)
    assert len(result["results"]) == 2   # the suite continued past the crash
    by_name = {r["name"]: r for r in result["results"]}
    assert by_name["crash-task"]["accepted"] is False
    assert by_name["ok-task"]["accepted"] is True


# --- (a) aggregation: accept-rate + per-tier breakdown --------------------------------------

def test_aggregate_accept_rate_and_per_tier_breakdown():
    tasks = [
        CreationTask(name="easy-ok", cls="cli-tool", tier="easy",
                     sentence="a CLI that sums numbers from stdin",
                     checks=[([], "1 2 3\n", "6")]),
        CreationTask(name="easy-bad", cls="cli-tool", tier="easy", sentence="CRASH",
                     checks=[([], "1 2\n", "3")]),
        CreationTask(name="hard-ok", cls="cli-tool", tier="hard",
                     sentence="a CLI that sums numbers from stdin",
                     checks=[([], "10 20\n", "30")]),
    ]
    result = run_creation_suite(_mixed_build_fn, tasks=tasks)
    agg = result["aggregate"]
    assert agg["overall"]["n"] == 3
    assert agg["overall"]["accept_rate"] == 2 / 3
    assert agg["overall"]["ship_rate"] == 2 / 3
    assert agg["by_tier"]["easy"]["n"] == 2
    assert agg["by_tier"]["easy"]["accept_rate"] == 0.5
    assert agg["by_tier"]["hard"]["n"] == 1
    assert agg["by_tier"]["hard"]["accept_rate"] == 1.0


def test_empty_task_list_aggregates_without_raising():
    result = run_creation_suite(_good_build_fn, tasks=[])
    assert result["results"] == []
    assert result["aggregate"]["overall"]["n"] == 0
    assert result["aggregate"]["overall"]["accept_rate"] == 0.0


# --- callable check support (the non-CLI escape hatch) -------------------------------------

def test_callable_check_supported():
    def _entrypoint_exists(root, plan):
        return (Path(root) / "main.py").is_file()

    tasks = [CreationTask(name="callable-task", cls="cli-tool", tier="easy",
                           sentence="a CLI that sums numbers from stdin",
                           checks=[_entrypoint_exists])]
    result = run_creation_suite(_good_build_fn, tasks=tasks)
    assert result["results"][0]["accepted"] is True


def test_callable_check_failure_not_accepted_no_raise():
    def _always_false(root, plan):
        return False

    tasks = [CreationTask(name="callable-task-2", cls="cli-tool", tier="easy",
                           sentence="a CLI that sums numbers from stdin",
                           checks=[_always_false])]
    result = run_creation_suite(_good_build_fn, tasks=tasks)
    assert result["results"][0]["accepted"] is False


# --- (e) the first-slice CreationTask registry ----------------------------------------------

def test_first_slice_registry_shape():
    assert len(FIRST_SLICE) == 6
    tiers = [t.tier for t in FIRST_SLICE]
    assert tiers.count("easy") == 2
    assert tiers.count("medium") == 2
    assert tiers.count("hard") == 2
    names = [t.name for t in FIRST_SLICE]
    assert len(names) == len(set(names))   # unique names
    for task in FIRST_SLICE:
        assert task.tier in ("easy", "medium", "hard")
        assert task.cls and isinstance(task.cls, str)
        assert task.sentence.strip()
        assert task.checks   # every task has at least one deterministic check
        for check in task.checks:
            assert callable(check) or len(check) == 3


def test_first_slice_actually_runs_offline_with_real_stub_entrypoint():
    """Sanity: at least one real first-slice task (sum-cli) is satisfied by a straightforward
    correct implementation of its own stated CLI contract -- proves the checks are internally
    coherent with the sentence they describe, not just well-formed."""
    sum_task = next(t for t in FIRST_SLICE if t.name == "sum-cli")

    def build_fn(sentence, root):
        return _good_build_fn(sentence, root)

    result = run_creation_suite(build_fn, tasks=[sum_task])
    assert result["results"][0]["accepted"] is True
