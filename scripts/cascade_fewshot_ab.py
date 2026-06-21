"""Acts on the decomposition finding: few-shot HURT this 2B single-shot, and the cascade uses
_FEWSHOT in 2 of its 6 strategies. Does an ALL-zero-shot cascade (more zero-shot temp diversity
in those 2 slots) beat the current mix on the full test-gated within-budget pass rate?

A/B via monkeypatching coding_loop._CASCADE_STRATEGIES (read at runtime) — no permanent change.
HumanEval[::6] (difficulty-spanning), max_iters=6, workers=4 (parallel eval). Same tasks both arms.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness.coding_loop as cl
from harness.humaneval import _read_problems, problem_to_task
from harness.eval_runner import run_task_list

tasks = [problem_to_task(p) for p in _read_problems()[::6]]
ORIG = list(cl._CASCADE_STRATEGIES)
# replace the 2 _FEWSHOT slots with extra zero-shot temperatures (body, no prefix)
ZEROSHOT = [("body", "", 0.0), ("body", "", 0.3), ("body", "", 0.5),
            ("body", "", 0.7), ("body", "", 0.9), ("body", "", 1.1)]

print(f"ARM A: CURRENT cascade (2/6 use _FEWSHOT), {len(tasks)} tasks, workers=4", flush=True)
t0 = time.time()
a = run_task_list(tasks, max_iters=6, workers=4, suite="he-current")
ta = time.time() - t0

print(f"\nARM B: ZERO-SHOT-only cascade, {len(tasks)} tasks, workers=4", flush=True)
cl._CASCADE_STRATEGIES = ZEROSHOT
t0 = time.time()
b = run_task_list(tasks, max_iters=6, workers=4, suite="he-zeroshot")
tb = time.time() - t0
cl._CASCADE_STRATEGIES = ORIG

print(f"\n=== CASCADE FEW-SHOT A/B (HumanEval[::6], {len(tasks)} tasks, max_iters=6, workers=4) ===")
print(f"current (2/6 fewshot):  {a['solved']}/{a['total']} = {a['solved']/a['total']*100:.0f}% in {ta:.0f}s")
print(f"zero-shot-only cascade: {b['solved']}/{b['total']} = {b['solved']/b['total']*100:.0f}% in {tb:.0f}s")
print(f"delta (zeroshot - current): {b['solved']-a['solved']:+d} problems")
