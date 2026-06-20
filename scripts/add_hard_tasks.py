"""Harden the authored suite (ratchet: it hit 100%/frontier=null). Add harder tier-3
tasks, each VERIFIED deterministically — the reference solution must pass the task's own
test before the task is written, so we never add a broken eval."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "coding_tasks"

# id, target module, func, instruction, test asserts, reference solution
TASKS = [
    ("two_sum", "two_sum", "two_sum",
     "Implement two_sum(nums, target): return the indices [i, j] (i < j) of the two "
     "distinct elements that add up to target. Exactly one solution exists. "
     "two_sum([2, 7, 11, 15], 9) == [0, 1]; two_sum([3, 2, 4], 6) == [1, 2].",
     ["assert two_sum([2, 7, 11, 15], 9) == [0, 1]",
      "assert two_sum([3, 2, 4], 6) == [1, 2]",
      "assert two_sum([3, 3], 6) == [0, 1]"],
     "def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n"
     "        if target - n in seen:\n            return [seen[target - n], i]\n"
     "        seen[n] = i\n    return []\n"),

    ("merge_intervals", "merge_intervals", "merge",
     "Implement merge(intervals): given a list of [start, end] intervals, merge all "
     "overlapping intervals and return the result sorted by start. "
     "merge([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]; "
     "merge([[1, 4], [4, 5]]) == [[1, 5]].",
     ["assert merge([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]",
      "assert merge([[1, 4], [4, 5]]) == [[1, 5]]",
      "assert merge([[1, 4], [2, 3]]) == [[1, 4]]"],
     "def merge(intervals):\n    out = []\n    for s, e in sorted(intervals):\n"
     "        if out and s <= out[-1][1]:\n            out[-1][1] = max(out[-1][1], e)\n"
     "        else:\n            out.append([s, e])\n    return out\n"),

    ("longest_common_prefix", "lcp", "lcp",
     "Implement lcp(strs): return the longest common prefix string of a list of strings, "
     "or '' if there is none. lcp(['flower', 'flow', 'flight']) == 'fl'; "
     "lcp(['dog', 'racecar', 'car']) == ''.",
     ["assert lcp(['flower', 'flow', 'flight']) == 'fl'",
      "assert lcp(['dog', 'racecar', 'car']) == ''",
      "assert lcp(['interspecies', 'interstellar', 'interstate']) == 'inters'",
      "assert lcp(['a']) == 'a'"],
     "def lcp(strs):\n    if not strs:\n        return ''\n    pre = strs[0]\n"
     "    for s in strs[1:]:\n        while not s.startswith(pre):\n            pre = pre[:-1]\n"
     "            if not pre:\n                return ''\n    return pre\n"),

    ("my_atoi", "my_atoi", "my_atoi",
     "Implement my_atoi(s): parse a leading 32-bit signed integer from string s like C's "
     "atoi. Skip leading spaces, accept an optional +/- sign, read digits until a "
     "non-digit, and ignore trailing characters. Return 0 if no digits are found. "
     "my_atoi('   -42') == -42; my_atoi('4193 with words') == 4193; "
     "my_atoi('words and 987') == 0.",
     ["assert my_atoi('   -42') == -42",
      "assert my_atoi('4193 with words') == 4193",
      "assert my_atoi('words and 987') == 0",
      "assert my_atoi('+13') == 13",
      "assert my_atoi('') == 0"],
     "def my_atoi(s):\n    s = s.lstrip()\n    if not s:\n        return 0\n    sign = 1\n"
     "    i = 0\n    if s[0] in '+-':\n        sign = -1 if s[0] == '-' else 1\n        i = 1\n"
     "    digits = ''\n    while i < len(s) and s[i].isdigit():\n        digits += s[i]\n        i += 1\n"
     "    return sign * int(digits) if digits else 0\n"),
]

written = 0
for tid, module, func, instr, asserts, ref in TASKS:
    test_body = "\n".join("    " + a for a in asserts)
    test_file = f"from {module} import {func}\n\n\ndef test_{tid}():\n{test_body}\n"
    # VERIFY: reference solution must pass the test before we add the task.
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        (dp / f"{module}.py").write_text(ref, encoding="utf-8")
        (dp / f"test_{module}.py").write_text(test_file, encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=d, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [X] {tid}: reference FAILS its own test — NOT adding\n{r.stdout[-300:]}")
        continue
    task = {"id": tid, "instruction": instr, "tier": 3, "target": f"{module}.py",
            "test_cmd": "python -m pytest -q",
            "files": {f"{module}.py": f"def {func}(*args, **kwargs):\n    raise NotImplementedError\n",
                      f"test_{module}.py": test_file}}
    (OUT / f"{tid}.json").write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    print(f"  [OK] {tid}: reference passes; task written ({len(asserts)} asserts)")
    written += 1

print(f"\nwrote {written}/{len(TASKS)} verified hard tasks")
