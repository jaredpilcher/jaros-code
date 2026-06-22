"""Multi-step agentic eval (EXT-009 REQ-6): the HONEST metric for the agentic layer.

HumanEval/MBPP are single-function benchmarks — they cannot measure whether the
agent can PLAN a multi-step fix: locate the fault, read the file, apply the fix,
run the tests. This eval seeds a small repo with a fault spanning >=2 files, gives
``agent_loop`` a high-level NL request, and scores ``solved`` iff pytest is green
after the loop exits. It is a local, zero-paid-API analogue of SWE-bench: the eval
drives the real ``agent_loop`` (model plans; deterministic tools act).

Three scenario classes are covered:
  1. Exception fault (AttributeError traceback names the file) — "easiest" for the model.
  2. Logic fault (wrong operator; no named traceback) — requires reasoning about the code.
  3. Cross-module import chain — the failing test imports through an intermediate module;
     the model must locate the root cause in the leaf file.

``run_agentic_eval`` uses the real model (gemma via llama.cpp / Ollama). The CI test
(``tests/test_agentic_eval.py``) injects a scripted planner so it is deterministic
and model-free.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# #EXT-009-REQ-6 Start

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
# Each scenario provides:
#   name     – short slug for reporting
#   request  – high-level NL request given to agent_loop (no file names)
#   files    – dict[relative_path -> content] to seed the repo
# ---------------------------------------------------------------------------
SCENARIOS = [
    {   # ---- SCENARIO 1: exception fault (AttributeError names the file) ----
        "name": "exception_fault",
        "request": "The tests are failing. Find and fix the bug.",
        "files": {
            "textutil.py": (
                "def words(s):\n"
                "    return s.spliit(' ')  # BUG: spliit -> split\n"
            ),
            "app.py": (
                "from textutil import words\n\n"
                "def count_words(s):\n"
                "    return len(words(s))\n"
            ),
            "test_app.py": (
                "from app import count_words\n\n"
                "def test_count_words():\n"
                "    assert count_words('hello world') == 2\n"
            ),
        },
    },
    {   # ---- SCENARIO 2: logic fault (wrong operator; no traceback hint) ----
        "name": "logic_fault",
        "request": "Tests are red. Find the bug and fix it.",
        "files": {
            "math_helpers.py": (
                "def double(x):\n"
                "    return x + x  # OK\n\n"
                "def square(x):\n"
                "    return x + x  # BUG: should be x * x\n"
            ),
            "processor.py": (
                "from math_helpers import square\n\n"
                "def process(values):\n"
                "    return [square(v) for v in values]\n"
            ),
            "test_processor.py": (
                "from processor import process\n\n"
                "def test_process():\n"
                "    assert process([2, 3, 4]) == [4, 9, 16]\n"
            ),
        },
    },
    {   # ---- SCENARIO 3: cross-module import chain (leaf is the culprit) ----
        "name": "import_chain_fault",
        "request": "The test suite is failing. Locate the root cause and fix it.",
        "files": {
            "core.py": (
                "def increment(x):\n"
                "    return x - 1  # BUG: should be x + 1\n"
            ),
            "middleware.py": (
                "from core import increment\n\n"
                "def step(x):\n"
                "    return increment(x)\n"
            ),
            "service.py": (
                "from middleware import step\n\n"
                "def run_pipeline(values):\n"
                "    return [step(v) for v in values]\n"
            ),
            "test_service.py": (
                "from service import run_pipeline\n\n"
                "def test_run_pipeline():\n"
                "    assert run_pipeline([1, 2, 3]) == [2, 3, 4]\n"
            ),
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pytest_passes(repo_dir: str) -> bool:
    """Return True iff ``pytest -q`` exits 0 in repo_dir."""
    r = subprocess.run(
        ["python", "-m", "pytest", "-q", "--tb=short"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return r.returncode == 0


def _seed_repo(files: dict[str, str], tmp_dir: str) -> None:
    """Write scenario files into tmp_dir, creating subdirectories as needed."""
    for rel, content in files.items():
        fp = Path(tmp_dir) / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Main eval runner
# ---------------------------------------------------------------------------

def run_agentic_eval(verbose: bool = False, planner=None, persist: bool = True) -> dict:
    """Run all SCENARIOS end-to-end through agent_loop; return a scorecard dict.

    Uses the REAL model (gemma via llama.cpp) by default. `planner` is injectable so the CI test
    can drive the loop deterministically (model-free); `persist=False` skips the history write so
    tests don't pollute the trend.
    """
    from harness.agent_loop import agent_loop

    results = []
    started = time.time()

    for sc in SCENARIOS:
        with tempfile.TemporaryDirectory(prefix=f"jcode-agentic-{sc['name']}-") as tmp:
            _seed_repo(sc["files"], tmp)

            # Confirm tests are initially failing (honest: we seed a broken repo)
            pre_ok = _pytest_passes(tmp)
            if pre_ok:
                # Scenario seeding error — bug is not actually present
                results.append({"name": sc["name"], "solved": False,
                                 "note": "SCENARIO_ERROR: tests passed before fix"})
                print(f"  FAIL {sc['name']:25} (scenario error: pre-run was green)", flush=True)
                continue

            if planner is not None:                  # CI test: scripted planner -> free-form mechanics
                loop_result = agent_loop(sc["request"], tmp, planner=planner, max_steps=8, verbose=verbose)
            else:                                     # model run: measure the DEFAULT repair flow (/agent)
                from harness.spec_loop import spec_driven_loop
                r = spec_driven_loop(sc["request"], tmp, verbose=verbose)
                loop_result = {"steps_run": "-", "done": bool(r.get("solved"))}
            solved = _pytest_passes(tmp)
            results.append({
                "name": sc["name"],
                "solved": solved,
                "steps_run": loop_result.get("steps_run", 0),
                "loop_done": loop_result.get("done", False),
            })
            mark = "PASS" if solved else "FAIL"
            print(f"  {mark} {sc['name']:25} steps={loop_result.get('steps_run', '?')} "
                  f"loop_done={loop_result.get('done')}", flush=True)

    solved_n = sum(1 for r in results if r["solved"])
    total = len(results)
    elapsed = round(time.time() - started, 1)
    print(f"\n=== agentic eval: {solved_n}/{total} = {solved_n / total * 100:.0f}% ===")

    scorecard = {
        "suite": "agentic",
        "solved": solved_n,
        "total": total,
        "perTask": results,
    }

    if persist:
        _append_history(solved_n, total, elapsed)
    return scorecard


# ---------------------------------------------------------------------------
# Trend history append
# ---------------------------------------------------------------------------

def _append_history(solved: int, total: int, elapsed_sec: float) -> None:
    """Append one trend line to history.jsonl with suite='agentic'.

    The format mirrors ``eval_runner._persist``'s summary rows exactly so
    ``/trend`` renders agentic progress alongside the other suite results.
    """
    from harness.eval_runner import HISTORY, ARTIFACTS
    from harness.coding_loop import _active_model_label
    from harness.report import census

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suite": "agentic",
        "model": _active_model_label(),
        "passRate": round(solved / total, 4) if total else 0.0,
        "solved": solved,
        "total": total,
        "elapsedSec": elapsed_sec,
        "census": census(),
    }
    with open(HISTORY, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")

# #EXT-009-REQ-6 End


if __name__ == "__main__":
    run_agentic_eval(verbose=True)
