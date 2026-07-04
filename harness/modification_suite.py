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

TASK-22 GROWTH (2026-07-03): ``MULTIFILE_SLICE`` grows the suite with a MULTI-FILE modification
tier -- ``FIRST_SLICE`` is entirely single-file (``main.py``-only) and gemma aces it 10/10
(saturated per PRIME-001's ratchet); multi-file modification (editing a helper module, or
editing ``main.py``'s wiring to a helper module, while a resolved-entrypoint CLI oracle checks
the whole system) is the measured next frontier and is now part of the held-out instrument.
``ALL_TASKS = FIRST_SLICE + MULTIFILE_SLICE`` is provided for callers that want the fuller set;
``run_modification_suite``'s default ``tasks=FIRST_SLICE`` is unchanged for backward
compatibility.
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
    containing an ``if __name__ == "__main__":`` block) that is written onto a fresh temp root
    BEFORE the modification is attempted, so the task measures editing a FIXED known-good
    system, never a model-built one (isolating modification from creation capability).
    ``start_system`` MAY contain more than one module (e.g. ``statlib.py`` + ``main.py``) --
    ``run_modification_suite`` writes every file in ``start_system`` onto the temp root before
    running ``modify_fn``, so multi-file systems work at the framework level unchanged; the
    CLI oracle always resolves and runs ``main.py`` as the single entrypoint regardless of how
    many supporting modules exist alongside it (see ``MULTIFILE_SLICE`` below).

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

# --- TASK-20 GROWTH (2026-07-03): +5 HARDER change classes ---------------------------------
# The TASK-16 first slice above is all simple ADD-a-feature edits (append a line, add a
# target unit, add a subcommand). PRIME-001's ratchet: an eval suite the harness can ace is
# too easy and must be made harder to stay informative. These 5 tasks instead exercise
# CHANGE/REPLACE/TIGHTEN classes -- the model must understand + precisely edit EXISTING
# logic, not just append. Each start_system is genuinely correct and verifiably passes its
# own regression_checks BEFORE any modification (Tenet 3). No check depends on wall-clock
# timing.

