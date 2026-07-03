"""EXT-036 TASK-16: Modification-suite framework + first slice (REQ-21).

OFFLINE -- no live model, no network. ``run_modification_suite`` itself never calls a model
(its whole job is to drive an arbitrary ``modify_fn`` and check the result with an
INDEPENDENT black-box CLI oracle, reusing ``harness.system_suite``'s CLI runner); these tests
use STUB ``modify_fn`` callables that play the role of a real
``harness.system_builder.modify_system`` call, so they prove the suite's plumbing (write
start_system -> modify -> black-box check -> aggregate, never-raise robustness, and -- the
critical case -- the SUITE'S OWN independent regression gate) without needing a live model.
"""

from __future__ import annotations

from pathlib import Path

from harness.modification_suite import FIRST_SLICE, ModificationTask, run_modification_suite

_SUM_CLI = (
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    nums = [int(x) for x in line.split()]\n"
    "    print(sum(nums))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_SUM_CLI_CORRECTLY_ADDS_COUNT = (
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    nums = [int(x) for x in line.split()]\n"
    "    print(sum(nums))\n"
    "    print('COUNT:' + str(len(nums)))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_SUM_CLI_ADDS_COUNT_BUT_BREAKS_SUM = (
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    nums = [int(x) for x in line.split()]\n"
    "    print(sum(nums) + 1)\n"          # BROKEN: off-by-one regression
    "    print('COUNT:' + str(len(nums)))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

ONE_TASK = [ModificationTask(
    name="counter-test", cls="cli-tool", tier="easy",
    start_system={"main.py": _SUM_CLI},
    mod_sentence="also print the count of numbers on a second line",
    new_checks=[([], "1 2 3\n", "COUNT:3")],
    regression_checks=[([], "1 2 3\n", "6")],
)]


def _good_modify_fn(modules, mod_sentence, root):
    """Correctly applies the change: adds the count line, keeps the sum line intact."""
    root = Path(root)
    (root / "main.py").write_text(_SUM_CLI_CORRECTLY_ADDS_COUNT, encoding="utf-8")
    return {"modules": {"main.py": _SUM_CLI_CORRECTLY_ADDS_COUNT}, "applied": True,
            "new_behavior_ok": True, "note": "applied"}


def _regression_breaking_modify_fn(modules, mod_sentence, root):
    """Adds the NEW behavior but silently BREAKS the pre-existing sum output -- and
    (dishonestly, like a naive/ungated modify_fn) reports applied=True anyway. The suite's OWN
    independent oracle must catch this regardless of what the modify_fn itself claims."""
    root = Path(root)
    (root / "main.py").write_text(_SUM_CLI_ADDS_COUNT_BUT_BREAKS_SUM, encoding="utf-8")
    return {"modules": {"main.py": _SUM_CLI_ADDS_COUNT_BUT_BREAKS_SUM}, "applied": True,
            "note": "applied (but actually regressed)"}


def _no_op_modify_fn(modules, mod_sentence, root):
    """Fails to apply the change at all: never touches root, honestly reports applied=False."""
    return {"modules": dict(modules), "applied": False, "note": "could not identify a target"}


def _crashing_modify_fn(modules, mod_sentence, root):
    raise RuntimeError("simulated modify crash")


def _mixed_modify_fn(modules, mod_sentence, root):
    if mod_sentence == "CRASH":
        raise RuntimeError("simulated modify crash")
    return _good_modify_fn(modules, mod_sentence, root)


# --- (a) a correct modification -> accepted=True --------------------------------------------

def test_correct_modification_is_accepted():
    result = run_modification_suite(_good_modify_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["applied"] is True
    assert rec["new_behavior_ok"] is True
    assert rec["no_regression"] is True
    assert rec["accepted"] is True


# --- (b) THE CRITICAL REGRESSION-GATE TEST: new behavior applied but a regression check
# broken -> accepted=False, independent of the modify_fn's own (dishonest) applied=True claim.

def test_regression_breaking_modification_is_not_accepted():
    result = run_modification_suite(_regression_breaking_modify_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["applied"] is True          # the modify_fn itself claimed success
    assert rec["new_behavior_ok"] is True  # the new behavior genuinely does hold
    assert rec["no_regression"] is False   # but the suite's own oracle catches the break
    assert rec["accepted"] is False        # so it is correctly rejected overall


# --- (c) fails to apply -> accepted=False, suite continues ----------------------------------

def test_failed_to_apply_modification_is_not_accepted_no_raise():
    result = run_modification_suite(_no_op_modify_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["applied"] is False
    assert rec["new_behavior_ok"] is False
    assert rec["no_regression"] is True    # nothing changed, so nothing regressed
    assert rec["accepted"] is False


# --- (d) a raising modify_fn -> task records accepted=False, suite continues ----------------

def test_raising_modify_fn_task_continues_and_records_not_accepted():
    result = run_modification_suite(_crashing_modify_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["accepted"] is False
    assert rec["applied"] is False


def test_mixed_modify_fn_one_crashes_suite_continues():
    tasks = [
        ModificationTask(name="crash-task", cls="cli-tool", tier="easy",
                          start_system={"main.py": _SUM_CLI}, mod_sentence="CRASH",
                          new_checks=[([], "1 2\n", "COUNT:2")],
                          regression_checks=[([], "1 2\n", "3")]),
        ModificationTask(name="ok-task", cls="cli-tool", tier="easy",
                          start_system={"main.py": _SUM_CLI},
                          mod_sentence="also print the count",
                          new_checks=[([], "1 2 3\n", "COUNT:3")],
                          regression_checks=[([], "1 2 3\n", "6")]),
    ]
    result = run_modification_suite(_mixed_modify_fn, tasks=tasks)
    assert len(result["results"]) == 2   # the suite continued past the crash
    by_name = {r["name"]: r for r in result["results"]}
    assert by_name["crash-task"]["accepted"] is False
    assert by_name["ok-task"]["accepted"] is True


# --- aggregation: accept/new-behavior/no-regression/applied rates, overall + per tier -------

def test_aggregate_rates_and_per_tier_breakdown():
    tasks = [
        ModificationTask(name="easy-ok", cls="cli-tool", tier="easy",
                          start_system={"main.py": _SUM_CLI}, mod_sentence="also print count",
                          new_checks=[([], "1 2 3\n", "COUNT:3")],
                          regression_checks=[([], "1 2 3\n", "6")]),
        ModificationTask(name="easy-bad", cls="cli-tool", tier="easy", mod_sentence="CRASH",
                          start_system={"main.py": _SUM_CLI},
                          new_checks=[([], "1 2\n", "COUNT:2")],
                          regression_checks=[([], "1 2\n", "3")]),
        ModificationTask(name="hard-ok", cls="cli-tool", tier="hard",
                          start_system={"main.py": _SUM_CLI}, mod_sentence="also print count",
                          new_checks=[([], "4 5\n", "COUNT:2")],
                          regression_checks=[([], "4 5\n", "9")]),
    ]
    result = run_modification_suite(_mixed_modify_fn, tasks=tasks)
    agg = result["aggregate"]
    assert agg["overall"]["n"] == 3
    assert agg["overall"]["accept_rate"] == 2 / 3
    assert agg["by_tier"]["easy"]["n"] == 2
    assert agg["by_tier"]["easy"]["accept_rate"] == 0.5
    assert agg["by_tier"]["hard"]["n"] == 1
    assert agg["by_tier"]["hard"]["accept_rate"] == 1.0


def test_empty_task_list_aggregates_without_raising():
    result = run_modification_suite(_good_modify_fn, tasks=[])
    assert result["results"] == []
    assert result["aggregate"]["overall"]["n"] == 0
    assert result["aggregate"]["overall"]["accept_rate"] == 0.0


# --- (e) the first-slice ModificationTask registry -------------------------------------------

def test_first_slice_registry_shape():
    assert len(FIRST_SLICE) == 10
    tiers = [t.tier for t in FIRST_SLICE]
    assert tiers.count("easy") == 3
    assert tiers.count("medium") == 4
    assert tiers.count("hard") == 3
    names = [t.name for t in FIRST_SLICE]
    assert len(names) == len(set(names))   # unique names
    for task in FIRST_SLICE:
        assert task.tier in ("easy", "medium", "hard")
        assert task.cls and isinstance(task.cls, str)
        assert task.mod_sentence.strip()
        assert task.start_system and "main.py" in task.start_system
        assert 'if __name__ == "__main__"' in task.start_system["main.py"]
        assert task.new_checks   # at least one deterministic new-behavior check
        assert task.regression_checks   # at least one deterministic regression check
        for check in task.new_checks + task.regression_checks:
            assert len(check) == 3


# --- sanity: every first-slice task is internally coherent -- a straightforward correct
# implementation of its own stated mod_sentence satisfies BOTH its new_checks and its
# regression_checks against its OWN start_system, proving the fixtures + checks are not just
# well-shaped but genuinely solvable/verifiable (Tenet 3).

def _correct_modify_fn_for(name: str):
    fixed = {
        "sum-add-count": (
            "import sys\n"
            "def main():\n"
            "    line = sys.stdin.readline()\n"
            "    nums = [int(x) for x in line.split()]\n"
            "    print(sum(nums))\n"
            "    print(len(nums))\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "wordcount-add-charcount": (
            "import sys\n"
            "def main():\n"
            "    text = sys.stdin.read()\n"
            "    print(len(text.split()))\n"
            "    print(len(text))\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "temp-converter-add-kelvin": (
            "import sys\n"
            "def convert(value, from_unit, to_unit):\n"
            "    value = float(value)\n"
            "    if from_unit == 'C' and to_unit == 'F':\n"
            "        return value * 9 / 5 + 32\n"
            "    if from_unit == 'F' and to_unit == 'C':\n"
            "        return (value - 32) * 5 / 9\n"
            "    if to_unit == 'K':\n"
            "        c = value if from_unit == 'C' else (value - 32) * 5 / 9\n"
            "        return c + 273.15\n"
            "    raise ValueError('unsupported')\n"
            "def main():\n"
            "    value, from_unit, to_unit = sys.argv[1], sys.argv[2], sys.argv[3]\n"
            "    print(f'{convert(value, from_unit, to_unit):.2f}')\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "todo-list-add-remove": (
            "import sys\n"
            "def main():\n"
            "    items = []\n"
            "    for line in sys.stdin:\n"
            "        line = line.rstrip('\\n')\n"
            "        if not line:\n"
            "            continue\n"
            "        if line.startswith('add '):\n"
            "            text = line[len('add '):]\n"
            "            items.append(text)\n"
            "            print(f'added {text}')\n"
            "        elif line == 'list':\n"
            "            for i, text in enumerate(items):\n"
            "                print(f'{i}) {text}')\n"
            "        elif line.startswith('remove '):\n"
            "            idx = int(line[len('remove '):])\n"
            "            items.pop(idx)\n"
            "            print(f'removed {idx}')\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "kv-store-add-delete": (
            "import sys\n"
            "def main():\n"
            "    store = {}\n"
            "    for line in sys.stdin:\n"
            "        line = line.rstrip('\\n')\n"
            "        if not line:\n"
            "            continue\n"
            "        parts = line.split(' ', 2)\n"
            "        cmd = parts[0]\n"
            "        if cmd == 'set' and len(parts) == 3:\n"
            "            _, key, value = parts\n"
            "            store[key] = value\n"
            "            print('ok')\n"
            "        elif cmd == 'get' and len(parts) == 2:\n"
            "            _, key = parts\n"
            "            print(store.get(key, 'none'))\n"
            "        elif cmd == 'delete' and len(parts) == 2:\n"
            "            _, key = parts\n"
            "            store.pop(key, None)\n"
            "            print('ok')\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        # --- TASK-20 GROWTH: correct reference modifications for the 5 harder tasks -------
        "sort-asc-to-desc": (
            "import sys\n"
            "def main():\n"
            "    lines = [line.rstrip('\\n') for line in sys.stdin]\n"
            "    for line in sorted(lines, reverse=True):\n"
            "        print(line)\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "keystore-reject-long-keys": (
            "import sys\n"
            "def main():\n"
            "    store = {}\n"
            "    for line in sys.stdin:\n"
            "        line = line.rstrip('\\n')\n"
            "        if not line or '=' not in line:\n"
            "            continue\n"
            "        key, value = line.split('=', 1)\n"
            "        if len(key) > 8:\n"
            "            print('error: key too long: ' + key)\n"
            "            continue\n"
            "        store[key] = value\n"
            "        print('set ' + key)\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "avg-to-median": (
            "import sys\n"
            "def main():\n"
            "    line = sys.stdin.readline()\n"
            "    nums = [float(x) for x in line.split()]\n"
            "    seen = []\n"
            "    for n in nums:\n"
            "        seen.append(n)\n"
            "        s = sorted(seen)\n"
            "        m = len(s)\n"
            "        if m % 2 == 1:\n"
            "            median = s[m // 2]\n"
            "        else:\n"
            "            median = (s[m // 2 - 1] + s[m // 2]) / 2\n"
            "        print(f'{median:.2f}')\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "calc-add-operators": (
            "import sys\n"
            "def main():\n"
            "    a = float(sys.argv[1])\n"
            "    op = sys.argv[2]\n"
            "    b = float(sys.argv[3])\n"
            "    if op == '+':\n"
            "        result = a + b\n"
            "    elif op == '-':\n"
            "        result = a - b\n"
            "    elif op == '*':\n"
            "        result = a * b\n"
            "    elif op == '/':\n"
            "        result = a / b\n"
            "    else:\n"
            "        raise ValueError('unsupported operator: ' + op)\n"
            "    print(f'{result:.2f}')\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "multicmd-add-verbose": (
            "import sys\n"
            "def main():\n"
            "    verbose = '--verbose' in sys.argv[1:]\n"
            "    for line in sys.stdin:\n"
            "        raw = line.rstrip('\\n')\n"
            "        if not raw:\n"
            "            continue\n"
            "        if verbose:\n"
            "            print('LOG: ' + raw)\n"
            "        parts = raw.split()\n"
            "        cmd = parts[0]\n"
            "        if cmd == 'add':\n"
            "            a, b = int(parts[1]), int(parts[2])\n"
            "            print(a + b)\n"
            "        elif cmd == 'mul':\n"
            "            a, b = int(parts[1]), int(parts[2])\n"
            "            print(a * b)\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
    }
    code = fixed[name]

    def _fn(modules, mod_sentence, root):
        (Path(root) / "main.py").write_text(code, encoding="utf-8")
        return {"modules": {"main.py": code}, "applied": True}
    return _fn


def test_first_slice_tasks_are_internally_coherent():
    for task in FIRST_SLICE:
        result = run_modification_suite(_correct_modify_fn_for(task.name), tasks=[task])
        rec = result["results"][0]
        assert rec["accepted"] is True, f"{task.name}: {rec}"


# --- TASK-20: the regression gate must hold on the HARDER (change/tighten/swap) classes too,
# not just the TASK-16 add-a-feature fixture. A modify_fn that correctly adds the NEW
# behavior (* and /) but silently BREAKS an existing operator (+) -- while dishonestly
# self-reporting applied=True -- must still be rejected by the suite's own independent
# oracle, regardless of the modify_fn's own claim.

_CALC_ADD_OPERATORS_BREAKS_PLUS = (
    "import sys\n"
    "def main():\n"
    "    a = float(sys.argv[1])\n"
    "    op = sys.argv[2]\n"
    "    b = float(sys.argv[3])\n"
    "    if op == '+':\n"
    "        result = a + b + 1\n"          # BROKEN: off-by-one regression on '+'
    "    elif op == '-':\n"
    "        result = a - b\n"
    "    elif op == '*':\n"
    "        result = a * b\n"
    "    elif op == '/':\n"
    "        result = a / b\n"
    "    else:\n"
    "        raise ValueError('unsupported operator: ' + op)\n"
    "    print(f'{result:.2f}')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)


def _calc_regression_breaking_modify_fn(modules, mod_sentence, root):
    (Path(root) / "main.py").write_text(_CALC_ADD_OPERATORS_BREAKS_PLUS, encoding="utf-8")
    return {"modules": {"main.py": _CALC_ADD_OPERATORS_BREAKS_PLUS}, "applied": True,
            "note": "applied (but actually regressed '+')"}


def test_harder_task_regression_breaking_modification_is_not_accepted():
    calc_task = next(t for t in FIRST_SLICE if t.name == "calc-add-operators")
    result = run_modification_suite(_calc_regression_breaking_modify_fn, tasks=[calc_task])
    rec = result["results"][0]
    assert rec["applied"] is True          # the modify_fn itself claimed success
    assert rec["new_behavior_ok"] is True  # * and / genuinely work
    assert rec["no_regression"] is False   # but '+' broke, and the oracle catches it
    assert rec["accepted"] is False        # so it is correctly rejected overall
