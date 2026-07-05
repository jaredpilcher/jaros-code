"""Multi-file fix (EXT-003 breadth): the single-file fix_loop only sees/edits ONE target,
so it cannot fix a bug whose fault lives in a different file than the one under test — the
Claude-Code-class case. This wraps fix_loop with deterministic FILE LOCATION: derive the
candidate files from the test failure (the traceback names files) plus the import graph
reachable from the failing test, then try fixing each candidate on a clean snapshot until
the test passes. Locating the file is parsing+graph (a deterministic tool), not a model
judgement; only the actual fix is model work (plane-placement: count/search -> deterministic).
"""
from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path

_IMPORT_RE = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+))", re.M)
_TRACE_FILE_RE = re.compile(r'File "([^"]+\.py)"|^([\w./\\-]+\.py):\d+', re.M)
_TRACE_FRAME_RE = re.compile(r'File "([^"]+\.py)", line (\d+), in (\S+)')


# #EXT-037-REQ-10 Start
def _jaros_write(path: "Path | str", content: str, root: "str | None",
                 runtime: "object | None" = None) -> "str | None":
    """Write `content` to `path` (Tenet 1 / EXT-037 REQ-10). Mirrors `harness/refactor.py`'s
    `_jaros_write` (EXT-037 REQ-9) idiom exactly: when `runtime` is given -- any object exposing
    `.apply(decision)`, e.g. `harness.coding_loop.Runtime` -- the write is performed as a real
    `code.write_file` Decision applied through it, so it gets the SAME gate (`validate_decision`)
    + EXT-037 root-jail + hash-chain log every other Jaros write Decision goes through, instead of
    a raw `Path.write_text`. `runtime=None` (the default -- used by every existing eval/test/
    sandbox caller against a throwaway temp dir with no meaningful project root) preserves the
    exact prior direct-write behavior byte-for-byte. Returns `None` on success, else an honest
    error string -- a gate rejection (e.g. the path escapes root) degrades to a message here,
    never a crash."""
    path = str(path)
    if runtime is None:
        Path(path).write_text(content, encoding="utf-8", newline="\n")
        return None
    try:
        from jaros.core import create_decision
        decision = create_decision(
            id=f"multifile-write-{uuid.uuid4().hex}", source="multi_file",
            type="code.write_file",
            payload={"path": path, "content": content, "root": str(root)},
        )
        runtime.apply(decision)
    except Exception as exc:
        return f"failed to write {path}: {exc}"
    return None
