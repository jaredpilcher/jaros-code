"""Shadow-mode parity replay harness (EXT-005 REQ-15).

THE PURSUIT scoreboard instrument #6 (PRIME-001 intent, ``docs/PURSUIT.md``): the
shadow-mode parity log replays the owner's REAL Claude Code task prompts against
jcode and scores whether jcode achieves a comparable result -- the one parity
instrument nobody can game, because the tasks are real, not self-authored.

This module builds the REPLAY MECHANISM + the transcript FORMAT only. HONESTY
(Tenet 3): there is no real Claude Code transcript data shipped with this module --
until the owner seeds real transcripts in the format documented below, there is no
parity number to report, and none is fabricated here. Seeding real transcripts is an
explicit STANDING ASK for the owner; this harness is fully offline-testable today
with synthetic transcripts (see ``tests/test_shadow_replay.py``).

Transcript FORMAT (JSONL, one shadow task per line)::

    {"task_id": "shadow-001",
     "prompt": "<the REAL Claude Code task prompt, verbatim>",
     "kind": "build",              # "build" | "modify" | "answer" | ...
     "acceptance": {...}}

``acceptance`` depends on ``kind``:

- ``build`` / ``modify`` -- a black-box CLI oracle, reusing the exact check shape
  ``harness.system_suite.CreationTask.checks`` already uses::

      {"entry": "main.py",             # optional; relative path of the CLI entrypoint
                                        # written by the build/modify (default "main.py",
                                        # or whatever solve_fn's returned plan resolves to)
       "checks": [[argv, stdin, expected_substring], ...]}

  Each check is run against the produced system's entrypoint via
  ``harness.system_suite._run_cli`` (Popen + tree-kill on timeout) exactly as the
  creation suite does -- this module does not reimplement that logic (Tenet 3).

- ``answer`` (or any other kind, as a fallback) -- a substring oracle against the
  text ``solve_fn`` returns::

      {"expect_substring": "42"}                  # single required substring, or
      {"expect_all": ["42", "the answer"]}         # every substring must appear

The prompt is the REAL Claude Code task; the acceptance is what "parity/success"
means for it. When the owner later supplies real transcripts, they populate this
format -- this module never invents or assumes the content of a real transcript.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from harness.system_suite import _resolve_entry, _run_cli

try:
    from harness import amortization
    _HAVE_AMORTIZATION = True
except Exception:  # pragma: no cover - amortization is always present in-repo
    _HAVE_AMORTIZATION = False


# #EXT-005-REQ-15 Start
@dataclass
class ShadowTask:
    """One shadow-mode replay task parsed from the transcript JSONL format."""

    task_id: str
    prompt: str
    kind: str
    acceptance: dict = field(default_factory=dict)


def load_transcripts(path: "str | Path") -> "list[ShadowTask]":
    """Parse a shadow-transcript JSONL file into `ShadowTask`s.

    Never raises: a missing/unreadable file returns `[]`; any individual line that
    fails to parse (bad JSON, missing required fields, malformed acceptance) is
    silently skipped -- everything that DOES parse is still returned (Tenet 3: no
    silent whole-run failure over one bad line).
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except Exception:
        return []

    tasks: list[ShadowTask] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                continue
            task_id = str(obj["task_id"])
            prompt = str(obj["prompt"])
            kind = str(obj.get("kind", "build"))
            acceptance = obj.get("acceptance", {})
            if not isinstance(acceptance, dict):
                continue
            tasks.append(ShadowTask(task_id=task_id, prompt=prompt, kind=kind, acceptance=acceptance))
        except Exception:
            continue
    return tasks


