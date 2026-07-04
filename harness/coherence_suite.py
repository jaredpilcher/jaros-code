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
"""

from __future__ import annotations

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


def run_coherence_suite(build_fn: Callable, tasks: "list[CoherenceTask] | None" = None,
                         python_exe: "str | None" = None) -> dict:
    """Run the COHERENCE suite: for each task, build via ``build_fn(task.prompt, root)`` (same
    positional shape as ``harness.system_builder.build_system`` -- callers pass a partial binding
    ``llm``) into an isolated temp root, then run EACH requirement's independent check against the
    built entrypoint. Records per task ``{name, tier, requirements_total,
    requirements_satisfied, coherence, all_satisfied, wall_seconds}`` where ``coherence =
    requirements_satisfied / requirements_total`` (the drift/partial signal -- NOT all-or-nothing)
    and ``wall_seconds`` is the measured duration of the BUILD call only (reported for visibility;
    correctness never depends on it). Returns ``{"results": [...], "aggregate": {"overall": {...},
    "by_tier": {...}}}`` reporting mean coherence + fully-coherent rate, overall and per tier.

    NEVER raises: any per-task failure (a ``build_fn`` exception, a missing/broken entrypoint, a
    hung/failing requirement check) is recorded as that task's honest
    ``requirements_satisfied=0``/``coherence=0.0`` and the suite continues to the next task -- one
    bad task can never abort the whole measurement run."""
    tasks = FIRST_SLICE if tasks is None else tasks
    python_exe = python_exe or sys.executable or "python"
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
# #EXT-036-REQ-23 End
