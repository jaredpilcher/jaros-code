"""A/B a real capability lever on EXTERNAL problems (HumanEval slice):
  BASELINE  = current fix_loop (3 sequential attempts WITH test-failure feedback)
  BEST-OF-N = N independent samples from the ORIGINAL stub at spread temperatures,
              selected purely by the deterministic test (the thesis: model proposes,
              harness verifies). No feedback, no accumulation -> escapes wrong attractors.

Prints solved counts + the per-problem delta so the lever is judged honestly, not by a
single anecdote. Same problems, same attempt budget (N == max_iters) for a fair compare.
"""
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import Runtime, build_llm, fix_loop, _load_agent, create_decision
from harness.humaneval import _read_problems, problem_to_task

N = 6
SLICE = range(0, 18)
TEMPS = [0.0, 0.3, 0.5, 0.7, 0.9, 1.1]


def best_of_n(target, instruction, test_cmd, *, cwd, n=N):
    rt = Runtime()
    rw = _load_agent("rewriter_agent.py", build_llm())
    stub = Path(target).read_text(encoding="utf-8")
    for k in range(n):
        Path(target).write_text(stub, encoding="utf-8", newline="\n")  # fresh sample
        [edit] = rw.decide({"path": str(target), "content": stub, "instruction": instruction,
                            "symbols": "", "feedback": "",
                            "temperature": TEMPS[k % len(TEMPS)], "seed": k + 1})
        if edit.type not in ("code.write_file", "code.apply_patch"):
            continue
        try:
            rt.apply(edit)
        except RuntimeError:
            continue
        res = rt.apply(create_decision(id=f"t-{uuid.uuid4().hex}", source="ab",
                       type="shell.exec", payload={"command": test_cmd, "cwd": cwd}))
        if isinstance(res, dict) and res.get("exitCode") == 0:
            return True
    return False


def materialize(task, d):
    dp = Path(d)
    for name, body in task.files.items():
        (dp / name).write_text(body, encoding="utf-8", newline="\n")
    return str(dp / task.target)


problems = _read_problems()
base_solved = bestn_solved = 0
rows = []
for i in SLICE:
    task = problem_to_task(problems[i])
    with tempfile.TemporaryDirectory() as d:
        tgt = materialize(task, d)
        b = fix_loop(tgt, task.instruction, task.test_cmd, max_iters=N, cwd=d, verbose=False).success
    with tempfile.TemporaryDirectory() as d:
        tgt = materialize(task, d)
        n = best_of_n(tgt, task.instruction, task.test_cmd, cwd=d)
    base_solved += b
    bestn_solved += n
    rows.append((task.id, b, n))
    print(f"  {task.id:18} baseline={'P' if b else '.'}  bestN={'P' if n else '.'}", flush=True)

t = len(rows)
print(f"\n===== A/B on HumanEval[{SLICE.start}:{SLICE.stop}] (N={N}) =====")
print(f"  baseline (seq+feedback): {base_solved}/{t}")
print(f"  best-of-N (test-select): {bestn_solved}/{t}")
print(f"  delta: {bestn_solved - base_solved:+d}")
print("  flips (bestN solved, baseline didn't):",
      [r[0] for r in rows if r[2] and not r[1]])
print("  regressions (baseline solved, bestN didn't):",
      [r[0] for r in rows if r[1] and not r[2]])
