"""The real lever: STRATEGY-DIVERSE CASCADE. Same attempt budget as baseline (6), but
each attempt uses a different strategy (plain / few-shot / high-temp), fresh from the
stub, and the deterministic test selects the first that passes. Because the test gates
acceptance, the cascade is the UNION of what its strategies can solve -> strictly
non-regressing vs any single strategy. Validated OUT-OF-SAMPLE on fresh HumanEval[40:60].
"""
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import Runtime, build_llm, fix_loop, _load_agent, create_decision
from harness.humaneval import _read_problems, problem_to_task

SLICE = range(40, 60)
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
# (instruction_prefix, temperature) — 6 diverse attempts, same budget as baseline.
STRATEGIES = [("", 0.0), ("", 0.4), (FEWSHOT, 0.2), (FEWSHOT, 0.6), ("", 0.9), ("", 1.1)]


def materialize(task, d):
    dp = Path(d)
    for n, b in task.files.items():
        (dp / n).write_text(b, encoding="utf-8", newline="\n")
    return str(dp / task.target)


def cascade(target, instruction, test_cmd, cwd):
    rt = Runtime()
    rw = _load_agent("rewriter_agent.py", build_llm())
    stub = Path(target).read_text(encoding="utf-8")
    for k, (prefix, temp) in enumerate(STRATEGIES):
        Path(target).write_text(stub, encoding="utf-8", newline="\n")
        [edit] = rw.decide({"path": target, "content": stub, "instruction": prefix + instruction,
                            "symbols": "", "feedback": "", "temperature": temp, "seed": k + 1})
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
base_n = casc_n = 0
rows = []
for i in SLICE:
    task = problem_to_task(problems[i])
    with tempfile.TemporaryDirectory() as d:
        b = fix_loop(materialize(task, d), task.instruction, task.test_cmd,
                     max_iters=6, cwd=d, verbose=False).success
    with tempfile.TemporaryDirectory() as d:
        c = cascade(materialize(task, d), task.instruction, task.test_cmd, d)
    base_n += b
    casc_n += c
    rows.append((i, b, c))
    print(f"  HumanEval_{i:<2} baseline={'P' if b else '.'}  cascade={'P' if c else '.'}", flush=True)

t = len(rows)
print(f"\n===== strategy-cascade vs baseline, OUT-OF-SAMPLE HumanEval[40:60] (budget=6 each) =====")
print(f"  baseline: {base_n}/{t} = {base_n/t*100:.0f}%")
print(f"  cascade : {casc_n}/{t} = {casc_n/t*100:.0f}%")
print(f"  delta: {casc_n - base_n:+d}")
print("  flips:", [f'HE_{i}' for i, b, c in rows if c and not b])
print("  regressions:", [f'HE_{i}' for i, b, c in rows if b and not c])
