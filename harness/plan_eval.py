"""Multi-step `/plan` eval (EXT-004): regression-guards the planner->executor flow end-to-end.
Each scenario seeds a small repo with a FAILING test, runs `cmd_plan(request)` (the model plans;
the deterministic executor runs find/read/fix/run), then checks the repo's tests now PASS. A
scenario passes iff the suite is green afterwards — so it covers planning, grounding, and the fix.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

SCENARIOS = [
    {  # cross-file bug-fix flow
        "name": "fix_crossfile",
        "request": "the tests are failing, find the bug, fix it and verify",
        "files": {
            "calc.py": "def add(a, b):\n    return a - b  # BUG: should add\n",
            "app.py": "from calc import add\n\ndef total(xs):\n    s = 0\n    for x in xs:\n        s = add(s, x)\n    return s\n",
            "test_app.py": "from app import total\n\ndef test_total():\n    assert total([1, 2, 3]) == 6\n",
        },
    },
    {  # from-stub implementation flow
        "name": "implement_stub",
        "request": "implement factorial in mathx.py so the tests pass",
        "files": {
            "mathx.py": "def factorial(n):\n    pass  # TODO: implement\n",
            "test_mathx.py": "from mathx import factorial\n\ndef test_fact():\n    assert factorial(5) == 120\n",
        },
    },
    {  # single-file bug, plain request
        "name": "fix_single",
        "request": "fix the failing test",
        "files": {
            "strutil.py": "def shout(s):\n    return s.lower()  # BUG: should be upper\n",
            "test_strutil.py": "from strutil import shout\n\ndef test_shout():\n    assert shout('hi') == 'HI'\n",
        },
    },
]


def run_plan_eval(verbose: bool = False) -> dict:
    from harness.cli import JcodeCli
    from harness.multi_file import _run

    cli = JcodeCli()
    root = os.getcwd()
    results = []
    for sc in SCENARIOS:
        d = tempfile.mkdtemp(prefix="planeval-")
        for n, b in sc["files"].items():
            fp = Path(d) / n
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(b, encoding="utf-8", newline="\n")
        os.chdir(d)
        try:
            transcript = cli.cmd_plan(sc["request"])
            ok, _ = _run(".", "python -m pytest -q")
        finally:
            os.chdir(root)
        if verbose:
            print(transcript)
        results.append({"name": sc["name"], "solved": ok})
        print(f"  {'PASS' if ok else 'FAIL'} {sc['name']}", flush=True)
    solved = sum(1 for r in results if r["solved"])
    n = len(results)
    print(f"\n=== /plan multi-step eval: {solved}/{n} = {solved / n * 100:.0f}% ===")
    return {"suite": "plan", "solved": solved, "total": n, "perTask": results}


if __name__ == "__main__":
    run_plan_eval(verbose=False)
