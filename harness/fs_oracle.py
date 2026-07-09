"""EXT-059 REQ-1: a deterministic, model-free FILESYSTEM acceptance oracle.

**The gap this closes (Tenet 3), mirroring `harness/datastore_oracle.py` (EXT-039 REQ-1) and
`harness/server_oracle.py` (EXT-036 REQ-22) exactly:** today's black-box CLI oracle
(`harness.system_suite._run_single_check`) only ever reads a built system's own STDOUT. A "move
this file", "write a report to disk", "generate a static site", or "scaffold these files" task can
print `"Moved!"`/`"Done!"` and never actually touch the filesystem at all, or write the wrong
bytes/paths -- and nothing that only reads stdout can ever catch that. This module closes that gap
for filesystem-effect tasks by seeding a declarative input tree, running the built entrypoint as a
real subprocess, and then INDEPENDENTLY re-reading the resulting tree from disk -- never trusting
the built program's own stdout for the effect.

Two-plane discipline holds throughout: this module is pure, deterministic execution-plane code
(stdlib `pathlib`/`subprocess`/`tempfile` only -- no new dependency, no model/reasoning call
anywhere). The built entrypoint is launched SANDBOXED, reusing (not reimplementing) the existing
audited primitives: `harness.secure_exec._scrubbed_env` / `_make_preexec_fn` for the
scrubbed-environment + POSIX-resource-capped subprocess launch (the same convention
`harness.server_oracle._launch` already uses), and `harness.server_oracle._kill_tree` for
process-tree teardown -- unconditionally, in a `finally` block, so a built program that spawns a
detached child (e.g. a background watcher) never survives a check.

**NEVER RAISES**, mirroring `harness/datastore_oracle.py` / `harness/server_oracle.py` exactly: a
missing entrypoint, a broken/crashing/timing-out program, or a malformed spec/check is always an
honest `ok=False` (or a per-entry failure message) with a diagnostic `note` -- never coerced to a
pass, never an uncaught exception.

**OS-independent, no host-path leakage:** every path in a seed spec or a check is interpreted as a
POSIX-style relative path (forward slashes accepted on any OS, backslashes normalized), rejecting
any path that is absolute or escapes the seeded/inspected root (`..` segments) so a spec/check can
never read or write outside the caller-provided temp `root`. `dir_members_equal` compares an EXACT
SORTED membership set so check results are reproducible across platforms. This module builds no
prompts at all -- it is a pure post-build verifier -- so there is nothing here that could leak a
host path into a build prompt.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# #EXT-059-REQ-1 Start
# TASK-1: reuse (not reimplement) the audited sandboxed-launch primitives `server_oracle._launch`
# already uses, and the audited process-tree-teardown helper `server_oracle` already defines.
from harness.secure_exec import _make_preexec_fn, _scrubbed_env
from harness.server_oracle import _kill_tree

DEFAULT_TIMEOUT_S = 15.0  # a hang is a real failure, never a hang (mirrors system_suite's default)


@dataclass
class FsCheckResult:
    """Result of :func:`run_and_inspect`. ``ok`` is True only when the built entrypoint could be
    launched and EVERY post-condition in ``checks`` held against the independently-re-read tree.
    ``failures`` is a list of human-readable diagnostic strings (empty when ``ok`` is True);
    ``note`` always carries a short, honest summary -- never fabricated, never silently swallowed.
    """

    ok: bool
    checks_passed: int = 0
    failures: "list" = field(default_factory=list)
    note: str = ""


def _norm_rel(path_str: Any) -> str:
    """Normalize a path string to a canonical forward-slash, no-redundant-separator relative form
    (``.`` segments and duplicate slashes collapsed) -- so a check/seed entry written with either
    slash style, or with a leading ``./``, still matches consistently across Windows and POSIX."""
    s = str(path_str).strip().replace("\\", "/")
    parts = [p for p in s.split("/") if p not in ("", ".")]
    return "/".join(parts)


def _is_safe_rel_path(path_str: Any) -> bool:
    """True only when ``path_str`` is a non-empty, genuinely RELATIVE path with no leading ``/``,
    no Windows drive letter, and no ``..`` segment -- so a seeded file, or an inspected check
    path, can never land (or read) outside the caller-provided ``root``."""
    if not isinstance(path_str, str) or not path_str.strip():
        return False
    s = path_str.strip().replace("\\", "/")
    if s.startswith("/"):
        return False
    if len(s) >= 2 and s[1] == ":" and s[0].isalpha():  # e.g. "C:/x" -- Windows drive-absolute
        return False
    parts = [p for p in s.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return False
    return True


def seed_tree(root: Any, spec: "list") -> "tuple[bool, str]":
    """Materialize a declarative file tree under ``root``: ``spec`` is a list of
    ``{"path": <relative path str>, "bytes": <str|bytes>}`` entries. Parent directories implied
    by a nested path (e.g. ``"a/b/c.txt"``) are created automatically -- there is no separate
    "directories" list, subdirs are always implied by the files placed inside them.

    Returns ``(ok, note)``. NEVER RAISES: a malformed entry, an unsafe/escaping path, or an
    OS-level write failure is reported as an honest ``ok=False`` with a diagnostic ``note`` --
    no entry is ever silently skipped and no write ever lands outside ``root``.
    """
    try:
        try:
            root_path = Path(root)
        except (TypeError, ValueError) as exc:
            return False, f"invalid root: {root!r}: {exc}"
        try:
            root_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, f"could not create root {root_path}: {exc}"

        entries = list(spec) if isinstance(spec, (list, tuple)) else None
        if entries is None:
            return False, f"spec must be a list of {{'path':..., 'bytes':...}} entries, got {type(spec)!r}"

        for i, entry in enumerate(entries):
            if not isinstance(entry, dict) or "path" not in entry:
                return False, f"seed_tree spec[{i}] malformed (needs a 'path' key): {entry!r}"
            raw_path = entry["path"]
            if not _is_safe_rel_path(raw_path):
                return False, f"seed_tree spec[{i}] has an unsafe/escaping path: {raw_path!r}"
            rel = _norm_rel(raw_path)

            data = entry.get("bytes", b"")
            if isinstance(data, str):
                data = data.encode("utf-8")
            elif not isinstance(data, (bytes, bytearray)):
                return False, f"seed_tree spec[{i}] 'bytes' must be str or bytes, got {type(data)!r}"

            file_path = root_path / rel
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(bytes(data))
            except OSError as exc:
                return False, f"seed_tree spec[{i}] failed to write {rel!r}: {exc}"

        return True, "ok"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"seed_tree failed unexpectedly: {exc}"


def _launch_entrypoint(root_path: Path, py_exe: str, entry_path: Path, argv: "list[str]",
                        out_fh, err_fh, *, mem_mb: int = 512, cpu_budget_s: float = 60):
    """Launch the built entrypoint as a foreground, SANDBOXED subprocess: a scrubbed environment
    (``harness.secure_exec._scrubbed_env`` -- no ambient host secrets reach the model-generated
    program) plus (POSIX) the same RLIMIT_AS/RLIMIT_CPU resource caps
    ``harness.secure_exec._make_preexec_fn`` applies, started in its own process group/session so
    any child tree it spawns can be torn down wholesale via ``server_oracle._kill_tree`` -- the
    exact launch discipline ``harness.server_oracle._launch`` already uses, reused here rather
    than reimplemented."""
    env = _scrubbed_env({
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(root_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    })
    cmd = [py_exe, str(entry_path)] + list(argv or [])
    popen_kwargs: dict = dict(cwd=str(root_path), stdout=out_fh, stderr=err_fh, env=env)
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
        preexec_fn = _make_preexec_fn(mem_mb, cpu_budget_s)
        if preexec_fn is not None:
            popen_kwargs["preexec_fn"] = preexec_fn
    return subprocess.Popen(cmd, **popen_kwargs)


def _tail(path, limit: int = 800) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def _eval_check(root_path: Path, check: Any) -> "tuple[bool, str]":
    """Evaluate ONE post-condition against the tree at ``root_path``, read INDEPENDENTLY (this
    function never looks at the built program's stdout). Supported ``check["kind"]`` values:
    ``path_exists``, ``path_absent``, ``file_bytes_equal`` (exact byte comparison, ``check["bytes"]``
    a ``str``/``bytes``), ``dir_members_equal`` (exact SORTED immediate-child membership,
    ``check["members"]`` a list of relative names). Never raises -- a malformed check, an unsafe
    path, or an OS error while reading is reported as an honest ``(False, <reason>)``."""
    try:
        if not isinstance(check, dict):
            return False, f"malformed check (must be a dict), got {type(check)!r}"
        kind = check.get("kind")
        raw_path = check.get("path", "")
        # An empty path means "the root itself" (used by dir_members_equal to inspect root's own
        # immediate children) -- every other, non-empty path must be a safe relative path.
        if raw_path not in ("", None) and not _is_safe_rel_path(raw_path):
            return False, f"check has an unsafe/escaping path: {raw_path!r}"
        rel = _norm_rel(raw_path) if raw_path else ""
        target = (root_path / rel) if rel else root_path

        if kind == "path_exists":
            return (target.exists(), f"{rel!r} does not exist under the inspected tree")

        if kind == "path_absent":
            exists = target.exists()
            return (not exists, f"{rel!r} unexpectedly exists in the inspected tree")

        if kind == "file_bytes_equal":
            if not target.is_file():
                return False, f"{rel!r} is not a file (missing or a directory)"
            expected = check.get("bytes", b"")
            if isinstance(expected, str):
                expected = expected.encode("utf-8")
            elif not isinstance(expected, (bytes, bytearray)):
                return False, f"check 'bytes' must be str or bytes, got {type(expected)!r}"
            try:
                actual = target.read_bytes()
            except OSError as exc:
                return False, f"could not read {rel!r}: {exc}"
            expected_bytes = bytes(expected)
            if actual != expected_bytes:
                return False, f"{rel!r} bytes mismatch: expected {expected_bytes!r}, got {actual!r}"
            return True, "ok"

        if kind == "dir_members_equal":
            if not target.is_dir():
                return False, f"{rel!r} is not a directory (missing or a file)"
            expected_members = check.get("members")
            if not isinstance(expected_members, (list, tuple)):
                return False, "dir_members_equal check requires a 'members' list"
            expected_sorted = sorted(_norm_rel(m) for m in expected_members)
            try:
                actual_sorted = sorted(p.name for p in target.iterdir())
            except OSError as exc:
                return False, f"could not list {rel!r}: {exc}"
            if actual_sorted != expected_sorted:
                return False, (f"{rel!r} membership mismatch: expected {expected_sorted}, "
                                f"got {actual_sorted}")
            return True, "ok"

        return False, f"unknown check kind: {kind!r}"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"check evaluation raised: {exc}"


def run_and_inspect(root: Any, entrypoint: Any, argv: "list | None", checks: "list", *,
                     timeout: float = DEFAULT_TIMEOUT_S, python_exe: "str | None" = None,
                     mem_mb: int = 512) -> FsCheckResult:
    """The load-bearing oracle: run the built ``entrypoint`` (a filename relative to ``root``) as
    a sandboxed subprocess with ``argv``, then INDEPENDENTLY verify every post-condition in
    ``checks`` against the resulting tree -- never trusting the entrypoint's own stdout.

    1. **Launch** -- the built entrypoint is run via :func:`_launch_entrypoint` (a scrubbed
       environment + POSIX resource caps, mirroring ``harness.server_oracle``'s own sandboxed
       launch convention), bounded by ``timeout``.
    2. **Teardown** -- the process (and any descendants it spawned) is ALWAYS torn down via
       ``server_oracle._kill_tree`` in a ``finally`` block, whether it finished cleanly, crashed,
       or timed out -- so a built program that daemonizes a child never survives a check.
    3. **Independently verify** -- every entry in ``checks`` is evaluated by :func:`_eval_check`,
       which re-reads ``root`` fresh from disk; the entrypoint's own stdout/exit code is never
       consulted for pass/fail (a non-zero exit does not by itself fail the check -- some
       contracts legitimately expect a refusal to leave the tree unchanged, which the relevant
       ``path_absent``/``path_exists`` checks already capture honestly).

    Returns an :class:`FsCheckResult` with ``ok=True`` only when the entrypoint could be launched
    and EVERY check held. NEVER RAISES: any failure at any stage (missing entrypoint, a process
    that never starts, a timeout, a malformed check) is reported as an honest ``ok=False`` with a
    diagnostic ``note`` -- never coerced to a pass.
    """
    try:
        try:
            root_path = Path(root)
        except (TypeError, ValueError) as exc:
            return FsCheckResult(ok=False, note=f"invalid root: {root!r}: {exc}")
        if not root_path.exists() or not root_path.is_dir():
            return FsCheckResult(ok=False, note=f"root does not exist: {root_path}")

        if not entrypoint:
            return FsCheckResult(ok=False, note="no entrypoint supplied")
        entry_path = root_path / str(entrypoint)
        if not entry_path.is_file():
            return FsCheckResult(ok=False, note=f"entrypoint not found: {entry_path.name}")

        checks_list = list(checks) if isinstance(checks, (list, tuple)) else None
        if not checks_list:
            return FsCheckResult(ok=False, note="no checks supplied (must be a non-empty list)")

        argv_list = list(argv) if isinstance(argv, (list, tuple)) else ([] if argv is None else [str(argv)])
        py_exe = python_exe or sys.executable or "python"

        proc = None
        out_fh = err_fh = None
        out_path = err_path = None
        try:
            fd_out, out_path = tempfile.mkstemp(prefix="jcode_fs_oracle_out_")
            fd_err, err_path = tempfile.mkstemp(prefix="jcode_fs_oracle_err_")
            os.close(fd_out)
            os.close(fd_err)
            out_fh = open(out_path, "w", encoding="utf-8")
            err_fh = open(err_path, "w", encoding="utf-8")
            cpu_budget_s = float(timeout) + 30
            proc = _launch_entrypoint(root_path, py_exe, entry_path, argv_list, out_fh, err_fh,
                                       mem_mb=mem_mb, cpu_budget_s=cpu_budget_s)
        except Exception as exc:
            for fh in (out_fh, err_fh):
                try:
                    if fh:
                        fh.close()
                except Exception:
                    pass
            _kill_tree(proc)
            return FsCheckResult(ok=False, note=f"failed to launch entrypoint: {exc}")

        timed_out = False
        try:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
        finally:
            _kill_tree(proc)
            for fh in (out_fh, err_fh):
                try:
                    if fh:
                        fh.close()
                except Exception:
                    pass

        if timed_out:
            tail_out, tail_err = _tail(out_path), _tail(err_path)
            note = f"entrypoint timed out after {timeout}s; process tree killed"
            if tail_out or tail_err:
                note += f" -- stdout tail: {tail_out!r} stderr tail: {tail_err!r}"
            for p in (out_path, err_path):
                try:
                    if p:
                        os.remove(p)
                except OSError:
                    pass
            return FsCheckResult(ok=False, note=note)

        for p in (out_path, err_path):
            try:
                if p:
                    os.remove(p)
            except OSError:
                pass

        # Independent inspection -- re-reads the tree from disk, never the entrypoint's stdout.
        passed = 0
        failures: "list" = []
        for i, check in enumerate(checks_list):
            ok, msg = _eval_check(root_path, check)
            if ok:
                passed += 1
            else:
                kind = check.get("kind") if isinstance(check, dict) else check
                failures.append(f"check[{i}] (kind={kind!r}) failed: {msg}")

        if failures:
            return FsCheckResult(
                ok=False, checks_passed=passed, failures=failures,
                note="one or more post-conditions failed against the independently re-read tree "
                     "-- the entrypoint's own stdout may claim success but the real filesystem "
                     "state does not match",
            )

        return FsCheckResult(ok=True, checks_passed=passed, failures=[],
                              note="ok: every post-condition verified independently against the "
                                   "re-read tree")
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return FsCheckResult(ok=False, note=f"run_and_inspect failed unexpectedly: {exc}")
# #EXT-059-REQ-1 End
