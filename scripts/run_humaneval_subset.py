"""Representative HumanEval subset on the Jetson, ROBUST to the device being moved.

Samples every 3rd problem across all 164 (≈55 problems spanning easy→hard, unlike the
first-50 which are all easy), reports pass@1 (attempt 1) AND within-3-attempts.

Resilience (the lesson from the hung full run): before each problem it health-gates the
endpoint — if the Jetson is down (moved/rebooting) it WAITS and resumes, instead of
hanging or failing. The per-call socket timeout (LLAMACPP_TIMEOUT_S, default 60s) bounds
any single stalled request.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import fix_loop
from harness.humaneval import _read_problems, problem_to_task
from harness.llamacpp_client import health

STEP = int(sys.argv[1]) if len(sys.argv) > 1 else 3       # every Nth problem
OUT = ROOT / ".jaros-data" / "artifacts" / "eval" / "humaneval_subset.json"


def wait_for_endpoint() -> None:
    """Block until the Jetson answers — survives a move/reboot instead of hanging."""
    while not health().get("ok"):
        print("  [endpoint down — waiting for the Jetson...]", flush=True)
        time.sleep(15)


problems = _read_problems()
idxs = list(range(0, len(problems), STEP))
rows = []
t_start = time.time()
for i in idxs:
    wait_for_endpoint()
    task = problem_to_task(problems[i])
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        for n, b in task.files.items():
            (dp / n).write_text(b, encoding="utf-8", newline="\n")
        t0 = time.time()
        try:
            r = fix_loop(str(dp / task.target), task.instruction, task.test_cmd,
                         max_iters=3, cwd=str(d), verbose=False)
            solved, attempts = r.success, r.attempts
        except Exception as exc:
            solved, attempts = False, 0
            print(f"  {task.id}: error {exc}", flush=True)
    rows.append({"id": task.id, "solved": solved, "attempts": attempts})
    print(f"  {'PASS' if solved else 'FAIL'} {task.id:14} attempts={attempts}  {time.time()-t0:.0f}s", flush=True)

n = len(rows)
p1 = sum(1 for r in rows if r["solved"] and r["attempts"] == 1)
w3 = sum(1 for r in rows if r["solved"])
summary = {"suite": "humaneval-subset", "step": STEP, "n": n,
           "pass_at_1": p1, "pass_at_1_rate": round(p1 / n, 4),
           "within_3": w3, "within_3_rate": round(w3 / n, 4),
           "elapsed_sec": round(time.time() - t_start, 1), "model": "gemma-4-e2b", "rows": rows}
OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(f"\n===== HumanEval subset (every {STEP}th, {n} problems spanning easy→hard) on gemma-4-e2b =====")
print(f"  pass@1 (attempt 1):      {p1}/{n} = {p1/n*100:.1f}%")
print(f"  within-3-attempts:       {w3}/{n} = {w3/n*100:.1f}%")
print(f"  elapsed {summary['elapsed_sec']}s -> {OUT}")
