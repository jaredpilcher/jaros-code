"""Diagnostic: what does the rewriter produce for running_total, given the correct
extracted test as feedback? The bottleneck moved here -- see exactly how it fails."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import build_llm, _load_agent  # noqa: E402

rw = _load_agent("rewriter_agent.py", build_llm())
intent = ("Build running_total(nums): given a list of numbers, return a new list where "
          "element i is the sum of nums[0] through nums[i] (a running cumulative sum). "
          "For example running_total([1, 2, 3]) returns [1, 3, 6]. An empty list returns "
          "an empty list.")
stub = "def running_total(nums):\n    raise NotImplementedError\n"
feedback = ("assert running_total([1, 2, 3]) == [1, 3, 6]\n"
            "E   assert running_total([1, 2, 3]) == [1, 3, 6]")
for seed in (1, 2, 3):
    [d] = rw.decide({"path": "running_total.py", "content": stub, "instruction": intent,
                     "symbols": "running_total(function)", "feedback": feedback,
                     "temperature": 0.0 if seed == 1 else 0.4, "seed": seed})
    print(f"\n--- seed {seed} ({d.type}) ---")
    print(d.payload.get("content", d.payload.get("note", "")))
