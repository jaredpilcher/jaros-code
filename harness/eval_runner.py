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
from harness.coding_loop import _active_model_label
MODEL = _active_model_label()  # the model actually serving inference (honest label)


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
                  suite: str = "authored", workers: int = 1) -> dict:
    """Run any task list through fix_loop in isolation; return a scorecard dict. `workers>1`
    runs tasks CONCURRENTLY — each in its own temp dir, and the model calls (the slow part)
    batch on the inference server's parallel slots (~1.8x throughput measured on the Jetson at
    4-wide). Each task is independent, so there's no wasted compute; verbose is forced off under
    concurrency so transcripts don't interleave."""
    from harness.coding_loop import fix_loop, reset_tool_usage, tool_usage, wiring_usage  # local: sets env first
    from harness.ollama_client import model_call_stats, reset_model_calls

    reset_tool_usage()
    reset_model_calls()
    started = time.time()
    print(f"\n\033[1m jaros-code eval \033[0m  suite={suite}  {len(tasks)} tasks  model={MODEL}  "
          f"max_iters={max_iters}  workers={workers}")
    print("   " + "-" * 56)

    def _run_one(task: Task) -> dict:
        with tempfile.TemporaryDirectory(prefix=f"jcode-{task.id}-") as tmp:
            workdir = Path(tmp)
            target = setup_task(task, workdir)
            t0 = time.time()
            try:
                res = fix_loop(str(target), task.instruction, task.test_cmd, max_iters=max_iters,
                               cwd=str(workdir), verbose=verbose and workers == 1)
                solved, attempts = res.success, res.attempts
            except Exception as exc:  # a single task failure never sinks the suite
                solved, attempts = False, max_iters
                print(f"    \033[31m{task.id}: runner error: {exc}\033[0m", flush=True)
            secs = round(time.time() - t0, 1)
            mark = "\033[32mPASS\033[0m" if solved else "\033[31mFAIL\033[0m"
            print(f"   {mark}  t{task.tier} {task.id:<18} attempts={attempts}  {secs}s", flush=True)
            return {"id": task.id, "tier": task.tier, "solved": solved,
                    "attempts": attempts, "secs": secs}

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        # Batched requests run ~workers x slower per-call, so the per-request model timeout must
        # scale up or long generations (e.g. MBPP whole-file) spuriously time out. Raise it for
        # the duration of the concurrent run, then restore.
        base_to = os.environ.get("LLAMACPP_TIMEOUT_S", "90")
        os.environ["LLAMACPP_TIMEOUT_S"] = str(int(float(base_to) * workers))
        try:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                per_task = list(ex.map(_run_one, tasks))   # order preserved; each task is isolated
        finally:
            os.environ["LLAMACPP_TIMEOUT_S"] = base_to
    else:
        per_task = [_run_one(task) for task in tasks]

    solved_n = sum(1 for t in per_task if t["solved"])
    total = len(per_task)
    per_tier, frontier, too_easy = _tier_stats(per_task)
    from harness.report import census  # growth census (agents/tools/evals/specs)
    cen = census()
    wu, tu = wiring_usage(), tool_usage()
    tool_fires = sum(tu.values())
    # Orchestration/wiring quality is a tracked success axis (not just agent/tool COUNT):
    # Jaros records every agent->tool decision, so the wiring graph is measurable. LEVERAGE
    # (solved tasks per agent) rising at a flat agent count IS better orchestration; richer
    # composition shows as more distinct wired edges and tool fires per solved task.
    orchestration = {
        "wiringEdges": len(wu),                                              # distinct agent->tool edges fired
        "toolFires": tool_fires,                                             # total deterministic tool executions
        "decisionsPerSolved": round(tool_fires / solved_n, 2) if solved_n else 0.0,
        "leverage": round(solved_n / cen["agents"], 3) if cen.get("agents") else 0.0,  # capability per agent
    }
    scorecard = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suite": suite,
        "model": MODEL,
        "census": cen,
        "maxIters": max_iters,
        "passRate": round(solved_n / total, 4) if total else 0.0,
        "solved": solved_n,
        "total": total,
        "perTier": per_tier,
        "frontierTier": frontier,
        "tooEasy": too_easy,
        "toolUsage": tu,
        "wiringUsage": wu,
        "orchestration": orchestration,
        "modelCalls": model_call_stats(),
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
    summary["census"] = scorecard.get("census")
    summary["orchestration"] = scorecard.get("orchestration")  # wiring quality trends too
    with open(HISTORY, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")


def history() -> list[dict]:
    """Return the recorded trend (one entry per run)."""
    if not HISTORY.is_file():
        return []
    return [json.loads(line) for line in HISTORY.read_text(encoding="utf-8").splitlines() if line.strip()]
# #EXT-005-REQ-3 End
