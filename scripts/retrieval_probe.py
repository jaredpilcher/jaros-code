"""Retrieval-few-shot probe (tests the owner's behavior-keyed code-retrieval idea, cheaply).

Corpus  = MBPP reference solutions, keyed by their NL description (a stand-in for the Gherkin
          key; the real Gherkin layer would only sharpen the key).
Query   = each HumanEval task's signature+docstring (a DIFFERENT source -> no leakage of the
          task's own answer).
Match   = nomic-embed (on the Jetson GPU, :8001) cosine similarity, behavior-to-behavior.
Test    = single greedy body-completion (temp 0) with the FIXED few-shot vs the RETRIEVED
          MBPP implementation as the few-shot; run the real test; compare pass@1.

If retrieved-few-shot beats fixed, behavior-keyed retrieval lifts the 2B and the big index is
justified; if not, we saved building a datacenter of specs.
"""
import json
import math
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.mbpp import _read_problems as mbpp_read
from harness.humaneval import _read_problems as he_read, problem_to_task
from harness.coding_loop import build_llm, _load_agent, _FEWSHOT
from jaros.llm import LlmRequest  # noqa: F401

EMBED = "http://192.168.1.183:8001"
STEP = int(sys.argv[1]) if len(sys.argv) > 1 else 8


def embed_batch(texts: list[str]) -> list[list[float]]:
    data = json.dumps({"input": [t[:1200] for t in texts]}).encode()
    req = urllib.request.Request(EMBED + "/v1/embeddings", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
    return [d["embedding"] for d in sorted(resp["data"], key=lambda d: d["index"])]


def cos(a, b):
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return s / (na * nb + 1e-9)


# 1) embed the MBPP corpus (nomic prefix improves retrieval)
mbpp = mbpp_read()
mbpp_code = [p["code"] for p in mbpp]
print(f"embedding {len(mbpp)} MBPP descriptions (corpus)...", flush=True)
mbpp_vecs = []
B = 16
for i in range(0, len(mbpp), B):
    batch = ["search_document: " + mbpp[j]["text"] for j in range(i, min(i + B, len(mbpp)))]
    mbpp_vecs.extend(embed_batch(batch))
    if i % 160 == 0:
        print(f"  {i}/{len(mbpp)}", flush=True)
print("corpus embedded.", flush=True)

# 2) generation + test harness
llm = build_llm()
bc = _load_agent("body_completer_agent.py", llm)


def gen_and_test(task, prefix: str) -> bool:
    with tempfile.TemporaryDirectory() as d:
        for n, b in task.files.items():
            (Path(d) / n).write_text(b, encoding="utf-8", newline="\n")
        [edit] = bc.decide({"path": task.target, "content": task.files[task.target],
                            "instruction": prefix + task.instruction, "symbols": "",
                            "feedback": "", "temperature": 0.0, "seed": 1})
        if edit.type == "code.write_file":
            (Path(d) / task.target).write_text(edit.payload["content"], encoding="utf-8", newline="\n")
        try:
            r = subprocess.run(task.test_cmd, cwd=d, shell=True, capture_output=True, text=True, timeout=20)
            return r.returncode == 0
        except Exception:
            return False


# 3) A/B over a HumanEval slice
he = he_read()
idxs = list(range(0, len(he), STEP))
fixed_pass = retr_pass = 0
for i in idxs:
    p = he[i]; task = problem_to_task(p)
    qvec = embed_batch(["search_query: " + p["prompt"]])[0]
    best = max(range(len(mbpp_vecs)), key=lambda j: cos(qvec, mbpp_vecs[j]))
    retrieved = ("Here is a working example of a similar Python function:\n"
                 f"{mbpp_code[best]}\n\nNow implement the REAL task carefully:\n")
    fp = gen_and_test(task, _FEWSHOT)
    rp = gen_and_test(task, retrieved)
    fixed_pass += fp; retr_pass += rp
    print(f"  {task.id:18} fixed={'P' if fp else 'F'} retrieved={'P' if rp else 'F'}  "
          f"(nearest MBPP: {mbpp[best]['text'][:46]})", flush=True)

n = len(idxs)
print(f"\n=== RETRIEVAL-FEWSHOT PROBE (HumanEval[::{STEP}], {n} tasks, single greedy attempt) ===")
print(f"fixed few-shot:     {fixed_pass}/{n} = {fixed_pass/n*100:.0f}%")
print(f"retrieved few-shot: {retr_pass}/{n} = {retr_pass/n*100:.0f}%")
print(f"delta: {(retr_pass-fixed_pass):+d} problems")
