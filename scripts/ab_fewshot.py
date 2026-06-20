"""Next lever: few-shot demonstration. Prepend 2 worked spec->implementation examples
to the implement instruction so gemma2:2b copies the pattern/idiom. Run on the SAME
HumanEval[0:18] slice; compare to the known baseline from the best-of-N A/B
(baseline solved: 0,2,3,4,5,7,8,9,12,13,14,15 = 12/18). Same budget (max_iters=6)."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import fix_loop
from harness.humaneval import _read_problems, problem_to_task

BASELINE = {0, 2, 3, 4, 5, 7, 8, 9, 12, 13, 14, 15}  # from blevwn42n
SLICE = range(0, 18)

FEWSHOT = (
    "Study these two examples of implementing a Python function from its spec, then do "
    "the same for the real task.\n\n"
    "EXAMPLE 1\nSPEC: Return the number of vowels in string s (case-insensitive).\n"
    "CODE:\ndef count_vowels(s):\n    return sum(1 for c in s.lower() if c in \"aeiou\")\n\n"
    "EXAMPLE 2\nSPEC: Return the running maximum of a list nums (element i is the max of "
    "nums[0..i]); empty list returns [].\n"
    "CODE:\ndef running_max(nums):\n    out, m = [], None\n    for n in nums:\n"
    "        m = n if m is None else max(m, n)\n        out.append(m)\n    return out\n\n"
    "Work carefully and handle edge cases. Now the REAL task:\n"
)

problems = _read_problems()
solved, rows = 0, []
for i in SLICE:
    task = problem_to_task(problems[i])
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        for n, b in task.files.items():
            (dp / n).write_text(b, encoding="utf-8", newline="\n")
        ok = fix_loop(str(dp / task.target), FEWSHOT + task.instruction, task.test_cmd,
                      max_iters=6, cwd=str(dp), verbose=False).success
    solved += ok
    base = i in BASELINE
    rows.append((i, base, ok))
    print(f"  HumanEval_{i:<2} baseline={'P' if base else '.'}  fewshot={'P' if ok else '.'}", flush=True)

t = len(rows)
print(f"\n===== few-shot vs baseline on HumanEval[0:18] =====")
print(f"  baseline: {len(BASELINE & set(SLICE))}/{t}")
print(f"  few-shot: {solved}/{t}")
print(f"  delta: {solved - len(BASELINE & set(SLICE)):+d}")
print("  flips (few-shot solved, baseline didn't):", [f'HE_{i}' for i, b, o in rows if o and not b])
print("  regressions (baseline solved, few-shot didn't):", [f'HE_{i}' for i, b, o in rows if b and not o])
