"""Refactor eval (EXT-003): tracks the test-gated refactor family on EDGE cases — class
rename, a symbol referenced from several files, moving a class, moving a DECORATED function
(decorator line-span), and a third-file importer relying on the re-export. Each scenario seeds
a GREEN repo, applies the refactor, and passes iff the refactor reports success (which means it
applied AND the suite stayed green). Deterministic — no model, runs in CI."""
from __future__ import annotations

import tempfile
from pathlib import Path

from harness.refactor import rename_symbol, move_symbol

_T = "python -m pytest -q"

SCENARIOS = [
    {   # rename a CLASS referenced in another file
        "name": "rename_class",
        "files": {
            "shapes.py": "class Circle:\n    def __init__(self, r):\n        self.r = r\n    def area(self):\n        return 3.14 * self.r * self.r\n",
            "main.py": "from shapes import Circle\n\ndef make(r):\n    return Circle(r).area()\n",
            "test_main.py": "from main import make\n\ndef test_make():\n    assert abs(make(2) - 12.56) < 0.01\n",
        },
        "op": ("rename", "Circle", "Disk"),
    },
    {   # symbol referenced from TWO files — all updated
        "name": "rename_multi_ref",
        "files": {
            "util.py": "def helper():\n    return 7\n",
            "a.py": "from util import helper\n\ndef ay():\n    return helper()\n",
            "b.py": "from util import helper\n\ndef be():\n    return helper() + 1\n",
            "test_ab.py": "from a import ay\nfrom b import be\n\ndef test_ab():\n    assert ay() == 7 and be() == 8\n",
        },
        "op": ("rename", "helper", "assist"),
    },
    {   # move a CLASS to another module
        "name": "move_class",
        "files": {
            "models.py": "class User:\n    def __init__(self, name):\n        self.name = name\n    def greet(self):\n        return 'hi ' + self.name\n",
            "store.py": "# store\n",
            "test_models.py": "from models import User\n\ndef test_user():\n    assert User('a').greet() == 'hi a'\n",
        },
        "op": ("move", "User", "models.py", "store.py"),
    },
    {   # move a DECORATED function — the decorator line must travel with it
        "name": "move_decorated",
        "files": {
            "svc.py": "import functools\n\n\n@functools.lru_cache\ndef compute(n):\n    return n * 2\n",
            "core.py": "import functools\n",
            "test_svc.py": "from svc import compute\n\ndef test_compute():\n    assert compute(5) == 10\n",
        },
        "op": ("move", "compute", "svc.py", "core.py"),
    },
    {   # a THIRD file imports from the source — the re-export must keep it working
        "name": "move_third_party_ref",
        "files": {
            "a.py": "def foo():\n    return 1\n",
            "b.py": "# b\n",
            "c.py": "from a import foo\n\ndef use():\n    return foo()\n",
            "test_c.py": "from c import use\n\ndef test_use():\n    assert use() == 1\n",
        },
        "op": ("move", "foo", "a.py", "b.py"),
    },
]


def run_refactor_eval(verbose: bool = False) -> dict:
    results = []
    for sc in SCENARIOS:
        with tempfile.TemporaryDirectory() as d:
            for n, b in sc["files"].items():
                (Path(d) / n).write_text(b, encoding="utf-8", newline="\n")
            op = sc["op"]
            if op[0] == "rename":
                r = rename_symbol(d, op[1], op[2], _T)
                ok = bool(r.get("renamed"))
            else:
                r = move_symbol(d, op[1], op[2], op[3], _T)
                ok = bool(r.get("moved"))
            results.append({"name": sc["name"], "ok": ok})
            print(f"  {'PASS' if ok else 'FAIL'} {sc['name']:22} {r.get('note', '')}", flush=True)
    solved = sum(1 for r in results if r["ok"])
    n = len(results)
    print(f"\n=== refactor eval: {solved}/{n} = {solved / n * 100:.0f}% ===")
    return {"suite": "refactor", "solved": solved, "total": n, "perTask": results}


if __name__ == "__main__":
    run_refactor_eval()
