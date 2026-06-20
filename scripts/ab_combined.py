"""Rigorous out-of-sample verdict on a FRESH slice (HumanEval[18:40], never measured):
  BASELINE = fix_loop (6 attempts, seq+feedback)
  COMBINED = few-shot demonstration prompt + best-of-N (6 diverse samples, test-select)
The combined lever is the full thesis: a better-conditioned model proposes many, the
deterministic test selects. Head-to-head, same problems, same budget -> honest delta."""
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import Runtime, build_llm, fix_loop, _load_agent, create_decision
from harness.humaneval import _read_problems, problem_to_task

SLICE = range(18, 40)
N = 6
TEMPS = [0.0, 0.3, 0.5, 0.7, 0.9, 1.1]
FEWSHOT = (
    "Study these two examples of implementing a Python function from its spec, then do "
    "the same for the real task.\n\n"
    "EXAMPLE 1\nSPEC: Return the number of vowels in string s (case-insensitive).\n"
    "CODE:\ndef count_vowels(s):\n    return sum(1 for c in s.lower() if c in \"aeiou\")\n\n"
    "EXAMPLE 2\nSPEC: Return the running maximum of a list nums; empty list returns [].\n"
    "CODE:\ndef running_max(nums):\n    out, m = [], None\n    for n in nums:\n"
    "        m = n if m is None else max(m, n)\n        out.append(m)\n    return out\n\n"
    "Work carefully and handle edge cases. Now the REAL task:\n"
)


def materialize(task, d):
    dp = Path(d)
    for n, b in task.files.items():
        (dp / n).write_text(b, encoding="utf-8", newline="\n")
    return str(dp / task.target)


def combined(target, instruction, test_cmd, cwd):
    rt = Runtime()
    rw = _load_agent("rewriter_agent.py", build_llm())
    stub = Path(target).read_text(encoding="utf-8")
    for k in range(N):
        Path(target).write_text(stub, encoding="utf-8", newline="\n")
        [edit] = rw.decide({"path": target, "content": stub, "instruction": FEWSHOT + instruction,
                            "symbols": "", "feedback": "", "temperature": TEMPS[k % len(TEMPS)],
                            "seed": k + 1})
        if edit.type not in ("code.write_file", "code.apply_patch"):
            continue
        try:
            rt.apply(edit)
        except RuntimeError:
            continue
        res = rt.apply(create_decision(id=f"t-{uuid.uuid4().hex}", source="ab",
                       type="shell.exec", payload={"command": test_cmd, "timeout_s": 15, "cwd": cwd}))
        if isinstance(res, dict) and res.get("exitCode") == 0:
            return True
    return False


problems = _read_problems()
base_n = comb_n = 0
rows = []
for i in SLICE:
    task = problem_to_task(problems[i])
    with tempfile.TemporaryDirectory() as d:
        b = fix_loop(materialize(task, d), task.instruction, task.test_cmd,
                     max_iters=N, cwd=d, verbose=False).success
    with tempfile.TemporaryDirectory() as d:
        c = combined(materialize(task, d), task.instruction, task.test_cmd, d)
    base_n += b
    comb_n += c
    rows.append((i, b, c))
    print(f"  HumanEval_{i:<2} baseline={'P' if b else '.'}  combined={'P' if c else '.'}", flush=True)

t = len(rows)
print(f"\n===== combined (few-shot + best-of-N) vs baseline, OUT-OF-SAMPLE HumanEval[18:40] =====")
print(f"  baseline: {base_n}/{t} = {base_n/t*100:.0f}%")
print(f"  combined: {comb_n}/{t} = {comb_n/t*100:.0f}%")
print(f"  delta: {comb_n - base_n:+d}")
print("  flips:", [f'HE_{i}' for i, b, c in rows if c and not b])
print("  regressions:", [f'HE_{i}' for i, b, c in rows if b and not c])