_SORT_ASC_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    lines = [line.rstrip(\"\\n\") for line in sys.stdin]\n"
    "    for line in sorted(lines):\n"
    "        print(line)\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_KEYSTORE_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    store = {}\n"
    "    for line in sys.stdin:\n"
    "        line = line.rstrip(\"\\n\")\n"
    "        if not line or \"=\" not in line:\n"
    "            continue\n"
    "        key, value = line.split(\"=\", 1)\n"
    "        store[key] = value\n"
    "        print(f\"set {key}\")\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_RUNNING_AVG_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    nums = [float(x) for x in line.split()]\n"
    "    total = 0.0\n"
    "    for i, n in enumerate(nums, start=1):\n"
    "        total += n\n"
    "        avg = total / i\n"
    "        print(f\"{avg:.2f}\")\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_CALC_ADD_SUB_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    a = float(sys.argv[1])\n"
    "    op = sys.argv[2]\n"
    "    b = float(sys.argv[3])\n"
    "    if op == \"+\":\n"
    "        result = a + b\n"
    "    elif op == \"-\":\n"
    "        result = a - b\n"
    "    else:\n"
    "        raise ValueError(f\"unsupported operator: {op}\")\n"
    "    print(f\"{result:.2f}\")\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_MULTICMD_CLI = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    for line in sys.stdin:\n"
    "        line = line.rstrip(\"\\n\")\n"
    "        if not line:\n"
    "            continue\n"
    "        parts = line.split()\n"
    "        cmd = parts[0]\n"
    "        if cmd == \"add\":\n"
    "            a, b = int(parts[1]), int(parts[2])\n"
    "            print(a + b)\n"
    "        elif cmd == \"mul\":\n"
    "            a, b = int(parts[1]), int(parts[2])\n"
    "            print(a * b)\n"
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

    # --- TASK-20 GROWTH: harder CHANGE classes (behavior change / constraint tightening /
    # algorithm swap / branch addition / cross-cutting), not just ADD-a-feature.

    ModificationTask(
        name="sort-asc-to-desc", cls="sort-cli", tier="medium",
        start_system={"main.py": _SORT_ASC_CLI},
        mod_sentence=(
            "The program in main.py reads lines from standard input until EOF and prints "
            "them sorted in ASCENDING alphabetical order, one per line. Change it to sort "
            "in DESCENDING alphabetical order instead. Keep reading all lines from standard "
            "input exactly as before, including the case of empty input (in which case it "
            "must still exit successfully and print nothing)."
        ),
        new_checks=[
            ([], "banana\napple\ncherry\n", "cherry\nbanana\napple"),
            ([], "b\na\nc\n", "c\nb\na"),
        ],
        regression_checks=[
            ([], "onlyone\n", "onlyone"),
            ([], "", ""),
        ],
    ),
    ModificationTask(
        name="keystore-reject-long-keys", cls="kv-store", tier="medium",
        start_system={"main.py": _KEYSTORE_CLI},
        mod_sentence=(
            "The program in main.py reads lines of the form key=value from standard input "
            "and, for each valid line, stores the value under the key and prints `set "
            "<key>`. Add validation: if a key is LONGER than 8 characters, REJECT it -- do "
            "not store it, and instead print `error: key too long: <key>`. Keys of 8 "
            "characters or fewer must continue to be accepted and stored exactly as before."
        ),
        new_checks=[
            ([], "averylongkey=1\n", "error: key too long: averylongkey"),
            ([], "123456789=x\n", "error: key too long: 123456789"),
        ],
        regression_checks=[
            ([], "short=1\n", "set short"),
            ([], "abcdefgh=1\n", "set abcdefgh"),
        ],
    ),
    ModificationTask(
        name="avg-to-median", cls="stats-cli", tier="hard",
        start_system={"main.py": _RUNNING_AVG_CLI},
        mod_sentence=(
            "The program in main.py reads one line of whitespace-separated numbers from "
            "standard input and, after each number is read (in the order given), prints "
            "the RUNNING AVERAGE of all numbers seen so far, formatted to exactly 2 decimal "
            "places, one line per number. Change it to print the RUNNING MEDIAN of all "
            "numbers seen so far instead (for an even count, the median is the average of "
            "the two middle values when the numbers seen so far are sorted). Keep "
            "everything else about the CLI unchanged: still one result per line, in the "
            "same order the numbers were read, formatted to exactly 2 decimal places."
        ),
        new_checks=[
            ([], "1 2 3 10\n", "2.50"),
            ([], "10 1 2 3\n", "2.00"),
        ],
        regression_checks=[
            ([], "5\n", "5.00"),
            ([], "4 4 4\n", "4.00\n4.00\n4.00"),
        ],
    ),
    ModificationTask(
        name="calc-add-operators", cls="calculator", tier="easy",
        start_system={"main.py": _CALC_ADD_SUB_CLI},
        mod_sentence=(
            "The program in main.py is run as `python main.py <num1> <op> <num2>` and "
            "currently supports the operators + and -, printing the result rounded to "
            "exactly 2 decimal places. Add support for the operators * (multiplication) "
            "and / (ordinary floating-point division). Keep the existing + and - behavior "
            "and output format exactly unchanged."
        ),
        new_checks=[
            (["2", "*", "3"], None, "6.00"),
            (["6", "/", "2"], None, "3.00"),
        ],
        regression_checks=[
            (["2", "+", "3"], None, "5.00"),
            (["5", "-", "3"], None, "2.00"),
        ],
    ),
    ModificationTask(
        name="multicmd-add-verbose", cls="multi-command-cli", tier="hard",
        start_system={"main.py": _MULTICMD_CLI},
        mod_sentence=(
            "The program in main.py is run as `python main.py` and reads commands from "
            "standard input, one per line: `add <x> <y>` prints the sum, `mul <x> <y>` "
            "prints the product. Add support for an optional `--verbose` command-line "
            "flag: when run as `python main.py --verbose`, for EVERY command processed, "
            "ALSO print a log line immediately BEFORE that command's normal output, in the "
            "exact format `LOG: <command line>` (echoing the raw command line that was "
            "read). When run WITHOUT `--verbose` (`python main.py`, the default), the "
            "output must remain EXACTLY as it is today -- no log lines, byte-identical to "
            "the current default behavior."
        ),
        new_checks=[
            (["--verbose"], "add 2 3\n", "LOG: add 2 3\n5"),
            (["--verbose"], "mul 2 3\nadd 1 1\n", "LOG: mul 2 3\n6\nLOG: add 1 1\n2"),
        ],
        regression_checks=[
            ([], "add 2 3\n", "5"),
            ([], "add 1 1\nmul 2 2\nadd 3 3\n", "2\n4\n6"),
        ],
    ),
]


# --- MULTIFILE_SLICE (2026-07-03): MULTI-FILE modification tier -----------------------------
# FIRST_SLICE above is entirely single-file (``main.py`` only) and gemma aces it 10/10
# (saturated); real editing work is often on a system with a helper module IMPORTED by
# main.py, and the correct change may live in the helper, in main.py's wiring, or both. Each
# start_system here is a genuinely-correct, hand-written multi-file fixture (>= 2 modules,
# always with ``main.py`` as the resolved CLI entrypoint) that verifiably passes its own
# regression_checks BEFORE any modification (Tenet 3). No check depends on wall-clock timing.

_STATLIB_MEAN = (
    '"""Small stats helpers."""\n'
    "\n"
    "def mean(nums):\n"
    "    return sum(nums) / len(nums) if nums else 0\n"
)

_STATS_MAIN = (
    "import sys\n"
    "from statlib import mean\n"
    "\n"
    "def main():\n"
    "    nums = [int(x) for x in sys.stdin.readline().split()]\n"
    "    print(mean(nums))\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_STATS_BASE_SYSTEM = {"statlib.py": _STATLIB_MEAN, "main.py": _STATS_MAIN}

# A variant of statlib.py WITHOUT the empty-input guard, used only by ``mf-empty-guard``
# below: with the guarded ``_STATLIB_MEAN`` (used by the other two stats-cli tasks), the
# mean-of-empty-input case is already handled and the task's mod_sentence would require no
# real change (a trivially-already-passing fixture) -- MEASURED via this suite's own
# no-op-modify_fn test, which must reject every MULTIFILE_SLICE task.
_STATLIB_MEAN_CRASHES_ON_EMPTY = (
    '"""Small stats helpers."""\n'
    "\n"
    "def mean(nums):\n"
    "    return sum(nums) / len(nums)\n"
)

_MATHLIB = (
    '"""Arithmetic helpers."""\n'
    "\n"
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def sub(a, b):\n"
    "    return a - b\n"
)

_FORMATTER = (
    '"""Output formatting."""\n'
    "\n"
    "def fmt(label, value):\n"
    "    return f\"{label}: {value}\"\n"
)

_CALC3_MAIN = (
    "import sys\n"
    "from mathlib import add, sub\n"
    "from formatter import fmt\n"
    "\n"
    "def main():\n"
    "    parts = sys.stdin.readline().split()\n"
    "    op, a, b = parts[0], int(parts[1]), int(parts[2])\n"
    "    result = add(a, b) if op == \"add\" else sub(a, b)\n"
    "    print(fmt(op, result))\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_CALC3_BASE_SYSTEM = {"mathlib.py": _MATHLIB, "formatter.py": _FORMATTER, "main.py": _CALC3_MAIN}

MULTIFILE_SLICE: "list[ModificationTask]" = [
    ModificationTask(
        name="mf-add-median-subcmd", cls="stats-cli", tier="medium",
        start_system=dict(_STATS_BASE_SYSTEM),
        mod_sentence=(
            "Add a median feature: when run as `python main.py median` it reads the stdin "
            "integers and prints their median (average of the two middle values if the count "
            "is even); with no argument it still prints the mean."
        ),
        # NOTE: input values are chosen so the median genuinely DIFFERS from the mean (the
        # mod_sentence's literal example numbers 1 2 3 4 / 1 2 3 4 5 coincidentally have
        # median == mean, which would let an unmodified/no-op system trivially pass -- caught
        # by this suite's own no-op-modify_fn test).
        new_checks=[
            (["median"], "1 2 3 10\n", "2.5"),      # sorted [1,2,3,10]: median=2.5, mean=4.0
            (["median"], "1 2 3 4 100\n", "3"),     # sorted [1,2,3,4,100]: median=3, mean=22.0
        ],
        regression_checks=[
            ([], "1 2 3 4\n", "2.5"),
        ],
    ),
    ModificationTask(
        name="mf-add-total-subcmd", cls="stats-cli", tier="medium",
        start_system=dict(_STATS_BASE_SYSTEM),
        mod_sentence=(
            "Change statlib.py so it also provides a `total` function returning the sum of "
            "the numbers, and make `python main.py total` print that sum; no argument still "
            "prints the mean."
        ),
        new_checks=[
            (["total"], "1 2 3\n", "6"),
            (["total"], "10 20\n", "30"),
        ],
        regression_checks=[
            ([], "1 2 3\n", "2"),
        ],
    ),
    ModificationTask(
        name="mf-empty-guard", cls="stats-cli", tier="easy",
        start_system={"statlib.py": _STATLIB_MEAN_CRASHES_ON_EMPTY, "main.py": _STATS_MAIN},
        mod_sentence=(
            "Make the program robust to empty input: if stdin has no integers, print 0 "
            "instead of crashing, for the mean path. Keep normal mean behavior unchanged."
        ),
        new_checks=[
            ([], "\n", "0"),
        ],
        regression_checks=[
            ([], "4 6\n", "5"),
        ],
    ),
    ModificationTask(
        name="mf3-add-mul-op", cls="calculator", tier="hard",
        start_system=dict(_CALC3_BASE_SYSTEM),
        mod_sentence=(
            "Add a multiply operation: when the op (first stdin token) is `mul`, multiply "
            "the two integers. Add a `mul` function to mathlib.py and wire it into main.py. "
            "Keep add and sub working."
        ),
        new_checks=[
            ([], "mul 4 5\n", "mul: 20"),
        ],
        regression_checks=[
            ([], "add 2 3\n", "add: 5"),
            ([], "sub 7 2\n", "sub: 5"),
        ],
    ),
    ModificationTask(
        name="mf3-change-format", cls="calculator", tier="medium",
        start_system=dict(_CALC3_BASE_SYSTEM),
        mod_sentence=(
            "Change the output format so it prints the result as `<op> = <value>` (for "
            "example `add = 5`) instead of `<op>: <value>`. This should only require editing "
            "formatter.py."
        ),
        new_checks=[
            ([], "add 2 3\n", "add = 5"),
            ([], "sub 9 4\n", "sub = 5"),
        ],
        # no old-format regression check by design -- the change alters the sole output, so
        # there is nothing PRE-EXISTING left to regress-check; new_checks alone pin correctness
        # (see module docstring / task-source notes for the honesty rationale).
        regression_checks=[],
    ),
]

ALL_TASKS: "list[ModificationTask]" = FIRST_SLICE + MULTIFILE_SLICE
# #EXT-036-REQ-21 End