def _score_build_task(task: ShadowTask, root: Path, result: Any, python_exe: str) -> bool:
    """Score a build/modify task's produced `root` against its CLI acceptance checks.

    Never raises -- a missing entrypoint, a failing/timing-out check, or a malformed
    acceptance block is a real `False`, never a fabricated pass.
    """
    try:
        checks = task.acceptance.get("checks") or []
        if not checks:
            return False

        entry = task.acceptance.get("entry")
        entry_path: Optional[Path] = None
        if isinstance(entry, str) and entry.strip():
            candidate = root / entry.strip()
            entry_path = candidate if candidate.is_file() else None
        if entry_path is None:
            plan = result if isinstance(result, dict) else None
            resolved = _resolve_entry(plan) if plan else None
            candidate = root / resolved if resolved else root / "main.py"
            entry_path = candidate if candidate.is_file() else None
        if entry_path is None:
            return False

        for check in checks:
            try:
                argv, stdin, expected = check
            except Exception:
                return False
            ok, out = _run_cli(python_exe, entry_path, argv, stdin, root)
            if not ok or expected not in out:
                return False
        return True
    except Exception:
        return False


def _score_answer_task(task: ShadowTask, result: Any) -> bool:
    """Score an answer-kind (or fallback) task via a substring oracle. Never raises."""
    try:
        text = "" if result is None else str(result)
        acceptance = task.acceptance

        expect = acceptance.get("expect_substring")
        if expect is not None:
            return str(expect) in text

        expect_all = acceptance.get("expect_all")
        if isinstance(expect_all, list) and expect_all:
            return all(str(e) in text for e in expect_all)

        return False
    except Exception:
        return False


def run_shadow_replay(
    tasks: "list[ShadowTask]",
    solve_fn: Callable[[str, Path], Any],
    python_exe: "str | None" = None,
) -> dict:
    """Replay `tasks` through the pluggable `solve_fn`, scoring each by its own
    acceptance oracle, and aggregate an overall + per-kind parity rate.

    `solve_fn(prompt, root) -> Any` is the pluggable solve step -- a real caller
    passes something bound to the model (build_system/modify_system/orchestrator);
    tests pass a deterministic stub. This function NEVER raises: any exception from
    `solve_fn` or from scoring scores that task `passed=False` and the replay
    continues with the next task. An empty `tasks` list returns a well-formed
    aggregate with `parity_rate == 0.0` (no divide error).
    """
    python_exe = python_exe or sys.executable
    per_task: list[dict] = []

    collector = None
    if _HAVE_AMORTIZATION:
        try:
            collector = amortization.ScopedCollector()
            collector.__enter__()
        except Exception:
            collector = None

    for task in tasks:
        root = Path(tempfile.mkdtemp(prefix="shadow_replay_"))
        passed = False
        try:
            result = solve_fn(task.prompt, root)
            if task.kind in ("build", "modify"):
                passed = _score_build_task(task, root, result, python_exe)
            else:
                passed = _score_answer_task(task, result)
        except Exception:
            passed = False

        if collector is not None:
            try:
                amortization.record_event(
                    amortization.MODEL_CALL,
                    kind=f"shadow:{task.kind}",
                    meta={"task_id": task.task_id},
                )
            except Exception:
                pass

        try:
            shutil.rmtree(root, ignore_errors=True)
        except Exception:
            pass

        per_task.append({"task_id": task.task_id, "kind": task.kind, "passed": bool(passed)})

    amort_summary = None
    if collector is not None:
        try:
            collector.__exit__(None, None, None)
            amort_summary = collector.ratio()
        except Exception:
            amort_summary = None

    total = len(per_task)
    passed_n = sum(1 for r in per_task if r["passed"])
    parity_rate = (passed_n / total) if total else 0.0

    by_kind: dict = {}
    for r in per_task:
        bucket = by_kind.setdefault(r["kind"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        if r["passed"]:
            bucket["passed"] += 1
    per_kind = {
        k: {"total": v["total"], "passed": v["passed"],
            "rate": (v["passed"] / v["total"] if v["total"] else 0.0)}
        for k, v in by_kind.items()
    }

    out: dict = {
        "total": total,
        "passed": passed_n,
        "parity_rate": parity_rate,
        "per_task": per_task,
        "per_kind": per_kind,
    }
    if amort_summary is not None:
        out["amortization"] = amort_summary
    return out
# #EXT-005-REQ-15 End
