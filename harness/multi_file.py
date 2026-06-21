"""Multi-file fix (EXT-003 breadth): the single-file fix_loop only sees/edits ONE target,
so it cannot fix a bug whose fault lives in a different file than the one under test — the
Claude-Code-class case. This wraps fix_loop with deterministic FILE LOCATION: derive the
candidate files from the test failure (the traceback names files) plus the import graph
reachable from the failing test, then try fixing each candidate on a clean snapshot until
the test passes. Locating the file is parsing+graph (a deterministic tool), not a model
judgement; only the actual fix is model work (plane-placement: count/search -> deterministic).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_IMPORT_RE = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+))", re.M)
_TRACE_FILE_RE = re.compile(r'File "([^"]+\.py)"|^([\w./\\-]+\.py):\d+', re.M)


def _imported_modules(src: str) -> list[str]:
    """Top-level module names imported by ``src`` (first dotted component)."""
    mods = []
    for a, b in _IMPORT_RE.findall(src):
        name = (a or b).lstrip(".").split(".")[0]
        if name:
            mods.append(name)
    return mods


def candidate_files(cwd: str, test_output: str, test_file: str) -> list[str]:
    """Ordered, de-duped list of repo .py files that could hold the fault — traceback files
    first (most direct), then the import graph reachable from the failing test. The test
    file itself is excluded (we fix the code under test, not the test)."""
    root = Path(cwd)
    test_name = Path(test_file).name
    ordered: list[str] = []

    def add(p: Path):
        if p.is_file() and p.suffix == ".py" and p.name != test_name and str(p) not in ordered:
            ordered.append(str(p))

    # 1) files named in the traceback, DEEPEST FRAME FIRST. Python prints "most recent call
    # last", so the exception origin is the bottom-most File line — try it before the shallower
    # callers (fewer wasted fix attempts on a multi-frame traceback).
    tb = [(m[0] or m[1]) for m in _TRACE_FILE_RE.findall(test_output or "")]
    for raw in reversed(tb):
        if raw:
            cand = Path(raw)
            add(cand if cand.is_absolute() else root / cand.name)

    # 2) import graph reachable from the failing test (BFS over local modules)
    seen, frontier = set(), [test_file]
    while frontier:
        cur = frontier.pop()
        try:
            src = Path(cur).read_text(encoding="utf-8")
        except OSError:
            continue
        for mod in _imported_modules(src):
            f = root / f"{mod}.py"
            if f.is_file() and str(f) not in seen:
                seen.add(str(f))
                add(f)
                frontier.append(str(f))
    return ordered


def _run(cwd: str, test_cmd: str) -> tuple[bool, str]:
    proc = subprocess.run(test_cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=30)
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def multi_file_fix(cwd: str, test_cmd: str, instruction: str, test_file: str,
                   *, max_iters: int = 3, verbose: bool = False) -> dict:
    """Fix a failing multi-file test. Locate candidate files, then try fixing each on a
    clean snapshot (reverting a non-helping attempt before the next) until the test passes."""
    from harness.coding_loop import fix_loop  # local import: avoid cycle at module load

    ok, out = _run(cwd, test_cmd)
    if ok:
        return {"solved": True, "file": None, "tried": [], "note": "already passing"}

    cands = candidate_files(cwd, out, test_file)
    tried = []
    for cand in cands:
        snap = tempfile.mkdtemp(prefix="mff-snap-")
        files = [p for p in Path(cwd).rglob("*.py")]
        for p in files:
            shutil.copy2(p, Path(snap) / p.name)
        tried.append(Path(cand).name)
        res = fix_loop(cand, instruction, test_cmd, max_iters=max_iters, cwd=cwd, verbose=verbose)
        ok, _ = _run(cwd, test_cmd)
        if res.success and ok:
            shutil.rmtree(snap, ignore_errors=True)
            return {"solved": True, "file": Path(cand).name, "tried": tried, "note": "fixed"}
        for p in files:  # revert: this candidate wasn't the fault (or fix_loop mangled it)
            sp = Path(snap) / p.name
            if sp.is_file():
                shutil.copy2(sp, p)
        shutil.rmtree(snap, ignore_errors=True)
    return {"solved": False, "file": None, "tried": tried, "note": "no candidate fixed it"}
