"""EXT-036 TASK-26: Long-horizon build coherence instrument (REQ-23).

PRIME-001's north-star capability (g) is staying ALIGNED to a LARGE, multi-requirement ask over
a long build without drift. The creation suite (``harness/system_suite.py``) and modification
suite (``harness/modification_suite.py``) each measure a SINGLE-behavior prompt end to end. What's
missing is the coherence/drift angle: given ONE prompt that states N DISTINCT requirements, how
many does the built system actually satisfy (each independently, honestly verified), not just
"shipped y/n". This module is the MINIMAL first version of that instrument, starting at
minute-scale (a handful of requirements, a single-file build) -- deterministic + independent-
oracle-graded, exactly like the creation suite. Wiring a governed decompose->task->alignment-gate
loop that LIFTS this number is an explicit follow-up capstone, not this module's job.

The oracle is the SAME proven BLACK-BOX CLI mechanism ``harness.system_suite`` already built and
proved (TASK-14/15/17/24): each requirement is an independent ``(req_id, argv, stdin,
expected_substring)`` check run as a real subprocess against the built system's resolved
entrypoint. This module REUSES ``harness.system_suite._run_cli``/``_resolve_entry`` rather than
duplicating that subprocess-execution/entrypoint-resolution logic -- it only composes them
differently (per-REQUIREMENT grading within ONE task, instead of per-TASK accept/reject), because
a coherence task's own contract may legitimately want a requirement's check to hold regardless of
exit code (unlike ``system_suite._run_single_check``, which always treats a non-zero exit as an
automatic fail before even looking at output). Nothing in ``harness/system_suite.py`` is modified.

Two-plane split: this module is entirely DETERMINISTIC (no model call anywhere) -- it drives an
arbitrary ``build_fn`` (which may itself call a model) against ONE multi-requirement prompt, then
independently checks each requirement via a real subprocess run. ``run_coherence_suite`` NEVER
raises: a build/exec failure for a given task records that task's honest
``requirements_satisfied=0`` and the suite continues to the next task.

Live gemma-vs-escalating measurement against this suite, and growing the class/tier coverage
beyond the FIRST_SLICE below, are explicit OUT-OF-SCOPE follow-ups for this task -- this module
only builds the instrument + a first concrete slice (3 tasks, 4-5 requirements each, across
easy/medium/hard tiers).

TASK-30 (REQ-23 hardening) added ``HARD_SLICE`` right below ``FIRST_SLICE``: HARD,
MANY-requirement, INTERDEPENDENT "highly-complex" tasks (11 requirements each) -- including the
kvdb-cli that a separate probe measured `build_system` at only 10/11 on, showing FIRST_SLICE alone
had saturated at coherence=1.00 and stopped being discriminating. ``ALL_COHERENCE_TASKS =
FIRST_SLICE + HARD_SLICE`` is exposed for callers that want the full, growing set;
``run_coherence_suite``'s own default is UNCHANGED (still ``FIRST_SLICE``) for backward
compatibility.

TASK-31 (REQ-23 stability): MEASURED (a live run of the hardened HARD_SLICE) that single-pass
(``repeats=1``) ``build_system`` is HIGH-VARIANCE on the hard, 11-requirement tasks -- kvdb-cli
scored 0/11 on one draw (a fast BROKEN build, ~49s) but 10/11 on another (~158s); taskmgr-cli hit
11/11. A single run is not a stable coherence number. ``run_coherence_suite`` now accepts an
``repeats: int = 1`` parameter (default 1 = the ORIGINAL behavior/record shape, byte-identical,
backward-compatible); when ``repeats > 1`` each task is built + independently verified ``repeats``
times and the per-task record is enriched with ``coherence_median``/``coherence_mean``/
``coherence_min``/``coherence_max``/``runs`` (the per-run ``requirements_satisfied`` list) plus a
``build_ok``-derived ``build_failed_count`` (the run's entrypoint never produced anything runnable
-- distinct from a run that ran fine but merely DROPPED a requirement, ``dropped_requirements_count``).
The top-level ``coherence``/``requirements_satisfied`` in the record stay the MEDIAN run's actual
values (a stable central number for existing consumers), while ``coherence_median`` is the plain
statistical median of the per-run coherence values. NEVER raises: a failed run counts as coherence
0.0 for that run, never aborting the suite.
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from harness.system_suite import _resolve_entry, _run_cli

# #EXT-036-REQ-23 Start

DEFAULT_TIMEOUT_S = 15   # per-requirement subprocess guard (a hang is a real failure, never a hang)


@dataclass
class CoherenceTask:
    """One held-out MULTI-REQUIREMENT build-coherence task (REQ-23). ``prompt`` is ONE
    contract-precise sentence/paragraph describing a system with N DISTINCT requirements.
    ``requirements`` is a list of 4-tuples ``(req_id: str, argv: list[str], stdin: str | None,
    expected_substring: str)`` -- each an INDEPENDENT black-box CLI check for exactly ONE of the
    prompt's stated requirements, run against the built system's resolved entrypoint (the SAME
    ``main.py``-single-entrypoint convention ``harness.system_suite.FIRST_SLICE`` uses). Kept
    intentionally simple + deterministic: no requirement check ever depends on wall-clock timing,
    so the suite is fully reproducible."""

    name: str
    tier: str                 # "easy" | "medium" | "hard" | "highly-complex"
    prompt: str
    requirements: list = field(default_factory=list)


def _run_requirement_check(req, root: Path, plan, python_exe: str) -> bool:
    """Run ONE requirement's independent black-box CLI check. REUSES ``_resolve_entry`` (the
    same plan-declared-entrypoint-with-``main.py``-fallback convention ``system_suite`` uses) and
    ``_run_cli`` (the same guarded Popen + tree-kill-on-timeout subprocess runner) -- never
    duplicating that logic. Deliberately does NOT gate on the subprocess exit code the way
    ``system_suite._run_single_check`` does: a requirement's own contract decides what "satisfied"
    means (e.g. a requirement may legitimately describe a graceful-error path), so this just checks
    whether ``expected_substring`` appears in the combined stdout+stderr. Never raises -- a missing
    entrypoint, a non-zero exit whose output doesn't contain the expected text, a timeout, or any
    exception is an honest ``False`` (never a fabricated pass, Tenet 3)."""
    try:
        _req_id, argv, stdin, expected = req
        entry = _resolve_entry(plan)
        entry_path = (root / entry) if entry else None
        if entry_path is None or not entry_path.is_file():
            fallback = root / "main.py"
            entry_path = fallback if fallback.is_file() else None
        if entry_path is None:
            return False
        _ok, out = _run_cli(python_exe, entry_path, argv, stdin, root, timeout=DEFAULT_TIMEOUT_S)
        return expected in out
    except Exception:
        return False


def _coherence_rates(results: "list[dict]") -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0, "mean_coherence": 0.0, "fully_coherent_rate": 0.0}
    return {
        "n": n,
        "mean_coherence": sum(r["coherence"] for r in results) / n,
        "fully_coherent_rate": sum(1 for r in results if r["all_satisfied"]) / n,
    }


def _aggregate(results: "list[dict]") -> dict:
    agg = {"overall": _coherence_rates(results)}
    tiers = sorted({r["tier"] for r in results})
    agg["by_tier"] = {t: _coherence_rates([r for r in results if r["tier"] == t]) for t in tiers}
    return agg


# --- TASK-31 (REQ-23 stability): repeats>1 n-of-k aggregation --------------------------------
# A SEPARATE aggregation path (never touched by the ``repeats=1``/default path above) so the
# original behavior/record shape stays byte-identical for existing callers/tests.

def _coherence_rates_repeated(results: "list[dict]") -> dict:
    """Like ``_coherence_rates`` but the mean is over each task's ``coherence_median`` (the
    stable central number, per TASK-31's motivation) rather than a single noisy draw, and adds
    ``build_failure_rate`` -- the fraction of ALL individual runs (across every task in
    ``results``) whose entrypoint never produced anything runnable at all (``build_ok`` False),
    as distinct from a run that ran but merely dropped a requirement."""
    n = len(results)
    if n == 0:
        return {"n": 0, "mean_coherence": 0.0, "fully_coherent_rate": 0.0, "build_failure_rate": 0.0}
    total_runs = sum(r.get("repeats", 1) for r in results)
    total_build_failed = sum(r.get("build_failed_count", 0) for r in results)
    return {
        "n": n,
        "mean_coherence": sum(r["coherence_median"] for r in results) / n,
        "fully_coherent_rate": sum(1 for r in results if r["all_satisfied"]) / n,
        "build_failure_rate": (total_build_failed / total_runs) if total_runs else 0.0,
    }


def _aggregate_repeated(results: "list[dict]") -> dict:
    agg = {"overall": _coherence_rates_repeated(results)}
    tiers = sorted({r["tier"] for r in results})
    agg["by_tier"] = {
        t: _coherence_rates_repeated([r for r in results if r["tier"] == t]) for t in tiers
    }
    return agg


def _run_task_once(task: "CoherenceTask", build_fn: Callable, python_exe: str) -> dict:
    """ONE build+verify run of ``task`` -- the repeats>1 per-run primitive. Returns
    ``{requirements_satisfied, coherence, all_satisfied, wall_seconds, build_ok}`` where
    ``build_ok`` is the deterministic BUILD-FAILURE vs DROPPED-REQUIREMENT distinguisher: True
    only when the resolved entrypoint genuinely exists on disk AND (the task has zero
    requirements OR at least one requirement was satisfied) -- i.e. the build produced SOMETHING
    runnable, as opposed to a broken/empty draw. Never raises -- any exception (a raising
    ``build_fn``, a missing entrypoint, a bad root) is an honest ``build_ok=False`` /
    ``requirements_satisfied=0`` run, never a fabricated pass."""
    total = len(task.requirements or [])
    rec = {"requirements_satisfied": 0, "coherence": 0.0, "all_satisfied": False,
           "wall_seconds": 0.0, "build_ok": False}
    try:
        with tempfile.TemporaryDirectory(prefix="coherence_suite_") as tmp:
            root = Path(tmp)
            t0 = time.perf_counter()
            build = build_fn(task.prompt, root)
            rec["wall_seconds"] = time.perf_counter() - t0
            if isinstance(build, dict):
                plan = build.get("plan")
                entry = _resolve_entry(plan)
                entry_path = (root / entry) if entry else None
                if entry_path is None or not entry_path.is_file():
                    fallback = root / "main.py"
                    entry_path = fallback if fallback.is_file() else None
                entry_exists = entry_path is not None and entry_path.is_file()
                satisfied = sum(
                    1 for req in (task.requirements or [])
                    if _run_requirement_check(req, root, plan, python_exe)
                )
                rec["requirements_satisfied"] = satisfied
                rec["coherence"] = (satisfied / total) if total else 0.0
                rec["all_satisfied"] = bool(total) and satisfied == total
                rec["build_ok"] = entry_exists and (total == 0 or satisfied > 0)
    except Exception:
        pass   # a build/exec failure -> the default rec (0 satisfied, build_ok False) stands
    return rec


def _run_task_repeated(task: "CoherenceTask", build_fn: Callable, python_exe: str,
                        repeats: int) -> dict:
    """Build + independently verify ``task`` ``repeats`` times and aggregate the runs into ONE
    per-task record. The top-level ``coherence``/``requirements_satisfied``/``all_satisfied`` are
    the MEDIAN run's own actual values (a stable, reproducible central pick: sort the per-run
    ``requirements_satisfied`` counts and take ``statistics.median_low`` -- the lower of the two
    middle values on a tie -- then use the FIRST run matching that count), so existing consumers
    of those keys get a stable number instead of one noisy draw. ``coherence_median`` is the
    plain statistical median of the per-run coherence values (may legitimately differ from the
    selected median run's own ``coherence`` on an even ``repeats`` with a tied split -- it is a
    separate, purely statistical figure). ``build_failed_count``/``dropped_requirements_count``
    separate the two measured failure modes: a run whose entrypoint never produced anything
    runnable at all (``build_ok`` False) vs. a run that ran fine but dropped >=1 requirement."""
    total = len(task.requirements or [])
    runs = [_run_task_once(task, build_fn, python_exe) for _ in range(repeats)]
    satisfied_values = [r["requirements_satisfied"] for r in runs]
    coherence_values = [r["coherence"] for r in runs]
    med_value = statistics.median_low(satisfied_values)
    med_idx = satisfied_values.index(med_value)
    median_run = runs[med_idx]
    build_failed_count = sum(1 for r in runs if not r["build_ok"])
    dropped_requirements_count = sum(
        1 for r in runs if r["build_ok"] and r["requirements_satisfied"] < total
    )
    return {
        "name": task.name, "tier": task.tier,
        "requirements_total": total,
        "requirements_satisfied": median_run["requirements_satisfied"],
        "coherence": median_run["coherence"],
        "all_satisfied": median_run["all_satisfied"],
        "wall_seconds": sum(r["wall_seconds"] for r in runs),
        "coherence_median": statistics.median(coherence_values),
        "coherence_mean": statistics.mean(coherence_values),
        "coherence_min": min(coherence_values),
        "coherence_max": max(coherence_values),
        "runs": satisfied_values,
        "build_failed_count": build_failed_count,
        "dropped_requirements_count": dropped_requirements_count,
        "repeats": repeats,
    }


def run_coherence_suite(build_fn: Callable, tasks: "list[CoherenceTask] | None" = None,
                         python_exe: "str | None" = None, repeats: int = 1) -> dict:
    """Run the COHERENCE suite: for each task, build via ``build_fn(task.prompt, root)`` (same
    positional shape as ``harness.system_builder.build_system`` -- callers pass a partial binding
    ``llm``) into an isolated temp root, then run EACH requirement's independent check against the
    built entrypoint. Records per task ``{name, tier, requirements_total,
    requirements_satisfied, coherence, all_satisfied, wall_seconds}`` where ``coherence =
    requirements_satisfied / requirements_total`` (the drift/partial signal -- NOT all-or-nothing)
    and ``wall_seconds`` is the measured duration of the BUILD call only (reported for visibility;
    correctness never depends on it). Returns ``{"results": [...], "aggregate": {"overall": {...},
    "by_tier": {...}}}`` reporting mean coherence + fully-coherent rate, overall and per tier.

    ``repeats`` (TASK-31, default 1) -- when <= 1 this is the ORIGINAL single-pass behavior above,
    byte-identical record/aggregate shape (backward-compatible). When > 1, MEASURED single-pass
    variance on hard tasks (a live run of ``HARD_SLICE`` scored kvdb-cli 0/11 on one draw, 10/11 on
    another) is smoothed by building + independently verifying each task ``repeats`` times: the
    per-task record gains ``coherence_median``/``coherence_mean``/``coherence_min``/
    ``coherence_max``/``runs`` (the per-run ``requirements_satisfied`` list), plus
    ``build_failed_count`` (runs whose entrypoint never produced anything runnable at all) and
    ``dropped_requirements_count`` (runs that ran fine but dropped >=1 requirement) -- two distinct
    measured failure modes. The record's top-level ``coherence``/``requirements_satisfied``/
    ``all_satisfied`` stay the MEDIAN run's own actual values (a stable central number for existing
    consumers of those keys); the aggregate additionally reports the mean of each task's
    ``coherence_median`` (the stable central number) and a ``build_failure_rate`` across all runs.

    NEVER raises: any per-task/per-run failure (a ``build_fn`` exception, a missing/broken
    entrypoint, a hung/failing requirement check) is recorded as that run's honest
    ``requirements_satisfied=0``/``coherence=0.0`` (and, at ``repeats > 1``, a ``build_failed``
    run) -- the suite continues to the next task/run, one bad run can never abort the whole
    measurement."""
    tasks = FIRST_SLICE if tasks is None else tasks
    python_exe = python_exe or sys.executable or "python"

    if repeats is None or repeats <= 1:
        # ORIGINAL single-pass behavior, kept byte-identical (backward-compatible record/
        # aggregate shape) -- deliberately NOT refactored to share code with the repeats>1 path
        # below so existing callers/tests are never affected by this task's addition.
        results: "list[dict]" = []
        for task in tasks:
            total = len(task.requirements or [])
            rec = {
                "name": task.name, "tier": task.tier,
                "requirements_total": total, "requirements_satisfied": 0,
                "coherence": 0.0, "all_satisfied": False, "wall_seconds": 0.0,
            }
            try:
                with tempfile.TemporaryDirectory(prefix="coherence_suite_") as tmp:
                    root = Path(tmp)
                    t0 = time.perf_counter()
                    build = build_fn(task.prompt, root)
                    rec["wall_seconds"] = time.perf_counter() - t0
                    if isinstance(build, dict):
                        plan = build.get("plan")
                        satisfied = sum(
                            1 for req in (task.requirements or [])
                            if _run_requirement_check(req, root, plan, python_exe)
                        )
                        rec["requirements_satisfied"] = satisfied
                        rec["coherence"] = (satisfied / total) if total else 0.0
                        rec["all_satisfied"] = bool(total) and satisfied == total
            except Exception:
                pass   # a build/exec failure -> the default rec (0 satisfied) stands
            results.append(rec)

        return {"results": results, "aggregate": _aggregate(results)}

    # repeats > 1 (TASK-31): build + independently verify each task ``repeats`` times, aggregate
    # per task via ``_run_task_repeated``, and report the median-of-k + build-failure-rate view.
    repeats = int(repeats)
    results = [_run_task_repeated(task, build_fn, python_exe, repeats) for task in tasks]
    return {"results": results, "aggregate": _aggregate_repeated(results)}


# --- FIRST SLICE (3 tasks, 4-5 requirements each, across easy/medium/hard tiers) ------------
# Each prompt is ONE contract-precise sentence/paragraph stating several DISTINCT requirements,
# pinning the same single ``main.py`` entrypoint convention ``harness.system_suite.FIRST_SLICE``
# proved (TASK-15): exact invocation (argv and/or a precise line-based stdin protocol), exact
# stdout format, `if __name__ == "__main__":` required. Each task's requirements are proven
# internally coherent (Tenet 3) by ``tests/test_ext036_coherence.py``: a correct reference
# implementation satisfies ALL of them.

FIRST_SLICE: "list[CoherenceTask]" = [
    CoherenceTask(
        name="stats-cli", tier="easy",
        prompt=(
            "Write a single-file Python CLI program in a file named main.py. Running it as "
            "`python main.py <subcommand>` where <subcommand> is exactly one command-line "
            "argument: (1) if <subcommand> is `sum`, read ONE line of whitespace-separated "
            "integers from standard input and print ONLY their sum, as a single integer "
            "followed by a newline, to standard output; (2) if <subcommand> is `mean`, read ONE "
            "line of whitespace-separated integers from standard input and print ONLY their "
            "arithmetic mean, rounded to exactly 2 decimal places, followed by a newline, to "
            "standard output; (3) if <subcommand> is `max`, read ONE line of "
            "whitespace-separated integers from standard input and print ONLY the maximum of "
            "those integers, as a single integer followed by a newline, to standard output; "
            "(4) for any other or missing <subcommand>, print exactly `usage: main.py "
            "{sum|mean|max}` followed by a newline to standard output and exit with code 0 (do "
            "not read standard input in this case). Nothing else is ever printed. The file must "
            "contain an `if __name__ == \"__main__\":` block that runs this."
        ),
        requirements=[
            ("sum", ["sum"], "1 2 3\n", "6"),
            ("mean", ["mean"], "1 2 3\n", "2.00"),
            ("max", ["max"], "1 2 3\n", "3"),
            ("usage", ["bogus"], None, "usage: main.py {sum|mean|max}"),
        ],
    ),
    CoherenceTask(
        name="text-tools-cli", tier="medium",
        prompt=(
            "Write a single-file Python CLI program in a file named main.py. Running it as "
            "`python main.py <subcommand>` where <subcommand> is exactly one command-line "
            "argument, it reads ONE line of text from standard input (excluding its trailing "
            "newline) and behaves as follows: (1) if <subcommand> is `upper`, print that line "
            "converted to UPPERCASE, followed by a newline; (2) if <subcommand> is `lower`, "
            "print that line converted to lowercase, followed by a newline; (3) if <subcommand> "
            "is `reverse`, print that line's characters reversed, followed by a newline; (4) if "
            "<subcommand> is `count-words`, print ONLY the number of whitespace-separated words "
            "in that line, as a single integer followed by a newline; (5) for any other or "
            "missing <subcommand>, print exactly `usage: main.py "
            "{upper|lower|reverse|count-words}` followed by a newline and exit with code 0 (do "
            "not read standard input in this case). Nothing else is ever printed. The file must "
            "contain an `if __name__ == \"__main__\":` block that runs this."
        ),
        requirements=[
            ("upper", ["upper"], "Hello World\n", "HELLO WORLD"),
            ("lower", ["lower"], "Hello World\n", "hello world"),
            ("reverse", ["reverse"], "abc\n", "cba"),
            ("count-words", ["count-words"], "the quick brown fox\n", "4"),
            ("usage", ["nope"], None, "usage: main.py {upper|lower|reverse|count-words}"),
        ],
    ),
    CoherenceTask(
        name="ledger-cli", tier="hard",
        prompt=(
            "Write a single-file Python CLI program in a file named main.py, an in-memory "
            "ledger starting at balance 0. Running it as `python main.py` (no command-line "
            "arguments), it reads commands from standard input, one command per line, until "
            "standard input is exhausted (EOF); after processing each command it immediately "
            "prints that command's output line, followed by a newline, to standard output, in "
            "the SAME order the commands were read. Supported commands: `deposit <amount>` "
            "(amount is a positive integer) increases the balance by <amount> and prints "
            "`balance <new_balance>`; `withdraw <amount>` decreases the balance by <amount> and "
            "prints `balance <new_balance>` IF the current balance is >= <amount>, otherwise the "
            "balance is left UNCHANGED and it prints `insufficient funds`; `balance` prints the "
            "current balance as `balance <current_balance>` (without changing it); any other "
            "command prints exactly `usage: deposit|withdraw|balance`. The file must contain an "
            "`if __name__ == \"__main__\":` block that runs this."
        ),
        requirements=[
            ("deposit", [], "deposit 100\n", "balance 100"),
            ("withdraw-ok", [], "deposit 100\nwithdraw 40\n", "balance 60"),
            ("withdraw-insufficient", [], "deposit 10\nwithdraw 50\n", "insufficient funds"),
            ("balance-query", [], "deposit 30\nbalance\n", "balance 30"),
            ("usage", [], "foo\n", "usage: deposit|withdraw|balance"),
        ],
    ),
]


# --- HARD SLICE (REQ-23 hardening, TASK-30) --------------------------------------------------
# MEASURED (2026-07-03/04, a separately-probed 11-requirement interdependent kvdb-cli): the
# FIRST_SLICE above saturates at coherence=1.00 for build_system -- a HARD, MANY-requirement,
# INTERDEPENDENT slice is needed to keep the instrument DISCRIMINATING (never floor/ceiling out).
# Each task below is "highly-complex" tier, >=8 independent requirements, and INTERDEPENDENT
# (later requirement checks depend on state built up by earlier commands in the SAME stdin
# stream -- e.g. `get` after a prior `set`, `count`/`pending-count` after prior `add`s), so a
# build that silently drops or corrupts EARLIER state shows up in LATER checks too. Same
# contract-precision + internal-coherence discipline as FIRST_SLICE (Tenet 3): each task's
# ``tests/test_ext036_coherence.py`` reference implementation satisfies ALL its requirements.

HARD_SLICE: "list[CoherenceTask]" = [
    CoherenceTask(
        name="kvdb-cli", tier="highly-complex",
        prompt=(
            "Write a single-file Python CLI program in a file named main.py, an in-memory "
            "key-value store starting empty. Running it as `python main.py` (no command-line "
            "arguments), it reads commands from standard input, one command per line, until "
            "standard input is exhausted (EOF); after processing each command it immediately "
            "prints that command's output line, followed by a newline, to standard output, in "
            "the SAME order the commands were read. Supported commands: `set <key> <value>` "
            "stores <value> (a single token) under <key> and prints `ok`; `get <key>` prints "
            "the stored value for <key> if it currently exists, otherwise prints `none`; "
            "`delete <key>` removes <key> if present (no error if absent) and prints `ok`; "
            "`exists <key>` prints `yes` if <key> is currently stored, otherwise prints `no`; "
            "`count` prints the current number of stored keys as a single integer; `keys` "
            "prints all currently-stored keys, SORTED alphabetically and separated by a single "
            "space, on one line; `incr <key>` treats the stored value for <key> as an integer "
            "(treating a currently-missing key as 0), adds 1 to it, stores the result as a "
            "string, and prints the new integer value; `clear` removes every stored key and "
            "prints `ok`; any other or malformed command prints exactly `usage`. The file must "
            "contain an `if __name__ == \"__main__\":` block that runs this."
        ),
        requirements=[
            ("set", [], "set a 1\n", "ok"),
            ("get", [], "set a 1\nget a\n", "1"),
            ("get-missing", [], "get zzz\n", "none"),
            ("delete", [], "set a 1\ndelete a\nget a\n", "none"),
            ("exists-yes", [], "set a 1\nexists a\n", "yes"),
            ("exists-no", [], "exists zzz\n", "no"),
            ("count", [], "set a 1\nset b 2\ncount\n", "2"),
            ("keys", [], "set b 2\nset a 1\nkeys\n", "a b"),
            ("incr", [], "set n 5\nincr n\n", "6"),
            ("clear", [], "set a 1\nset b 2\nclear\ncount\n", "0"),
            ("usage", [], "bogus\n", "usage"),
        ],
    ),
    CoherenceTask(
        name="taskmgr-cli", tier="highly-complex",
        prompt=(
            "Write a single-file Python CLI program in a file named main.py, an in-memory task "
            "list starting empty, with an auto-incrementing integer id starting at 1. Running "
            "it as `python main.py` (no command-line arguments), it reads commands from "
            "standard input, one command per line, until standard input is exhausted (EOF); "
            "after processing each command it immediately prints that command's output "
            "line(s), followed by a newline, to standard output, in the SAME order the "
            "commands were read. Supported commands: `add <text>` (<text> may contain spaces "
            "and is everything after the first space) creates a new task with the next id "
            "(assigned in order starting at 1) and status `pending`, and prints `added <id>`; "
            "`done <id>` marks the task with that id as `done` and prints `done <id>` if a "
            "task with that id currently exists, otherwise prints `no such task` and changes "
            "nothing; `remove <id>` deletes the task with that id and prints `removed <id>` "
            "if it currently exists, otherwise prints `no such task` and changes nothing; "
            "`list` prints each remaining task, one per line, in the order it was added, each "
            "formatted as `<id> <status> <text>` (status is `pending` or `done`), or prints "
            "exactly `no tasks` if there are currently none; `count` prints the current total "
            "number of tasks (pending plus done) as a single integer; `pending-count` prints "
            "the current number of tasks whose status is still `pending`, as a single integer; "
            "any other or malformed command prints exactly `usage`. The file must contain an "
            "`if __name__ == \"__main__\":` block that runs this."
        ),
        requirements=[
            ("add-first", [], "add buy milk\n", "added 1"),
            ("add-second-increments", [], "add buy milk\nadd walk dog\n", "added 2"),
            ("done", [], "add buy milk\ndone 1\n", "done 1"),
            ("done-missing", [], "done 99\n", "no such task"),
            ("list-shows-status", [], "add buy milk\ndone 1\nlist\n", "1 done buy milk"),
            ("list-empty", [], "list\n", "no tasks"),
            ("remove", [], "add buy milk\nremove 1\n", "removed 1"),
            ("remove-missing", [], "remove 5\n", "no such task"),
            ("count-after-remove", [], "add a\nadd b\nremove 1\ncount\n", "1"),
            ("pending-count", [], "add a\nadd b\ndone 1\npending-count\n", "1"),
            ("usage", [], "bogus\n", "usage"),
        ],
    ),
]

# ``ALL_COHERENCE_TASKS`` composes FIRST_SLICE + HARD_SLICE for callers that want the full,
# harder-and-growing set; ``run_coherence_suite``'s own DEFAULT stays FIRST_SLICE (backward
# compatible -- existing callers/tests that rely on the small, fast default are unaffected).
ALL_COHERENCE_TASKS: "list[CoherenceTask]" = FIRST_SLICE + HARD_SLICE
# #EXT-036-REQ-23 End