# #EXT-037-REQ-10 End


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
    # #EXT-010-REQ-5 Start
    # Seed with the test file resolved against root (not the bare test_file), so the seed
    # read below succeeds regardless of the process cwd (every isolated eval/SWE-bench run).
    seen, frontier = set(), [str(root / Path(test_file).name)]
    # #EXT-010-REQ-5 End
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
    # Real repos have suites slower than the old hard 30s (jaros-code's own is ~45s), which made every
    # test-gated flow — fix, build, REFACTOR — spuriously report "not green". Configurable, realistic
    # default. A timeout is a non-green run, never a crash.
    to = int(os.environ.get("JCODE_TEST_TIMEOUT_S", "120"))
    # #EXT-005-REQ-12 Start
    # Use Popen + tree-kill on timeout so an infinite-loop solution can't orphan pytest on Windows.
    kwargs: dict = dict(shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if os.name != "nt":
        kwargs["start_new_session"] = True
    p = subprocess.Popen(test_cmd, cwd=cwd, **kwargs)
    try:
        stdout, stderr = p.communicate(timeout=to)
        return p.returncode == 0, (stdout or "") + (stderr or "")
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                f"taskkill /F /T /PID {p.pid}",
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            import signal
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            p.communicate(timeout=5)
        except Exception:
            pass
        return False, f"test command timed out after {to}s (treated as not-passing): {test_cmd}"
    # #EXT-005-REQ-12 End


def _snapshot(cwd: str) -> dict[str, str]:
    """In-memory copy of every repo .py keyed by FULL path — so subdir/package files with the
    same basename don't collide (the old flatten-by-name snapshot could corrupt them)."""
    return {str(p): p.read_text(encoding="utf-8") for p in Path(cwd).rglob("*.py")}


def _restore(snap: dict[str, str], *, runtime: "object | None" = None,
             root: "str | None" = None) -> "str | None":
    """Restore every `{path: content}` pair in `snap`.

    `runtime`/`root` (EXT-037 REQ-10, Tenet 1): optional -- `_restore` is SHARED by more than
    `/fixrepo` (`multi_file_fix`'s own internal revert-on-no-progress path below) -- it is also
    imported directly by `harness/cli.py`'s `cmd_undo` (EXT-009 `/undo`) and by
    `harness/refactor.py`'s rename/move revert paths. When `runtime` is given, each file write is
    routed through `_jaros_write` as a real `code.write_file` Decision (gated, EXT-037
    root-jailed via `root`, hash-chain logged) instead of a raw `Path.write_text`. `runtime=None`
    (the default) is byte-identical to the pre-existing behavior -- every caller that omits it
    (every eval/test caller, and `harness/refactor.py`, unchanged by this task) is unaffected.
    Returns `None` on full success, or the first honest error string encountered (a gate
    rejection never crashes and never stops the remaining files from being attempted)."""
    err: "str | None" = None
    for path, text in snap.items():
        e = _jaros_write(path, text, root, runtime)
        if e and err is None:
            err = e
    return err


def _fail_count(out: str) -> int:
    nums = [int(m) for m in re.findall(r"(\d+)\s+(?:failed|error)", out or "")]
    return sum(nums) if nums else 1


# #EXT-010-REQ-6 Start
def _minimize_edits(cwd: str, test_cmd: str, orig: dict[str, str],
                     kept_paths: list[str], *,
                     runtime: "object | None" = None) -> tuple[list[str], list[str]]:
    """Delta-debugging minimization pass (GAP-MAP #3, diff cleanliness): once the cumulative
    loop in multi_file_fix has reached all-green, some of the KEPT edits may have become
    redundant — a partial-progress "symptom patch" that was necessary before the root-cause fix
    landed, but is no longer needed once it did. For each kept edit, in REVERSE (most-recently
    -kept-first) order, temporarily revert that single file to its ORIGINAL (pre-edit) content
    and re-run the suite:
      - still all-green -> the edit was redundant; leave it reverted and record it as dropped
      - not green -> the edit is necessary; restore its fixed content before moving on

    Purely deterministic + test-gated, no model call. Invariant: the repo is all-green both
    before and after every single probe in this loop (a redundant drop is confirmed green by the
    very run that drops it; a non-green probe is always undone before the next probe), so the
    final state is guaranteed all-green with the minimal necessary edit set — this can never
    leave the repo failing, and can never drop an edit that the suite actually needs.

    `runtime` (EXT-037 REQ-10, Tenet 1): optional, same contract as `_restore`/`_jaros_write` --
    when given, both probe writes below are routed through a real `code.write_file` Decision
    instead of a raw `Path.write_text`. `runtime=None` (the default, used by every existing
    eval/test caller against a throwaway temp dir) is unchanged from before this parameter
    existed. If a probe write is refused by the gate (should not happen for an in-root candidate
    file, but never trusted to raise), that edit is conservatively left KEPT/untouched rather
    than risk shipping a half-reverted file -- never a crash."""
    kept_min = list(kept_paths)
    dropped: list[str] = []
    for path in reversed(kept_paths):
        if path not in orig:
            continue  # not part of the pre-edit snapshot (e.g. a new file) — keep it, don't touch
        fixed_content = Path(path).read_text(encoding="utf-8")
        # #EXT-037-REQ-10 Start
        err = _jaros_write(path, orig[path], cwd, runtime)
        if err:
            continue  # couldn't even probe this edit -- leave it kept, exactly as it was
        # #EXT-037-REQ-10 End
        ok, _ = _run(cwd, test_cmd)
        if ok:
            dropped.append(Path(path).name)
            kept_min.remove(path)
        else:
            # #EXT-037-REQ-10 Start
            _jaros_write(path, fixed_content, cwd, runtime)  # restore the necessary fix
            # #EXT-037-REQ-10 End
    return kept_min, dropped
# #EXT-010-REQ-6 End


def multi_file_fix(cwd: str, test_cmd: str, instruction: str, test_file: str,
                   *, max_iters: int = 3, verbose: bool = False,
                   runtime: "object | None" = None,
                   interrupt: "object | None" = None) -> dict:
    """Fix a failing multi-file test. Locate candidate files, then fix them CUMULATIVELY: try
    each candidate with fix_loop(keep_partial=True) so its best partial edit survives; KEEP the
    edit only if it strictly REDUCES the failing-test count (and build the next fix on top),
    else revert it. Resolves faults that span several files, not just a single-file fault.
    Once all-green, a deterministic minimization pass (_minimize_edits, REQ-6) drops any kept
    edit that turned out redundant (e.g. a caller-side symptom patch superseded by a later
    root-cause fix), so the final result is the MINIMAL necessary edit set — a clean diff.

    No candidate-count cap: the candidates are only files in the IMPORT CLOSURE reachable from
    the failing test (naturally small for realistic tests), and a count cap can silently
    EXCLUDE the culprit — for a logic bug the traceback doesn't name it, so its rank is just
    import order. If pathological cost ever bites, bound it with a time budget, not a count.

    `runtime` (EXT-037 REQ-10, Tenet 1): optional -- any object exposing `.apply(decision)`, e.g.
    `harness.coding_loop.Runtime`. When given, every REVERT this function performs (the
    no-progress `_restore` below, and `_minimize_edits`'s probe writes) is routed through a real
    `code.write_file` Decision (gated, EXT-037 root-jailed, hash-chain logged) instead of a raw
    `Path.write_text`. `runtime=None` (the default) is unchanged from before this parameter
    existed -- every eval/test/sandbox caller (`harness/daily_driver.py`, `harness/multifile_eval.py`,
    `harness/spec_loop.py`, `harness/agent_loop.py`, `tests/test_ext003_multifile.py`) against a
    throwaway temp dir keeps the exact prior raw-write behavior.

    `interrupt` (EXT-055 REQ-2, Tenet 1): optional -- any object exposing `.is_cancelled() ->
    bool` (e.g. `harness.interrupt.InterruptController`). Checked ONLY at the TOP of the
    per-candidate loop below, i.e. a SAFE point before starting work on the NEXT candidate --
    never mid-fix, never mid-write. When cancelled, this function stops trying further
    candidates and returns its CURRENT partial result (whatever was kept so far) with an honest
    note, instead of continuing. `interrupt=None` (the default -- every existing eval/test/sandbox
    caller) is byte-identical to before this parameter existed."""
    from harness.coding_loop import fix_loop  # local import: avoid cycle at module load

    ok, out = _run(cwd, test_cmd)
    if ok:
        return {"solved": True, "file": None, "tried": [], "fixed": [], "dropped": [],
                "note": "already passing"}

    # #EXT-010-REQ-6 Start
    orig = _snapshot(cwd)  # pre-edit contents of every repo .py, for the minimization pass below
    # #EXT-010-REQ-6 End
    base = _fail_count(out)
    cands = candidate_files(cwd, out, test_file)
    tried, kept, kept_paths = [], [], []
    for cand in cands:
        # #EXT-055-REQ-2 Start
        # Cooperative cancel check (EXT-055): a SAFE point -- before starting the NEXT candidate,
        # never mid-fix. `interrupt=None` (the default) makes this a complete no-op.
        if interrupt is not None and interrupt.is_cancelled():
            return {"solved": False, "file": None, "tried": tried, "fixed": kept, "dropped": [],
                    "note": f"interrupted after {len(tried)} step(s) — partial work preserved; "
                            "/rewind to undo"}
        # #EXT-055-REQ-2 End
        snap = _snapshot(cwd)
        tried.append(Path(cand).name)
        fix_loop(cand, instruction, test_cmd, max_iters=max_iters, cwd=cwd,
                 verbose=verbose, keep_partial=True)
        ok, out = _run(cwd, test_cmd)
        if ok:
            kept.append(Path(cand).name)
            kept_paths.append(cand)
            # #EXT-010-REQ-6 Start
            kept_paths, dropped = _minimize_edits(cwd, test_cmd, orig, kept_paths,
                                                   runtime=runtime)
            kept = [Path(p).name for p in kept_paths]
            file = kept[-1] if kept else Path(cand).name
            return {"solved": True, "file": file, "tried": tried, "fixed": kept,
                    "dropped": dropped, "note": "fixed"}
            # #EXT-010-REQ-6 End
        nf = _fail_count(out)
        if nf < base:                 # strict progress — keep this partial, build on it
            base = nf
            kept.append(Path(cand).name)
            kept_paths.append(cand)
        else:                         # no progress (distractor / harmless rewrite) — revert
            # #EXT-037-REQ-10 Start
            _restore(snap, runtime=runtime, root=cwd)
            # #EXT-037-REQ-10 End
    return {"solved": False, "file": None, "tried": tried, "fixed": kept, "dropped": [],
            "note": "no candidate fixed it"}
