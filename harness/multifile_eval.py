"""Multi-file eval suite (EXT-003 breadth): a measurable set of cross-file bug-fix
scenarios that exercise harness/multi_file.py end-to-end. Each scenario seeds a small repo
whose FAULT lives in a different file than the failing test, then asks multi_file_fix to
locate and fix it. Reports solved/total + which file each run fixed — so the cross-file
capability is a tracked, regression-guarded number, not a one-off demo.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

# Each scenario: the fault is NOT in the test file. instruction is intentionally generic
# (the harness must LOCATE the file). Bugs are simple enough for the 2B once the right file
# is targeted; the eval measures location + fix together.
SCENARIOS = [
    {  # logic bug, 2-file import graph
        "name": "scale_mul",
        "files": {
            "mathutils.py": "def scale(x):\n    return x + 2  # BUG: should multiply by 2\n",
            "main.py": "from mathutils import scale\n\ndef apply(items):\n    return [scale(i) for i in items]\n",
            "test_app.py": "from main import apply\n\ndef test_apply():\n    assert apply([1, 2, 3]) == [2, 4, 6]\n",
        },
    },
    {  # logic bug, 3-level deep import chain (bug in the deepest file)
        "name": "deep_inc",
        "files": {
            "a.py": "def base(x):\n    return x - 1  # BUG: should be x + 1\n",
            "b.py": "from a import base\n\ndef mid(x):\n    return base(x) * 2\n",
            "c.py": "from b import mid\n\ndef top(x):\n    return mid(x)\n",
            "test_c.py": "from c import top\n\ndef test_top():\n    assert top(3) == 8\n",
        },
    },
    {  # exception (typo) — the traceback names the faulty file directly
        "name": "typo_split",
        "files": {
            "textutil.py": "def parse(s):\n    return s.spliit(',')  # BUG: typo, should be split\n",
            "app.py": "from textutil import parse\n\ndef count(s):\n    return len(parse(s))\n",
            "test_app.py": "from app import count\n\ndef test_count():\n    assert count('a,b,c') == 3\n",
        },
    },
    {  # wrong operator in a helper called across files
        "name": "wrong_op",
        "files": {
            "calc.py": "def combine(a, b):\n    return a - b  # BUG: should add\n",
            "runner.py": "from calc import combine\n\ndef total(xs):\n    out = 0\n    for x in xs:\n        out = combine(out, x)\n    return out\n",
            "test_runner.py": "from runner import total\n\ndef test_total():\n    assert total([1, 2, 3]) == 6\n",
        },
    },
]


def run_multifile_eval(verbose: bool = False) -> dict:
    from harness.multi_file import multi_file_fix

    results = []
    for sc in SCENARIOS:
        with tempfile.TemporaryDirectory() as d:
            for n, b in sc["files"].items():
                (Path(d) / n).write_text(b, encoding="utf-8", newline="\n")
            test_file = next(n for n in sc["files"] if n.startswith("test"))
            r = multi_file_fix(d, "python -m pytest -q",
                               "Fix the failing test", str(Path(d) / test_file),
                               max_iters=3, verbose=verbose)
            results.append({"name": sc["name"], "solved": r["solved"],
                            "file": r.get("file"), "tried": r.get("tried", [])})
            print(f"  {'PASS' if r['solved'] else 'FAIL'} {sc['name']:12} "
                  f"fixed={r.get('file')} tried={r.get('tried')}", flush=True)
    solved = sum(1 for r in results if r["solved"])
    n = len(results)
    print(f"\n=== multi-file eval: {solved}/{n} = {solved / n * 100:.0f}% ===")
    return {"suite": "multifile", "solved": solved, "total": n, "perTask": results}


if __name__ == "__main__":
    run_multifile_eval(verbose=False)
