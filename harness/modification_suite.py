"""EXT-036 TASK-16: Modification-suite framework + first slice (REQ-21).

REQ-21 needs the harder, more realistic parity instrument: MODIFYING an existing working
system from a one-sentence change, isolated from the CREATION capability (REQ-20,
``harness/system_suite.py``) by starting each task from a FIXED, known-good ``start_system``
(a small hand-written fixture) instead of a model-built one. This mirrors real dev work
(most editing is on an existing codebase, not greenfield) and is the natural pairing of
REQ-14's ``harness.system_builder.modify_system``.

Two-plane split (identical shape to ``system_suite.py``): this module is entirely
DETERMINISTIC (no model call anywhere) -- it writes a task's ``start_system`` onto a fresh
temp root, drives an arbitrary ``modify_fn`` (which may itself call a model), then checks the
result with an INDEPENDENT black-box CLI oracle. The oracle is REUSED verbatim from
``harness/system_suite.py`` (``_run_single_check``/``_run_cli``/``_resolve_entry``) rather
than duplicated -- one shared CLI-execution mechanism for both suites.

The regression gate is the honesty core (Tenet 3): ``accepted`` requires BOTH the new
behavior to hold (``new_behavior_ok``) AND nothing previously-working to have broken
(``no_regression``) -- checked by this suite's OWN independent oracle, never by trusting a
``modify_fn``'s self-reported ``applied`` flag (a modify_fn could optimistically claim
``applied=True`` while having silently broken something; the suite catches that regardless).

``run_modification_suite`` NEVER raises overall: any per-task failure (a ``modify_fn``
exception, a missing/broken entrypoint, a check that errors or times out) is recorded as that
task's honest ``accepted=False`` and the suite moves on to the next task.

Live gemma-vs-escalating-system measurement against this suite, and growing the change-class
coverage beyond this first slice, are explicit OUT-OF-SCOPE follow-ups for this task -- this
module only builds the framework + a first concrete slice (2 easy / 2 medium / 1 hard).
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from harness.system_suite import _run_single_check

# #EXT-036-REQ-21 Start


@dataclass
class ModificationTask:
    """One held-out sentence->system MODIFICATION task (REQ-21). ``start_system`` is a small,
    hand-written KNOWN-GOOD system (``{filename: code}``, always with a ``main.py`` entrypoint
    containing an ``if __name__ == "__main__":`` block -- the same single-file CLI convention
    ``harness/system_suite.py``'s ``FIRST_SLICE`` uses) that is written onto a fresh temp root
    BEFORE the modification is attempted, so the task measures editing a FIXED known-good
    system, never a model-built one (isolating modification from creation capability).

    ``new_checks``/``regression_checks`` are each a list of ``(argv, stdin,
    expected_substring)`` black-box CLI checks, run against ``root``'s resolved entrypoint
    (``main.py``) exactly like ``system_suite.CreationTask.checks`` -- ``new_checks`` verify
    the requested change now holds, ``regression_checks`` verify the PRE-EXISTING behavior the
    modification must not break. No check ever depends on wall-clock timing."""

    name: str
    cls: str
    tier: str                 # "easy" | "medium" | "hard"
    start_system: dict
    mod_sentence: str
    new_checks: list = field(default_factory=list)
    regression_checks: list = field(default_factory=list)


def _rates(results: "list[dict]") -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0, "accept_rate": 0.0, "new_behavior_rate": 0.0,
                "no_regression_rate": 0.0, "applied_rate": 0.0}
    return {
        "n": n,
        "accept_rate": sum(1 for r in results if r["accepted"]) / n,
        "new_behavior_rate": sum(1 for r in results if r["new_behavior_ok"]) / n,
        "no_regression_rate": sum(1 for r in results if r["no_regression"]) / n,
        "applied_rate": sum(1 for r in results if r["applied"]) / n,
    }


def _aggregate(results: "list[dict]") -> dict:
    agg = {"overall": _rates(results)}
    tiers = sorted({r["tier"] for r in results})
    agg["by_tier"] = {t: _rates([r for r in results if r["tier"] == t]) for t in tiers}
    return agg


def run_modification_suite(modify_fn: Callable, tasks: "list[ModificationTask] | None" = None,
                            python_exe: "str | None" = None) -> dict:
    """Run the MODIFICATION suite: for each task, write ``task.start_system`` onto a fresh
    isolated temp root, then call ``modify_fn(modules, mod_sentence, root)`` (same positional
    signature as ``harness.system_builder.modify_system(modules, mod_sentence, root, *,
    llm=...)`` -- callers pass a partial/wrapper binding ``llm`` so this suite stays
    model-agnostic and fully offline-testable). ``modify_fn`` is expected to leave ``root``
    reflecting the FINAL system state (assembling any change onto disk itself, mirroring
    ``modify_system``'s own behavior) -- this suite never re-writes files from a returned
    ``modules`` dict, so a ``modify_fn`` that reports success without touching ``root`` is
    honestly caught by the oracle below, not silently trusted.

    Then runs the INDEPENDENT black-box CLI oracle (REUSING
    ``harness.system_suite._run_single_check`` -- one shared mechanism for both suites) against
    the resulting ``root``: every ``new_check`` (does the requested change now hold?) and every
    ``regression_check`` (does the pre-existing behavior still hold?). Records per task
    ``{name, cls, tier, applied, new_behavior_ok, no_regression, accepted}`` where
    ``new_behavior_ok`` requires ALL ``new_checks`` to pass, ``no_regression`` requires ALL
    ``regression_checks`` to still pass, and ``accepted`` requires BOTH -- independent of
    whatever ``modify_fn`` itself reported (the regression gate is enforced by THIS suite, the
    honest oracle, not by trusting the thing under test).

    Returns ``{"results": [...], "aggregate": {"overall": {...}, "by_tier": {...}}}`` with
    accept-rate / new-behavior-rate / no-regression-rate (+ applied-rate), overall and per tier.

    NEVER raises: any per-task failure (a ``modify_fn`` exception, a broken/missing entrypoint,
    a hung/failing check) is recorded as that task's ``accepted=False`` and the suite continues
    to the next task -- one bad task can never abort the whole measurement run."""
    tasks = FIRST_SLICE if tasks is None else tasks
    python_exe = python_exe or sys.executable or "python"
    results: "list[dict]" = []
    for task in tasks:
        rec = {"name": task.name, "cls": task.cls, "tier": task.tier,
               "applied": False, "new_behavior_ok": False, "no_regression": False,
               "accepted": False}
        try:
            with tempfile.TemporaryDirectory(prefix="s2s_modsuite_") as tmp:
                root = Path(tmp)
                for fname, code in (task.start_system or {}).items():
                    (root / fname).write_text(code, encoding="utf-8", newline="\n")
                modules = dict(task.start_system or {})
                result = modify_fn(modules, task.mod_sentence, root)
                if isinstance(result, dict):
                    rec["applied"] = bool(result.get("applied"))

                new_checks = task.new_checks or []
                reg_checks = task.regression_checks or []
                n_new_pass = sum(1 for c in new_checks if _run_single_check(c, root, None, python_exe))
                n_reg_pass = sum(1 for c in reg_checks if _run_single_check(c, root, None, python_exe))
                rec["new_behavior_ok"] = bool(new_checks) and n_new_pass == len(new_checks)
                rec["no_regression"] = n_reg_pass == len(reg_checks)
                rec["accepted"] = rec["new_behavior_ok"] and rec["no_regression"]
        except Exception:
            pass   # a modify/exec failure -> the default rec (accepted=False) stands
        results.append(rec)

    return {"results": results, "aggregate": _aggregate(results)}


# --- FIRST SLICE (2 easy / 2 medium / 1 hard) -----------------------------------------------
# Each start_system is a small, genuinely-correct, hand-written known-good CLI (never
# model-built) so a modification task measures EDITING, isolated from creation. Every
# mod_sentence + its checks were hand-verified for internal coherence: a straightforward
# correct implementation of the change satisfies new_checks, and the start_system's existing
# behavior (unmodified) already satisfies regression_checks. No check depends on wall-clock
# timing.

_SUM_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    nums = [int(x) for x in line.split()]\n"
    "    print(sum(nums))\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_WORDCOUNT_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    text = sys.stdin.read()\n"
    "    print(len(text.split()))\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_TEMP_CONVERTER_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def convert(value, from_unit, to_unit):\n"
    "    value = float(value)\n"
    "    if from_unit == \"C\" and to_unit == \"F\":\n"
    "        return value * 9 / 5 + 32\n"
    "    if from_unit == \"F\" and to_unit == \"C\":\n"
    "        return (value - 32) * 5 / 9\n"
    "    raise ValueError(f\"unsupported conversion: {from_unit} -> {to_unit}\")\n"
    "\n"
    "\n"
    "def main():\n"
    "    value, from_unit, to_unit = sys.argv[1], sys.argv[2], sys.argv[3]\n"
    "    print(f\"{convert(value, from_unit, to_unit):.2f}\")\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_TODO_LIST_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    items = []\n"
    "    for line in sys.stdin:\n"
    "        line = line.rstrip(\"\\n\")\n"
    "        if not line:\n"
    "            continue\n"
    "        if line.startswith(\"add \"):\n"
    "            text = line[len(\"add \"):]\n"
    "            items.append(text)\n"
    "            print(f\"added {text}\")\n"
    "        elif line == \"list\":\n"
    "            for i, text in enumerate(items):\n"
    "                print(f\"{i}) {text}\")\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_KV_STORE_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    store = {}\n"
    "    for line in sys.stdin:\n"
    "        line = line.rstrip(\"\\n\")\n"
    "        if not line:\n"
    "            continue\n"
    "        parts = line.split(\" \", 2)\n"
    "        cmd = parts[0]\n"
    "        if cmd == \"set\" and len(parts) == 3:\n"
    "            _, key, value = parts\n"
    "            store[key] = value\n"
    "            print(\"ok\")\n"
    "        elif cmd == \"get\" and len(parts) == 2:\n"
    "            _, key = parts\n"
    "            print(store.get(key, \"none\"))\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

FIRST_SLICE: "list[ModificationTask]" = [
    ModificationTask(
        name="sum-add-count", cls="cli-tool", tier="easy",
        start_system={"main.py": _SUM_CLI},
        mod_sentence=(
            "The program in main.py reads one line of whitespace-separated integers from "
            "standard input and prints their sum. Also print the COUNT of how many numbers "
            "were read, as a second line printed immediately after the sum line. Keep the sum "
            "line's exact existing format unchanged."
        ),
        new_checks=[
            ([], "1 2 3 10\n", "4"),     # sum=16, count=4 ("4" not a substring of "16")
            ([], "5 5\n", "2"),          # sum=10, count=2 ("2" not a substring of "10")
        ],
        regression_checks=[
            ([], "1 2 3 10\n", "16"),
            ([], "5 5\n", "10"),
        ],
    ),
    ModificationTask(
        name="wordcount-add-charcount", cls="cli-tool", tier="easy",
        start_system={"main.py": _WORDCOUNT_CLI},
        mod_sentence=(
            "The program in main.py reads all text from standard input and prints the number "
            "of whitespace-separated words. Also print the total number of characters in the "
            "input (including all whitespace and newlines), as a second line printed "
            "immediately after the word-count line. Keep the word-count line's exact existing "
            "format unchanged."
        ),
        new_checks=[
            ([], "one two three\n", "14"),          # 14 chars, 3 words
            ([], "hello world foo bar\n", "20"),     # 20 chars, 4 words
        ],
        regression_checks=[
            ([], "one two three\n", "3"),
            ([], "hello world foo bar\n", "4"),
        ],
    ),
    ModificationTask(
        name="temp-converter-add-kelvin", cls="cli-tool", tier="medium",
        start_system={"main.py": _TEMP_CONVERTER_CLI},
        mod_sentence=(
            "The program in main.py is run as `python main.py <value> <from_unit> <to_unit>` "
            "and currently only supports converting between Celsius (C) and Fahrenheit (F). "
            "Add support for converting to Kelvin (K) as the target unit: from Celsius, "
            "K = C + 273.15; from Fahrenheit, first convert to Celsius then add 273.15. Keep "
            "printing the result rounded to exactly 2 decimal places, and keep the existing "
            "C<->F conversions unchanged."
        ),
        new_checks=[
            (["0", "C", "K"], None, "273.15"),
            (["100", "C", "K"], None, "373.15"),
        ],
        regression_checks=[
            (["0", "C", "F"], None, "32.00"),
            (["100", "C", "F"], None, "212.00"),
        ],
    ),
    ModificationTask(
        name="todo-list-add-remove", cls="todo-list", tier="medium",
        start_system={"main.py": _TODO_LIST_CLI},
        mod_sentence=(
            "The program in main.py is an in-memory todo list reading commands from standard "
            "input (`add <text>` prints `added <text>`; `list` prints one line per item as "
            "`<index>) <text>`). Add a `remove <index>` command: it removes the item currently "
            "at that integer index and prints `removed <index>`. Keep the existing `add` and "
            "`list` commands and their output formats exactly unchanged."
        ),
        new_checks=[
            ([], "add buy milk\nadd walk dog\nremove 0\nlist\n", "0) walk dog"),
            ([], "add buy milk\nremove 0\n", "removed 0"),
        ],
        regression_checks=[
            ([], "add buy milk\nlist\n", "added buy milk"),
            ([], "add buy milk\nadd walk dog\nlist\n", "1) walk dog"),
        ],
    ),
    ModificationTask(
        name="kv-store-add-delete", cls="kv-store", tier="hard",
        start_system={"main.py": _KV_STORE_CLI},
        mod_sentence=(
            "The program in main.py is an in-memory key-value store reading commands from "
            "standard input (`set <key> <value>` prints `ok`; `get <key>` prints the stored "
            "value or `none` if absent). Add a `delete <key>` command that removes the key if "
            "present and prints `ok` (print `ok` even if the key was already absent). Keep the "
            "existing `set` and `get` commands and their output formats exactly unchanged."
        ),
        new_checks=[
            ([], "set a 1\ndelete a\nget a\n", "none"),
            ([], "delete missing\n", "ok"),
        ],
        regression_checks=[
            ([], "set a 1\nget a\n", "1"),
            ([], "get missing\n", "none"),
        ],
    ),
]
# #EXT-036-REQ-21 End
