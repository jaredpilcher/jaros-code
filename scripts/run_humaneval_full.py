"""Honest full HumanEval run: all 164 problems, reporting BOTH the pass@1 proxy
(solved on attempt 1, no test visibility) and the within-3-attempts rate (which leaks
test cases on retry, so it is NOT comparable to published pass@1). Dumps per-task
results so the number is auditable."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.humaneval import run_humaneval  # noqa: E402

OUT = ROOT / ".jaros-data" / "artifacts" / "eval" / "humaneval_full.json"

t0 = time.time()
sc = run_humaneval(limit=None, max_iters=3, verbose=True)
results = sc.get("results", [])
n = len(results)
within3 = sum(1 for r in results if r.get("solved"))
pass1 = sum(1 for r in results if r.get("solved") and r.get("attempts") == 1)
summary = {
    "suite": "humaneval-full",
    "n": n,
    "pass_at_1_proxy": round(pass1 / n, 4) if n else 0,
    "pass_at_1_count": pass1,
    "within_3_attempts": round(within3 / n, 4) if n else 0,
    "within_3_count": within3,
    "elapsed_sec": round(time.time() - t0, 1),
    "results": results,
}
OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("\n===== HUMANEVAL FULL (164) =====")
print(f"pass@1 proxy (attempt 1, no test visibility): {pass1}/{n} = {summary['pass_at_1_proxy']*100:.1f}%")
print(f"within 3 attempts (leaks test cases on retry): {within3}/{n} = {summary['within_3_attempts']*100:.1f}%")
print(f"elapsed {summary['elapsed_sec']}s  ->  wrote {OUT}")
