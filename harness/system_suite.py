"""EXT-036 TASK-14: Creation-suite framework + first slice (REQ-20).

REQ-20 needs a broad, DIVERSE, HELD-OUT benchmark of sentence->system CREATION tasks -- not just
the handful of sentences that happened to be probed while building the pipeline (TASK-4/5/6/13).
For the score to be an honest signal (Tenet 3) the acceptance oracle must be INDEPENDENT of the
system under test: it must NOT be the model's own self-derived checklist
(``system_builder._derive_acceptance_checklist``), and the checks themselves must NEVER be leaked
into the solving prompt (``task.sentence`` is all a build ever sees).

The oracle here is BLACK-BOX CLI execution: each task's sentence specifies a concrete CLI contract
(argv / stdin -> stdout), and acceptance runs the BUILT system's entrypoint as a real subprocess
with given args/stdin and asserts on stdout. This is API-agnostic -- the model is free to choose
any module/function names/internal design; the oracle only depends on the CLI contract the
sentence itself states, so it composes with ANY ``build_fn`` matching
``harness.system_builder.build_system``'s signature (``build_fn(spec, root, ...) -> dict`` with
``shipped``/``done``/``plan``/``modules`` keys) without modifying that pipeline at all.

Two-plane split: this module is entirely DETERMINISTIC (no model call anywhere) -- it drives
``build_fn`` (which may itself call a model) and then checks the result via real subprocess runs.

``run_creation_suite`` NEVER raises overall: a failure at any stage for a given task (build
exception, missing/broken entrypoint, a check that errors or times out) is recorded as that task's
honest ``accepted=False`` and the suite moves on to the next task -- one bad task never aborts the
whole measurement run.

Live gemma-vs-escalating-system measurement against this suite, and growing the class/tier
coverage beyond the first slice below, are explicit OUT-OF-SCOPE follow-ups for this task -- this
module only builds the framework + a first concrete slice (2 easy / 2 medium / 2 hard).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# #EXT-036-REQ-20 Start

DEFAULT_TIMEOUT_S = 15   # per-check subprocess guard (a hang is a real failure, never a hang)


@dataclass
class CreationTask:
    """One held-out sentence->system CREATION task (REQ-20). ``checks`` is a list whose items are
    EITHER a 3-tuple ``(argv: list[str], stdin: str | None, expected_substring: str)`` -- a
    black-box CLI check run against the built system's resolved entrypoint -- OR a
    ``callable(root: Path, plan: dict | None) -> bool`` for the rare case a CLI-shaped check
    doesn't fit. Kept intentionally simple + deterministic: no check ever depends on wall-clock
    timing (see the ``ttl=0`` immediate-expiry trick used by the kv-store task below) so the suite
    is reproducible."""

    name: str
    cls: str
    tier: str                 # "easy" | "medium" | "hard"
    sentence: str
    checks: list = field(default_factory=list)


def _run_cli(python_exe: str, entry_path: Path, argv: "list[str]", stdin: "str | None",
             cwd: Path, timeout: float = DEFAULT_TIMEOUT_S) -> "tuple[bool, str]":
    """Guarded BLACK-BOX subprocess execution of the built system's CLI entrypoint (mirrors
    ``harness/multi_file.py::_run``'s Popen + tree-kill-on-timeout pattern, adapted for stdin).
    Runs ``python <entry_path> <argv...>`` in ``cwd``, feeding ``stdin`` (or none). Returns
    ``(ok, combined stdout+stderr)`` where ``ok`` means the process exited 0. Never raises -- a
    failure to start, or a timeout, is a REAL non-passing result, never fabricated as a pass."""
    cmd = [python_exe, str(entry_path)] + list(argv or [])
    try:
        kwargs: dict = dict(cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.PIPE, text=True)
        if os.name != "nt":
            kwargs["start_new_session"] = True
        p = subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        return False, f"failed to start entrypoint: {exc}"
    try:
        stdout, stderr = p.communicate(input=stdin, timeout=timeout)
        return p.returncode == 0, (stdout or "") + (stderr or "")
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                f"taskkill /F /T /PID {p.pid}",
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            import signal
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            p.communicate(timeout=5)
        except Exception:
            pass
        return False, f"entrypoint timed out after {timeout}s (treated as not-passing)"


def _resolve_entry(plan) -> "str | None":
    """The CLI entrypoint the build declared (``plan['entrypoint']``), or None -- a missing/
    malformed plan is a real "no entrypoint resolvable", never a guess."""
    if not isinstance(plan, dict):
        return None
    entry = plan.get("entrypoint")
    return entry.strip() if isinstance(entry, str) and entry.strip() else None


def _run_single_check(check, root: Path, plan, python_exe: str) -> bool:
    """Run ONE acceptance check for a task: either a ``callable(root, plan) -> bool`` or a
    black-box ``(argv, stdin, expected_substring)`` CLI check against the resolved entrypoint.
    Never raises -- a missing entrypoint file, a non-zero exit, a timeout, or any exception is a
    real ``False`` (never a fabricated pass, Tenet 3).

    TASK-15 (REQ-20): every current task's sentence pins a SINGLE-FILE convention ("in a file
    named main.py"). If the plan-declared entrypoint doesn't resolve to a real file (e.g. the
    plan is missing/malformed) but ``root/main.py`` exists, fall back to that -- a minimal,
    GENERIC convention fallback (not keyed to any specific task), never a fabricated pass: it
    still requires a real file to actually exist and actually run successfully."""
    try:
        if callable(check):
            return bool(check(root, plan))
        argv, stdin, expected = check
        entry = _resolve_entry(plan)
        entry_path = (root / entry) if entry else None
        if entry_path is None or not entry_path.is_file():
            fallback = root / "main.py"
            entry_path = fallback if fallback.is_file() else None
        if entry_path is None:
            return False
        ok, out = _run_cli(python_exe, entry_path, argv, stdin, root)
        if not ok:
            return False
        return expected in out
    except Exception:
        return False


def _rates(results: "list[dict]") -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0, "ship_rate": 0.0, "done_rate": 0.0, "accept_rate": 0.0}
    return {
        "n": n,
        "ship_rate": sum(1 for r in results if r["shipped"]) / n,
        "done_rate": sum(1 for r in results if r["done"]) / n,
        "accept_rate": sum(1 for r in results if r["accepted"]) / n,
    }


def _aggregate(results: "list[dict]") -> dict:
    agg = {"overall": _rates(results)}
    tiers = sorted({r["tier"] for r in results})
    agg["by_tier"] = {t: _rates([r for r in results if r["tier"] == t]) for t in tiers}
    return agg


def run_creation_suite(build_fn: Callable, tasks: "list[CreationTask] | None" = None,
                        python_exe: "str | None" = None) -> dict:
    """Run the CREATION suite: for each task, build via ``build_fn(task.sentence, root)`` (same
    positional signature as ``harness.system_builder.build_system``) into an isolated temp root,
    then check the result with the INDEPENDENT black-box CLI oracle (``task.checks`` -- never the
    build's own self-derived acceptance checklist, and never shown to ``build_fn``). Returns
    ``{"results": [...], "aggregate": {"overall": {...}, "by_tier": {...}}}`` reporting honest
    ship-rate/done-rate/accept-rate overall and per tier.

    NEVER raises: any per-task failure (a ``build_fn`` exception, a missing/broken entrypoint, a
    hung/failing check) is recorded as that task's ``accepted=False`` and the suite continues to
    the next task -- one bad task can never abort the whole measurement run."""
    tasks = FIRST_SLICE if tasks is None else tasks
    python_exe = python_exe or sys.executable or "python"
    results: "list[dict]" = []
    for task in tasks:
        rec = {"name": task.name, "cls": task.cls, "tier": task.tier,
               "shipped": False, "done": False, "accepted": False,
               "n_checks_passed": 0, "n_checks": len(task.checks or [])}
        try:
            with tempfile.TemporaryDirectory(prefix="s2s_suite_") as tmp:
                root = Path(tmp)
                build = build_fn(task.sentence, root)
                if isinstance(build, dict):
                    rec["shipped"] = bool(build.get("shipped"))
                    rec["done"] = bool(build.get("done"))
                    plan = build.get("plan")
                    n_pass = sum(1 for c in (task.checks or [])
                                 if _run_single_check(c, root, plan, python_exe))
                    rec["n_checks_passed"] = n_pass
                    rec["accepted"] = bool(task.checks) and n_pass == len(task.checks)
        except Exception:
            pass   # a build/exec failure -> the default rec (accepted=False) stands
        results.append(rec)

    return {"results": results, "aggregate": _aggregate(results)}


# --- FIRST SLICE (2 easy / 2 medium / 2 hard, 6 distinct classes) -------------------------
# Each sentence pins down a concrete, unambiguous CLI contract so the black-box oracle applies
# without needing to know anything about the model's chosen module/function names. Checks never
# depend on wall-clock timing (the TTL task uses a ttl=0 immediate-expiry case, not a real sleep)
# so re-running the suite is fully reproducible.
#
# TASK-15 (REQ-20) CONTRACT-PRECISE REWRITE (2026-07-03): MEASURED (first live run) that the
# original sentences below were too VAGUE, causing two distinct HARNESS false-negatives (not a
# model capability ceiling; see ``.jaros-data/hyp_precise_sentence.py`` +
# ``.jaros-data/debug_suite_v2.py``): (1) gemma sometimes planned an entrypoint filename that
# wasn't one of its own listed modules, so ``validate_plan`` correctly rejected the plan
# ("entrypoint not a listed module") and 0 modules got built; (2) even when it shipped, gemma
# could build a DIFFERENT CLI surface than the one this suite's hardcoded ``checks`` assumed, so
# the independent oracle correctly couldn't run/match it. PROVEN FIX: pin the entrypoint FILENAME
# (``main.py``), the exact invocation, the exact stdout format (incl. a trailing newline), and
# the ``if __name__ == "__main__":`` requirement, directly in the sentence -- this is honest
# (Tenet 3), not leakage: the sentence IS the spec the independent, held-out oracle checks
# against, and the model still has to build a genuinely working system that satisfies it.

FIRST_SLICE: "list[CreationTask]" = [
    CreationTask(
        name="sum-cli", cls="cli-tool", tier="easy",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py. Running it as "
            "`python main.py` (no command-line arguments), it reads one line of "
            "whitespace-separated integers from standard input and prints ONLY their sum, as a "
            "single integer followed by a newline, to standard output (nothing else). The file "
            "must contain an `if __name__ == \"__main__\":` block that runs this."
        ),
        checks=[
            ([], "1 2 3\n", "6"),
            ([], "10 20 5\n", "35"),
        ],
    ),
    CreationTask(
        name="wordcount-cli", cls="cli-tool", tier="easy",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py. Running it as "
            "`python main.py` (no command-line arguments), it reads all text from standard "
            "input and prints ONLY the number of whitespace-separated words in it, as a single "
            "integer followed by a newline, to standard output (nothing else). The file must "
            "contain an `if __name__ == \"__main__\":` block that runs this."
        ),
        checks=[
            ([], "the quick brown fox\n", "4"),
            ([], "hello world\n", "2"),
        ],
    ),
    CreationTask(
        name="todo-list-cli", cls="todo-list", tier="medium",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py, backed by an "
            "in-memory list. Running it as `python main.py` (no command-line arguments), it "
            "reads commands from standard input, one command per line, until standard input is "
            "exhausted (EOF); after processing each command it immediately prints that "
            "command's output line, followed by a newline, to standard output, in the SAME "
            "order the commands were read. Supported commands (each is one line of stdin): "
            "`add <text>` appends a new item with the given text and prints `added <text>`; "
            "`list` prints one line per current item, each formatted exactly as `<index>) "
            "<text>` (index starting at 0, in the order items were added; if there are no "
            "items, `list` prints nothing); `done <index>` marks the item at that integer index "
            "as done and prints `marked done <index>`. The file must contain an `if __name__ "
            "== \"__main__\":` block that runs this."
        ),
        checks=[
            ([], "add buy milk\nlist\n", "added buy milk"),
            ([], "add buy milk\nadd walk dog\nlist\n", "1) walk dog"),
            ([], "add buy milk\ndone 0\n", "marked done 0"),
        ],
    ),
    CreationTask(
        name="temp-converter-cli", cls="cli-tool", tier="medium",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py. Running it as "
            "`python main.py <value> <from_unit> <to_unit>` (exactly three command-line "
            "arguments: value is a number, from_unit and to_unit are each one of C, F, K for "
            "Celsius/Fahrenheit/Kelvin), it prints ONLY the converted numeric value, rounded to "
            "exactly 2 decimal places, followed by a newline, to standard output (nothing "
            "else). The file must contain an `if __name__ == \"__main__\":` block that runs "
            "this."
        ),
        checks=[
            (["0", "C", "F"], None, "32.00"),
            (["100", "C", "F"], None, "212.00"),
            (["0", "C", "K"], None, "273.15"),
        ],
    ),
    CreationTask(
        name="kv-store-ttl-cli", cls="kv-store", tier="hard",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py, an in-memory "
            "key-value store with TTL (time-to-live) expiry. Running it as `python main.py` "
            "(no command-line arguments), it reads commands from standard input, one command "
            "per line, until standard input is exhausted (EOF); after processing each command "
            "it immediately prints that command's output line, followed by a newline, to "
            "standard output, in the SAME order the commands were read. Supported commands: "
            "`set <key> <value> <ttl_seconds>` stores value under key with an integer TTL in "
            "seconds and prints `ok` (a ttl of 0 means the key is treated as already expired "
            "and is immediately unavailable to any later `get`); `get <key>` prints the stored "
            "value if present and not expired, or prints `none` if the key is absent or "
            "expired; `delete <key>` removes the key if present and prints `ok` (print `ok` "
            "even if the key was already absent). The file must contain an `if __name__ == "
            "\"__main__\":` block that runs this."
        ),
        checks=[
            ([], "set a 1 100\nget a\n", "1"),
            ([], "set a 1 0\nget a\n", "none"),
            ([], "set a 1 100\ndelete a\nget a\n", "none"),
        ],
    ),
    CreationTask(
        name="priority-jobqueue-cli", cls="job-queue", tier="hard",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py, an in-memory "
            "priority job queue. Running it as `python main.py` (no command-line arguments), it "
            "reads commands from standard input, one command per line, until standard input is "
            "exhausted (EOF); after processing each command it immediately prints that "
            "command's output line, followed by a newline, to standard output, in the SAME "
            "order the commands were read. Supported commands: `enqueue <name> <priority>` adds "
            "a job with an integer priority (a HIGHER number runs first; jobs with EQUAL "
            "priority run in the order they were enqueued, earliest first) and prints "
            "`enqueued <name>`; `run` removes and runs the single highest-priority pending job, "
            "printing `ran <name>`, or prints `empty` if there are no pending jobs. The file "
            "must contain an `if __name__ == \"__main__\":` block that runs this."
        ),
        checks=[
            ([], "enqueue low 1\nenqueue high 5\nrun\n", "ran high"),
            ([], "enqueue a 1\nenqueue b 1\nrun\nrun\n", "ran a\nran b"),
            ([], "run\n", "empty"),
        ],
    ),

    # --- TASK-17 GROWTH (2026-07-03): +6 more classes, spread easy/medium/hard, same
    # contract-precise convention proven by TASK-15 (single main.py entrypoint, exact
    # invocation, exact stdout format, `if __name__ == "__main__":` required). Held-out,
    # deterministic, no wall-clock dependence.

    CreationTask(
        name="reverse-lines-cli", cls="text-transform", tier="easy",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py. Running it as "
            "`python main.py` (no command-line arguments), it reads lines from standard input "
            "until end of input (EOF); for EACH line, in the SAME order it was read, it prints "
            "that line's characters reversed (excluding its own trailing newline character), "
            "followed by a newline, to standard output (nothing else is printed). The file must "
            "contain an `if __name__ == \"__main__\":` block that runs this."
        ),
        checks=[
            ([], "abc\n", "cba"),
            ([], "hello\nworld\n", "olleh\ndlrow"),
        ],
    ),
    CreationTask(
        name="max-of-stdin-cli", cls="cli-tool", tier="easy",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py. Running it as "
            "`python main.py` (no command-line arguments), it reads one line of "
            "whitespace-separated integers from standard input and prints ONLY the MAXIMUM of "
            "those integers, as a single integer followed by a newline, to standard output "
            "(nothing else). The file must contain an `if __name__ == \"__main__\":` block that "
            "runs this."
        ),
        checks=[
            ([], "3 1 4 1 5\n", "5"),
            ([], "7 2 9 3\n", "9"),
        ],
    ),
    CreationTask(
        name="rpn-calc-cli", cls="calculator", tier="medium",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py, a Reverse Polish "
            "Notation (postfix) calculator. Running it as `python main.py` (no command-line "
            "arguments), it reads ONE line of whitespace-separated tokens from standard input, "
            "where each token is either an integer or one of the operators +, -, *, / ; it "
            "evaluates the postfix expression using a standard stack-based algorithm (for each "
            "operator, pop the top two values, apply the operator with the SECOND-popped value "
            "on the left and the FIRST-popped value on the right, and push the result) and "
            "prints ONLY the final result, as a single integer followed by a newline, to "
            "standard output (nothing else). You may assume the input is always a valid postfix "
            "expression and that every `/` divides evenly (the test inputs never require "
            "rounding). The file must contain an `if __name__ == \"__main__\":` block that runs "
            "this."
        ),
        checks=[
            ([], "3 4 +\n", "7"),
            ([], "5 1 2 + 4 * + 3 -\n", "14"),
            ([], "10 2 /\n", "5"),
        ],
    ),
    CreationTask(
        name="kv-lines-sorted-cli", cls="parser", tier="medium",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py. Running it as "
            "`python main.py` (no command-line arguments), it reads lines from standard input "
            "until end of input (EOF); each non-blank line is of the form `key=value` where key "
            "and value are single tokens containing no `=` or whitespace characters (blank "
            "lines are ignored). After all input has been read, it prints ONE line per UNIQUE "
            "key, in ASCENDING alphabetical order by key, each formatted EXACTLY as "
            "`key=value` followed by a newline; if a key appears more than once, use the value "
            "from its LAST occurrence. Nothing else is printed. The file must contain an `if "
            "__name__ == \"__main__\":` block that runs this."
        ),
        checks=[
            ([], "b=2\na=1\n", "a=1\nb=2"),
            ([], "x=1\nx=2\n", "x=2"),
            ([], "z=9\na=1\nm=5\n", "a=1\nm=5\nz=9"),
        ],
    ),
    CreationTask(
        name="pubsub-cli", cls="pub-sub", tier="hard",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py, an in-memory "
            "publish/subscribe event system. Running it as `python main.py` (no command-line "
            "arguments), it reads commands from standard input, one command per line, until "
            "standard input is exhausted (EOF); after processing each command it immediately "
            "prints that command's output, followed by a newline for each printed line, to "
            "standard output. Supported commands: `subscribe <name> <topic>` registers "
            "subscriber `<name>` to `<topic>` and prints `subscribed <name> <topic>`; `publish "
            "<topic> <message>` (message is a single token with no spaces) delivers the message "
            "to every subscriber currently subscribed to `<topic>`, printing one line per "
            "subscriber, in the ORDER those subscribers subscribed, each formatted EXACTLY as "
            "`<name> received <message>`; if `<topic>` has no subscribers, `publish` prints "
            "ONLY `no subscribers` instead. The file must contain an `if __name__ == "
            "\"__main__\":` block that runs this."
        ),
        checks=[
            ([], "subscribe a t\nsubscribe b t\npublish t hello\n",
             "a received hello\nb received hello"),
            ([], "publish t2 hi\n", "no subscribers"),
            ([], "subscribe a t\npublish other hi\n", "no subscribers"),
        ],
    ),
    CreationTask(
        name="rate-limiter-cli", cls="rate-limiter", tier="hard",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py, a fixed-window "
            "request rate limiter. Running it as `python main.py <limit>` (exactly one "
            "command-line argument, a positive integer `limit`), it then reads commands from "
            "standard input, one command per line, until standard input is exhausted (EOF); "
            "each line is `request <id>` (id is a single token identifying the request). "
            "Treat the ENTIRE run as one fixed window: the first `limit` requests, in the "
            "order they are read, are ALLOWED -- print `allow <id>` for each; every request "
            "after that (the (limit+1)-th and beyond) is DENIED -- print `deny <id>` for each. "
            "Print exactly one line per `request` command, in the order the commands were "
            "read, and nothing else. The file must contain an `if __name__ == \"__main__\":` "
            "block that runs this."
        ),
        checks=[
            (["2"], "request a\nrequest b\nrequest c\n", "allow a\nallow b\ndeny c"),
            (["1"], "request x\nrequest y\n", "allow x\ndeny y"),
            (["3"], "request a\nrequest b\n", "allow a\nallow b"),
        ],
    ),
]
# #EXT-036-REQ-20 End
