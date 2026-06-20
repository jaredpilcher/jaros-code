"""A/B: WHOLE-FILE rewrite vs BODY-ONLY completion on the implement regime (HumanEval).

Hypothesis: the model wastes most tokens copying the signature+docstring back; asking for
ONLY the body and splicing it after the given prompt cuts tokens -> faster, with equal-or-
better pass. Single greedy attempt (temp 0) per mode for a clean per-call comparison:
report time + pass for each, on a small spread of problems.
"""
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import Runtime, build_llm, _load_agent, create_decision
from harness.humaneval import _read_problems, problem_to_task
from jaros.llm import LlmRequest

IDXS = [0, 12, 24, 39, 48, 63, 80, 100]   # spread across difficulty
llm = build_llm()
rw = _load_agent("rewriter_agent.py", llm)

_BODY_PROMPT = (
    "Complete this Python function. Output ONLY the function body — the indented "
    "statements that go after the signature/docstring. NO signature, NO docstring, NO "
    "markdown fences, NO explanation. Every line indented under the function.\n\n{code}"
)


def run_test(d, files):
    dp = Path(d)
    for n, b in files.items():
        (dp / n).write_text(b, encoding="utf-8", newline="\n")
    rt = Runtime()
    res = rt.apply(create_decision(id=f"t-{uuid.uuid4().hex}", source="ab",
                   type="shell.exec", payload={"command": "python -m pytest -q", "timeout_s": 15, "cwd": d}))
    return isinstance(res, dict) and res.get("exitCode") == 0


def splice_body(prompt_code, raw):
    import re
    raw = re.sub(r"```[\w+-]*", "", raw).replace("```", "")
    # if the model re-emitted the whole function, just use that
    if "def " in raw and raw.lstrip().startswith("def "):
        return raw
    lines = [ln for ln in raw.split("\n")]
    # ensure body lines are indented (model sometimes drops indentation)
    body = "\n".join(ln if (ln.strip() == "" or ln.startswith((" ", "\t"))) else "    " + ln for ln in lines)
    return prompt_code + body + "\n"


probs = _read_problems()
wf_pass = bo_pass = 0
wf_t = bo_t = 0.0
print(f"{'problem':22} {'whole-file':>22} {'body-only':>22}")
for i in IDXS:
    task = problem_to_task(probs[i])
    target = task.target
    # --- whole-file (current rewriter) ---
    t0 = time.time()
    [edit] = rw.decide({"path": target, "content": task.files[target], "instruction": task.instruction,
                        "symbols": "", "feedback": "", "temperature": 0.0, "seed": 1})
    wf_dt = time.time() - t0
    wf_files = dict(task.files)
    if edit.type == "code.write_file":
        wf_files[target] = edit.payload["content"]
    with tempfile.TemporaryDirectory() as d:
        wf_ok = run_test(d, wf_files)
    # --- body-only ---
    sig_doc = probs[i]["prompt"]   # signature + docstring, no body
    t0 = time.time()
    raw = llm.complete(LlmRequest(prompt=_BODY_PROMPT.format(code=sig_doc), params={"seed": 1})).text
    bo_dt = time.time() - t0
    bo_files = dict(task.files)
    bo_files[target] = splice_body(sig_doc, raw)
    with tempfile.TemporaryDirectory() as d:
        bo_ok = run_test(d, bo_files)
    wf_pass += wf_ok; bo_pass += bo_ok; wf_t += wf_dt; bo_t += bo_dt
    print(f"{task.id:22} {('PASS' if wf_ok else 'fail')+f' {wf_dt:.0f}s':>22} {('PASS' if bo_ok else 'fail')+f' {bo_dt:.0f}s':>22}", flush=True)

n = len(IDXS)
print(f"\n=== single greedy attempt, {n} problems ===")
print(f"  whole-file: {wf_pass}/{n} pass | avg gen {wf_t/n:.0f}s")
print(f"  body-only:  {bo_pass}/{n} pass | avg gen {bo_t/n:.0f}s  ({(1-bo_t/wf_t)*100:.0f}% faster gen)" if wf_t else "")
