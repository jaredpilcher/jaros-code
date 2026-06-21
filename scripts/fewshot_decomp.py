"""Few-shot DECOMPOSITION experiment — WHY did retrieved-fewshot not beat fixed-fewshot?

The first probe compared retrieved-fewshot vs fixed-fewshot (both ARE few-shot), so a tie only
says "relevance/content didn't matter given a generic example was already present" — NOT "few-shot
doesn't help." This isolates the two real questions with a controlled 4-condition matrix on the
SAME HumanEval slice, single greedy body-completion:

  zero       : no example added            (the missing baseline)
  fixed      : current _FEWSHOT (generic)  (reference)
  random     : ONE random MBPP example     (seeded; "does ANY example help?" vs zero)
  retrieved  : ONE nearest MBPP example    ("does RELEVANCE help?" vs random — the controlled pair)

random and retrieved use an IDENTICAL wrapper and differ ONLY in which MBPP example is shown, so
their contrast isolates relevance. zero vs random isolates the presence of any example.
"""
import json
import math
import random
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.mbpp import _read_problems as mbpp_read
from harness.humaneval import _read_problems as he_read, problem_to_task
from harness.coding_loop import build_llm, _load_agent, _FEWSHOT

EMBED = "http://192.168.1.183:8001"
STEP = int(sys.argv[1]) if len(sys.argv) > 1 else 4
rng = random.Random(42)


def embed_batch(texts):
    data = json.dumps({"input": [t[:1200] for t in texts]}).encode()
    req = urllib.request.Request(EMBED + "/v1/embeddings", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
    return [d["embedding"] for d in sorted(resp["data"], key=lambda d: d["index"])]


def cos(a, b):
    s = sum(x * y for x, y in zip(a, b))
    return s / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)


mbpp = mbpp_read()
mbpp_code = [p["code"] for p in mbpp]
print(f"embedding {len(mbpp)} MBPP descriptions...", flush=True)
mbpp_vecs = []
for i in range(0, len(mbpp), 16):
    mbpp_vecs.extend(embed_batch(["search_document: " + mbpp[j]["text"]
                                  for j in range(i, min(i + 16, len(mbpp)))]))
print("corpus embedded.", flush=True)

llm = build_llm()
bc = _load_agent("body_completer_agent.py", llm)


def gen_and_test(task, prefix):
    with tempfile.TemporaryDirectory() as d:
        for n, b in task.files.items():
            (Path(d) / n).write_text(b, encoding="utf-8", newline="\n")
        [edit] = bc.decide({"path": task.target, "content": task.files[task.target],
                            "instruction": prefix + task.instruction, "symbols": "",
                            "feedback": "", "temperature": 0.0, "seed": 1})
        if edit.type == "code.write_file":
            (Path(d) / task.target).write_text(edit.payload["content"], encoding="utf-8", newline="\n")
        try:
            return subprocess.run(task.test_cmd, cwd=d, shell=True, capture_output=True,
                                  text=True, timeout=20).returncode == 0
        except Exception:
            return False


def wrap(code):
    return f"Here is a working example of a Python function:\n{code}\n\nNow implement the REAL task carefully:\n"


he = he_read()
idxs = list(range(0, len(he), STEP))
tally = {"zero": 0, "fixed": 0, "random": 0, "retrieved": 0}
for i in idxs:
    p = he[i]; task = problem_to_task(p)
    qvec = embed_batch(["search_query: " + p["prompt"]])[0]
    nearest = max(range(len(mbpp_vecs)), key=lambda j: cos(qvec, mbpp_vecs[j]))
    rand_j = rng.randrange(len(mbpp_code))
    conds = {"zero": "", "fixed": _FEWSHOT,
             "random": wrap(mbpp_code[rand_j]), "retrieved": wrap(mbpp_code[nearest])}
    res = {name: gen_and_test(task, pre) for name, pre in conds.items()}
    for name, ok in res.items():
        tally[name] += ok
    print(f"  {task.id:18} " + " ".join(f"{k}={'P' if v else 'F'}" for k, v in res.items()), flush=True)

n = len(idxs)
print(f"\n=== FEW-SHOT DECOMPOSITION (HumanEval[::{STEP}], {n} tasks, single greedy) ===")
for k in ("zero", "fixed", "random", "retrieved"):
    print(f"  {k:10} {tally[k]:2}/{n} = {tally[k]/n*100:.0f}%")
print(f"\n  any-example effect (random - zero):    {tally['random']-tally['zero']:+d}")
print(f"  relevance effect   (retrieved - random): {tally['retrieved']-tally['random']:+d}")
