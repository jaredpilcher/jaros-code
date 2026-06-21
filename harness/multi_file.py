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
import subprocess
from pathlib import Path

_IMPORT_RE = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+))", re.M)
_TRACE_FILE_RE = re.compile(r'File "([^"]+\.py)"|^([\w./\\-]+\.py):\d+', re.M)
_TRACE_FRAME_RE = re.compile(r'File "([^"]+\.py)", line (\d+), in (\S+)')


def localize_fault(test_output: str) -> list[dict]:
    """Agentless-style fault localization: pull the (file, line, function) frames from a Python
    traceback, DEEPEST FRAME FIRST (the most direct fault site). Deterministic — the traceback
    already names the exact function, so no model is needed to localize. Python prints frames
    outermost->innermost ('most recent call last'), so reversed() surfaces the deepest frame
    first. De-duped on (file, function)."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for f, ln, fn in reversed(_TRACE_FRAME_RE.findall(test_output)):
        key = (f, fn)
        if key in seen:
            continue
        seen.add(key)
        out.append({"file": f, "line": int(ln), "function": fn})
    return out


def _imported_modules(src: str) -> list[str]:
    """Dotted module names imported by ``src`` (e.g. 'pkg.sub', 'mathutils') — full path kept
    so subpackages resolve to pkg/sub.py rather than a non-existent pkg.py."""
    mods = []
    for a, b in _IMPORT_RE.findall(src):
        name = (a or b).lstrip(".")
        if name:
            mods.append(name)
    return mods


def _module_to_file(root: Path, dotted: str) -> Path | None:
    """Resolve a dotted module name to an existing file in the repo: pkg/sub.py or the
    package's pkg/sub/__init__.py. Returns None for stdlib/third-party (not in the repo)."""
    rel = dotted.replace(".", "/")
    for cand in (root / f"{rel}.py", root / rel / "__init__.py"):
        if cand.is_file():
            return cand
    return None


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
            f = _module_to_file(root, mod)
            if f is not None and str(f) not in seen:
                seen.add(str(f))
                add(f)
                frontier.append(str(f))
    return ordered


def _run(cwd: str, test_cmd: str) -> tuple[bool, str]:
    proc = subprocess.run(test_cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=30)
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _snapshot(cwd: str) -> dict[str, str]:
    """In-memory copy of every repo .py keyed by FULL path — so subdir/package files with the
    same basename don't collide (the old flatten-by-name snapshot could corrupt them)."""
    return {str(p): p.read_text(encoding="utf-8") for p in Path(cwd).rglob("*.py")}


def _restore(snap: dict[str, str]) -> None:
    for path, text in snap.items():
        Path(path).write_text(text, encoding="utf-8", newline="\n")


def _fail_count(out: str) -> int:
    nums = [int(m) for m in re.findall(r"(\d+)\s+(?:failed|error)", out or "")]
    return sum(nums) if nums else 1


def multi_file_fix(cwd: str, test_cmd: str, instruction: str, test_file: str,
                   *, max_iters: int = 3, verbose: bool = False) -> dict:
    """Fix a failing multi-file test. Locate candidate files, then fix them CUMULATIVELY: try
    each candidate with fix_loop(keep_partial=True) so its best partial edit survives; KEEP the
    edit only if it strictly REDUCES the failing-test count (and build the next fix on top),
    else revert it. Resolves faults that span several files, not just a single-file fault.

    No candidate-count cap: the candidates are only files in the IMPORT CLOSURE reachable from
    the failing test (naturally small for realistic tests), and a count cap can silently
    EXCLUDE the culprit — for a logic bug the traceback doesn't name it, so its rank is just
    import order. If pathological cost ever bites, bound it with a time budget, not a count."""
    from harness.coding_loop import fix_loop  # local import: avoid cycle at module load

    ok, out = _run(cwd, test_cmd)
    if ok:
        return {"solved": True, "file": None, "tried": [], "fixed": [], "note": "already passing"}

    base = _fail_count(out)
    cands = candidate_files(cwd, out, test_file)
    tried, kept = [], []
    for cand in cands:
        snap = _snapshot(cwd)
        tried.append(Path(cand).name)
        fix_loop(cand, instruction, test_cmd, max_iters=max_iters, cwd=cwd,
                 verbose=verbose, keep_partial=True)
        ok, out = _run(cwd, test_cmd)
        if ok:
            kept.append(Path(cand).name)
            return {"solved": True, "file": kept[-1], "tried": tried, "fixed": kept, "note": "fixed"}
        nf = _fail_count(out)
        if nf < base:                 # strict progress — keep this partial, build on it
            base = nf
            kept.append(Path(cand).name)
        else:                         # no progress (distractor / harmless rewrite) — revert
            _restore(snap)
    return {"solved": False, "file": None, "tried": tried, "fixed": kept, "note": "no candidate fixed it"}
