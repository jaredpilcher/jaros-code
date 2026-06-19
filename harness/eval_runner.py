"""Convergence evaluation harness (EXT-005).

Runs the real fix_loop over a suite of isolated coding tasks on gemma2:2b, scores
the pass rate, and appends the result to a durable trend history. The pass-rate
trend is the explicit convergence signal toward Claude-Code-on-Opus-4.8 (PRIME-001).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "evals" / "coding_tasks"
ARTIFACTS = ROOT / ".jaros-data" / "artifacts" / "eval"
HISTORY = ARTIFACTS / "history.jsonl"
MODEL = os.environ.get("OLLAMA_MODEL", "gemma2:2b")


# #EXT-005-REQ-1 Start
@dataclass
class Task:
    id: str
    instruction: str
    target: str
    test_cmd: str
    files: dict


def load_tasks(tasks_dir: Path = TASKS_DIR) -> list[Task]:
    """Load every *.json task definition, sorted by id for deterministic order."""
    tasks = []
    for path in sorted(tasks_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks.append(Task(id=data["id"], instruction=data["instruction"],
                          target=data["target"], test_cmd=data["test_cmd"],
                          files=data["files"]))
    return tasks


def setup_task(task: Task, workdir: Path) -> Path:
    """Materialize a task's files into an isolated working dir; return the target."""
    for name, content in task.files.items():
        (workdir / name).write_text(content, encoding="utf-8")
    return workdir / task.target
# #EXT-005-REQ-1 End


# #EXT-005-REQ-2 Start
def run_suite(max_iters: int = 3, verbose: bool = False) -> dict:
    """Run every task through fix_loop in isolation; return a scorecard dict."""
    from harness.coding_loop import fix_loop  # local import: sets up env first

    tasks = load_tasks()
    started = time.time()
    print(f"\n\033[1m jaros-code eval \033[0m  {len(tasks)} tasks  model={MODEL}  max_iters={max_iters}")
    print("   " + "-" * 56)

    per_task = []
    for task in tasks:
        with tempfile.TemporaryDirectory(prefix=f"jcode-{task.id}-") as tmp:
            workdir = Path(tmp)
            target = setup_task(task, workdir)
            t0 = time.time()
            try:
                res = fix_loop(str(target), task.instruction, task.test_cmd,
                               max_iters=max_iters, cwd=str(workdir), verbose=verbose)
                solved, attempts = res.success, res.attempts
            except Exception as exc:  # a single task failure never sinks the suite
                solved, attempts = False, max_iters
                print(f"    \033[31m{task.id}: runner error: {exc}\033[0m")
            secs = round(time.time() - t0, 1)
            mark = "\033[32mPASS\033[0m" if solved else "\033[31mFAIL\033[0m"
            print(f"   {mark}  {task.id:<16} attempts={attempts}  {secs}s")
            per_task.append({"id": task.id, "solved": solved, "attempts": attempts, "secs": secs})

    solved_n = sum(1 for t in per_task if t["solved"])
    total = len(per_task)
    scorecard = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "maxIters": max_iters,
        "passRate": round(solved_n / total, 4) if total else 0.0,
        "solved": solved_n,
        "total": total,
        "elapsedSec": round(time.time() - started, 1),
        "perTask": per_task,
    }
    _print_scorecard(scorecard)
    _persist(scorecard)
    return scorecard


def _print_scorecard(sc: dict) -> None:
    print("   " + "-" * 56)
    pct = int(sc["passRate"] * 100)
    bar = "#" * (pct // 5) + "." * (20 - pct // 5)
    print(f"   SCORECARD  pass {sc['solved']}/{sc['total']}  [{bar}] {pct}%   {sc['elapsedSec']}s")
    print(f"   model={sc['model']}  (target: Claude-Code on Opus-4.8 = 100%)\n")
# #EXT-005-REQ-2 End


# #EXT-005-REQ-3 Start
def _persist(scorecard: dict) -> None:
    """Write the full scorecard and append one trend line to history.jsonl."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stamp = scorecard["timestamp"].replace(":", "").replace("-", "")[:15]
    (ARTIFACTS / f"scorecard-{stamp}.json").write_text(
        json.dumps(scorecard, indent=2), encoding="utf-8")
    summary = {k: scorecard[k] for k in
               ("timestamp", "model", "passRate", "solved", "total", "elapsedSec")}
    with open(HISTORY, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")


def history() -> list[dict]:
    """Return the recorded trend (one entry per run)."""
    if not HISTORY.is_file():
        return []
    return [json.loads(line) for line in HISTORY.read_text(encoding="utf-8").splitlines() if line.strip()]
# #EXT-005-REQ-3 End
