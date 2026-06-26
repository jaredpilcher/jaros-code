"""Real public benchmark adapter: MBPP (EXT-005 / REQ-5).

Mostly Basic Python Problems — 974 short tasks, each a natural-language description plus
a few `assert` tests. Mapped to the same isolated, exit-code-honest pytest Task the rest
of the harness uses, then run through the real fix_loop on Gemma 4 2B (`e2b`).

Dataset is NOT vendored. Place the official `mbpp.jsonl` at `evals/benchmarks/mbpp.jsonl`
(from https://github.com/google-research/google-research, `mbpp/mbpp.jsonl`). Absent →
the runner says so, never a silent pass (Tenet 3).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from harness.eval_runner import Task, run_task_list

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "benchmarks" / "mbpp.jsonl"
MBPP_TIER = 4

_OBTAIN = (
    "MBPP dataset not found. Obtain it (no silent pass):\n"
    "  1. Download mbpp/mbpp.jsonl from https://github.com/google-research/google-research\n"
    f"  2. Place it at {DATASET}\n"
)


def _read_problems() -> list[dict]:
    if not DATASET.is_file():
        raise FileNotFoundError(_OBTAIN)
    return [json.loads(ln) for ln in DATASET.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _entry_point(test_list: list[str]) -> str | None:
    for t in test_list:
        m = re.search(r"assert\s+(\w+)\s*\(", t)
        if m:
            return m.group(1)
    return None


def problem_to_task(p: dict) -> Task | None:
    entry = _entry_point(p.get("test_list", []))
    if not entry:
        return None
    setup = (p.get("test_setup_code") or "").strip()
    asserts = "\n".join("    " + a for a in p["test_list"])
    test_file = (
        (setup + "\n" if setup else "")
        + f"from solution import {entry}\n\n\n"
        + f"def test_mbpp():\n{asserts}\n"
    )
    # Stub only fixes the name the test imports; the agent writes the real signature/body
    # from the description + the asserts (which pin the contract).
    solution = f"def {entry}(*args, **kwargs):\n    raise NotImplementedError\n"
    instruction = (
        p["text"].strip()
        + "\n\nThe function must be named "
        + f"`{entry}` and pass these tests:\n"
        + "\n".join(p["test_list"])
    )
    # Target the real test explicitly: when the entry point is named like `test_duplicate`, the
    # test's `from solution import test_duplicate` makes pytest COLLECT that imported function as a
    # test (called with no args -> error -> spurious suite failure). `::test_mbpp` runs only our test.
    return Task(id=f"mbpp_{p['task_id']}", instruction=instruction, target="solution.py",
                test_cmd="python -m pytest -q test_solution.py::test_mbpp",
                files={"solution.py": solution, "test_solution.py": test_file},
                tier=MBPP_TIER)


def run_mbpp(limit: int | None = 20, max_iters: int = 3, verbose: bool = False,
             workers: int = 1) -> dict:
    problems = _read_problems()
    if limit is not None:
        problems = problems[:limit]
    tasks = [t for t in (problem_to_task(p) for p in problems) if t is not None]
    return run_task_list(tasks, max_iters=max_iters, verbose=verbose, suite="mbpp", workers=workers)
