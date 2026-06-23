"""Real public benchmark adapter: HumanEval (EXT-005 / REQ-5).

Converts each HumanEval problem into the same isolated, exit-code-honest task the
authored suite uses, then runs it through the real fix_loop on gemma2:2b. This makes
our yardstick an external, recognized one — the bar the Prime Directive demands.

The dataset is NOT vendored. Place the official `HumanEval.jsonl` at
`evals/benchmarks/HumanEval.jsonl` (from https://github.com/openai/human-eval,
`data/HumanEval.jsonl.gz`, gunzipped). If it is absent the runner says so — never a
silent pass (Tenet 3).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from harness.eval_runner import Task, run_task_list

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "benchmarks" / "HumanEval.jsonl"
DATASET_GZ = ROOT / "evals" / "benchmarks" / "HumanEval.jsonl.gz"

HUMANEVAL_TIER = 4  # real external benchmark sits above the authored tiers

_OBTAIN = (
    "HumanEval dataset not found. Obtain it (no silent pass):\n"
    "  1. Download data/HumanEval.jsonl.gz from https://github.com/openai/human-eval\n"
    f"  2. Place it at {DATASET_GZ}  (or gunzip to {DATASET})\n"
)


def _read_problems() -> list[dict]:
    if DATASET.is_file():
        lines = DATASET.read_text(encoding="utf-8").splitlines()
    elif DATASET_GZ.is_file():
        with gzip.open(DATASET_GZ, "rt", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    else:
        raise FileNotFoundError(_OBTAIN)
    return [json.loads(line) for line in lines if line.strip()]


def problem_to_task(p: dict) -> Task:
    """Map one HumanEval problem to an isolated, pytest-checked Task."""
    entry = p["entry_point"]
    # solution.py: the given prompt (signature + docstring) plus a stub body the
    # agent must replace with a correct implementation.
    solution = p["prompt"]
    if not solution.endswith("\n"):
        solution += "\n"
    solution += "    pass\n"
    # test_solution.py: the official check() plus a pytest entry that runs it.
    test_file = (
        f"from solution import {entry}\n\n"
        f"{p['test']}\n\n"
        f"def test_humaneval():\n    check({entry})\n"
    )
    return Task(
        id=p["task_id"].replace("/", "_"),
        instruction=(
            "Implement the function body so it satisfies its docstring and passes the "
            "hidden tests. Keep the given signature; replace the `pass` stub with a "
            "correct implementation."
        ),
        target="solution.py",
        # Target our test explicitly: a `test_*` entry point would otherwise be collected by pytest
        # via the test's `from solution import ...` and spuriously fail (see mbpp.py). Defensive.
        test_cmd="python -m pytest -q test_solution.py::test_humaneval",
        files={"solution.py": solution, "test_solution.py": test_file},
        tier=HUMANEVAL_TIER,
    )


def run_humaneval(limit: int | None = 20, max_iters: int = 3, verbose: bool = False,
                  workers: int = 1) -> dict:
    """Run the first ``limit`` HumanEval problems (or all) through the harness."""
    problems = _read_problems()
    if limit is not None:
        problems = problems[:limit]
    tasks = [problem_to_task(p) for p in problems]
    return run_task_list(tasks, max_iters=max_iters, verbose=verbose, suite="humaneval", workers=workers)
