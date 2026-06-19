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
    tier: int = 1


def load_tasks(tasks_dir: Path = TASKS_DIR) -> list[Task]:
    """Load every *.json task definition, sorted by (tier, id) for a difficulty ramp."""
    tasks = []
    for path in sorted(tasks_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks.append(Task(id=data["id"], instruction=data["instruction"],
                          target=data["target"], test_cmd=data["test_cmd"],
                          files=data["files"], tier=int(data.get("tier", 1))))
    tasks.sort(key=lambda t: (t.tier, t.id))
    return tasks


def setup_task(task: Task, workdir: Path) -> Path:
    """Materialize a task's files into an isolated working dir; return the target."""
    for name, content in task.files.items():
        (workdir / name).write_text(content, encoding="utf-8")
    return workdir / task.target
# #EXT-005-REQ-1 End


# #EXT-005-REQ-2 Start
def run_suite(max_iters: int = 3, verbose: bool = False) -> dict:
    """Run the authored coding-task suite through fix_loop in isolation."""
    return run_task_list(load_tasks(), max_iters=max_iters, verbose=verbose, suite="authored")


def run_task_list(tasks: list[Task], *, max_iters: int = 3, verbose: bool = False,
                  suite: str = "authored") -> dict:
    """Run any task list through fix_loop in isolation; return a scorecard dict."""
    from harness.coding_loop import fix_loop  # local import: sets up env first

    started = time.time()
    print(f"\n\033[1m jaros-code eval \033[0m  suite={suite}  {len(tasks)} tasks  model={MODEL}  max_iters={max_iters}")
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
            print(f"   {mark}  t{task.tier} {task.id:<18} attempts={attempts}  {secs}s")
            per_task.append({"id": task.id, "tier": task.tier, "solved": solved,
                             "attempts": attempts, "secs": secs})

    solved_n = sum(1 for t in per_task if t["solved"])
    total = len(per_task)
    per_tier, frontier, too_easy = _tier_stats(per_task)
    scorecard = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suite": suite,
        "model": MODEL,
        "maxIters": max_iters,
        "passRate": round(solved_n / total, 4) if total else 0.0,
        "solved": solved_n,
        "total": total,
        "perTier": per_tier,
        "frontierTier": frontier,
        "tooEasy": too_easy,
        "elapsedSec": round(time.time() - started, 1),
        "perTask": per_task,
    }
    _print_scorecard(scorecard)
    _persist(scorecard)
    return scorecard


# #EXT-005-REQ-4 Start
def _tier_stats(per_task: list[dict], mastery: float = 1.0):
    """Per-tier pass rate, the frontier tier (lowest not mastered), and too-easy flag.

    A tier is "mastered" when its pass rate >= ``mastery`` (default: all tasks pass).
    The frontier is the lowest tier not yet mastered — where the harness should focus.
    If every tier is mastered the suite is too easy and must be hardened (PRIME-001).
    """
    tiers = sorted({t["tier"] for t in per_task})
    per_tier = {}
    for tier in tiers:
        rows = [t for t in per_task if t["tier"] == tier]
        solved = sum(1 for t in rows if t["solved"])
        per_tier[str(tier)] = {"solved": solved, "total": len(rows),
                               "passRate": round(solved / len(rows), 4)}
    frontier = None
    for tier in tiers:
        if per_tier[str(tier)]["passRate"] < mastery:
            frontier = tier
            break
    too_easy = frontier is None and bool(tiers)
    return per_tier, frontier, too_easy


def _print_scorecard(sc: dict) -> None:
    print("   " + "-" * 56)
    for tier in sorted(sc["perTier"], key=int):
        t = sc["perTier"][tier]
        pct = int(t["passRate"] * 100)
        print(f"   tier {tier}: {t['solved']}/{t['total']}  {pct:>3}%")
    pct = int(sc["passRate"] * 100)
    bar = "#" * (pct // 5) + "." * (20 - pct // 5)
    print(f"   SCORECARD  pass {sc['solved']}/{sc['total']}  [{bar}] {pct}%   {sc['elapsedSec']}s")
    if sc["tooEasy"]:
        print("   \033[33m[!] every tier mastered — suite is TOO EASY; add harder tasks\033[0m")
    else:
        print(f"   frontier tier = {sc['frontierTier']}  (focus harder; ratchet only goes up)")
    print(f"   model={sc['model']}  (target: Claude-Code on Opus-4.8 = 100%)\n")
# #EXT-005-REQ-4 End
# #EXT-005-REQ-2 End


# #EXT-005-REQ-3 Start
def _persist(scorecard: dict) -> None:
    """Write the full scorecard and append one trend line to history.jsonl."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stamp = scorecard["timestamp"].replace(":", "").replace("-", "")[:15]
    (ARTIFACTS / f"scorecard-{stamp}.json").write_text(
        json.dumps(scorecard, indent=2), encoding="utf-8")
    summary = {k: scorecard[k] for k in
               ("timestamp", "suite", "model", "passRate", "solved", "total", "elapsedSec")}
    with open(HISTORY, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")


def history() -> list[dict]:
    """Return the recorded trend (one entry per run)."""
    if not HISTORY.is_file():
        return []
    return [json.loads(line) for line in HISTORY.read_text(encoding="utf-8").splitlines() if line.strip()]
# #EXT-005-REQ-3 End
