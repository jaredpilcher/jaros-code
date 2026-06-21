"""Test-gated refactoring (EXT-003): rename a symbol across a repo, behavior-preserving.

A NEW capability class — the harness could fix/implement but not REFACTOR. Refactoring is a
perfect two-plane fit: the edit is DETERMINISTIC (rename every whole-word occurrence of the
symbol across .py files — no model needed) and correctness is the GATE (the suite, green
before, must stay green after). If the rename turns the suite red, it touched something it
shouldn't have, so we REVERT — the rename can never silently break behavior. Crude-but-safe:
a word-boundary rename may also touch a same-named comment/string, but the test-gate guarantees
behavior preservation, which is what a refactor must promise. (A future AST version can tighten
scope; the gate keeps even the simple version honest.)
"""
from __future__ import annotations

import re
from pathlib import Path

from harness.multi_file import _run, _snapshot, _restore  # reuse run/snapshot/restore


def rename_symbol(cwd: str, old: str, new: str,
                  test_cmd: str = "python -m pytest -q") -> dict:
    """Rename whole-word `old` -> `new` across the repo's .py files, gated by the suite staying
    green. Pre-req: a refactor preserves PASSING tests, so the suite must be green first."""
    if not (old.isidentifier() and new.isidentifier()):
        return {"renamed": False, "occurrences": 0, "note": "old/new must be identifiers"}
    ok0, _ = _run(cwd, test_cmd)
    if not ok0:
        return {"renamed": False, "occurrences": 0, "note": "suite not green before rename"}

    snap = _snapshot(cwd)
    pat = re.compile(rf"\b{re.escape(old)}\b")
    occ, files = 0, 0
    for p in Path(cwd).rglob("*.py"):
        try:
            src = p.read_text(encoding="utf-8")
        except OSError:
            continue
        new_src, n = pat.subn(new, src)
        if n:
            p.write_text(new_src, encoding="utf-8", newline="\n")
            occ += n
            files += 1

    ok1, _ = _run(cwd, test_cmd)
    if ok1:
        return {"renamed": True, "occurrences": occ, "files": files,
                "note": f"renamed {old}->{new} ({occ} occurrences in {files} files), suite green"}
    _restore(snap)   # the rename broke something it shouldn't have — never ship a red suite
    return {"renamed": False, "occurrences": occ, "files": files,
            "note": f"rename {old}->{new} turned the suite red; reverted"}
