"""Navigation eval (EXT-004): guards the AST navigation family on the SUBTLE behaviors plain grep
gets wrong — find_usages ignoring matches inside strings/comments, go-to-definition isolating the
def site from its uses, and find_dead_code's reference-awareness (incl. test-file handling). Each
scenario seeds a fixture repo and asserts the navigator's EXACT answer. Deterministic — no model,
runs in CI. Complements refactor_eval.py on the read/analysis side of the toolkit."""
from __future__ import annotations

import tempfile
from pathlib import Path

from harness.navigate import find_usages, find_definition, find_dead_code, find_callers

SCENARIOS = [
    {   # AST must ignore the symbol inside a string and a comment (grep would find 4)
        "name": "usages_ignores_strings_comments",
        "files": {"m.py": ("def foo():\n    return 1\n\n"
                           "msg = 'please call foo here'   # foo also in this comment\n"
                           "x = foo()\n")},
        "check": lambda d: sum(1 for u in find_usages(d, "foo") if u["kind"] == "ref"),
        "expect": 1,
    },
    {   # go-to-definition returns the def site only, not the two uses
        "name": "definition_isolates_def",
        "files": {"m.py": "def bar():\n    return 2\n\ny = bar()\nz = bar()\n"},
        "check": lambda d: [(x["kind"], x["line"]) for x in find_definition(d, "bar")],
        "expect": [("def", 1)],
    },
    {   # class definition reports kind 'class'
        "name": "definition_class_kind",
        "files": {"s.py": "class Widget:\n    pass\n\nw = Widget()\n"},
        "check": lambda d: [x["kind"] for x in find_definition(d, "Widget")],
        "expect": ["class"],
    },
    {   # only the never-referenced symbol is dead; test-file defs are excluded
        "name": "deadcode_flags_only_orphan",
        "files": {
            "lib.py": "def used():\n    return 1\n\ndef orphan():\n    return 2\n",
            "main.py": "from lib import used\n\ndef run():\n    return used()\n",
            "test_main.py": "from main import run\n\ndef test_run():\n    assert run() == 1\n",
        },
        "check": lambda d: sorted(x["symbol"] for x in find_dead_code(d)),
        "expect": ["orphan"],
    },
    {   # call hierarchy attributes each call to its enclosing function (not a bare def-ref)
        "name": "callers_attributed_to_enclosing_fn",
        "files": {"m.py": ("def target():\n    return 1\n\n"
                           "def outer():\n    return target()\n\n"
                           "z = target()\n")},  # called in outer() and at module level
        "check": lambda d: sorted((c["caller"] for c in find_callers(d, "target"))),
        "expect": ["<module>", "outer"],
    },
    {   # a reference counts across multiple files (the two calls, not the import aliases)
        "name": "usages_across_multiple_files",
        "files": {
            "u.py": "def shared():\n    return 9\n",
            "a.py": "from u import shared\n\ndef ay():\n    return shared()\n",
            "b.py": "from u import shared\n\ndef be():\n    return shared() + 1\n",
        },
        "check": lambda d: sum(1 for x in find_usages(d, "shared") if x["kind"] == "ref"),
        "expect": 2,
    },
]


def run_navigation_eval() -> dict:
    results = []
    for sc in SCENARIOS:
        with tempfile.TemporaryDirectory() as d:
            for n, b in sc["files"].items():
                (Path(d) / n).write_text(b, encoding="utf-8", newline="\n")
            try:
                got = sc["check"](d)
                ok = got == sc["expect"]
            except Exception as e:  # a broken navigator surfaces as a failed scenario, not a crash
                got, ok = f"error: {e}", False
            results.append({"name": sc["name"], "ok": ok})
            print(f"  {'PASS' if ok else 'FAIL'} {sc['name']:34} got={got!r} expect={sc['expect']!r}",
                  flush=True)
    solved = sum(1 for r in results if r["ok"])
    n = len(results)
    print(f"\n=== navigation eval: {solved}/{n} = {solved / n * 100:.0f}% ===")
    return {"suite": "navigation", "solved": solved, "total": n, "perTask": results}


if __name__ == "__main__":
    run_navigation_eval()
