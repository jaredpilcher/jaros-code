"""EXT-039 REQ-1: a SQLite datastore acceptance oracle.

**The gap this closes (Tenet 3, exactly analogous to ``harness/server_oracle.py``, EXT-036
REQ-22):** ``harness.system_builder.build_system``'s acceptance checklist -- and the black-box CLI
oracle in ``harness.system_suite`` -- both grade a build by what its CLI PRINTS. A generated
"persist notes to a database" CLI can print ``"Saved!"`` on every ``add`` and never touch a
database file at all, or keep its state in an in-process structure that vanishes the instant the
process exits -- and nothing that only reads stdout can ever catch that. This module closes that
gap for the SQLite case by INDEPENDENTLY opening the resulting ``.db`` file with stdlib ``sqlite3``
and asserting real rows/state -- never trusting the CLI's own stdout -- and by proving persistence
survives a SECOND, entirely fresh CLI invocation (a real process boundary), which an
in-memory-only fake, or a CLI that silently re-initializes its own storage on every run, cannot
fake.

Two-plane discipline holds throughout: this module is pure, deterministic execution-plane code
(stdlib ``sqlite3``/``re``/``pathlib`` only -- no new dependency, no model/reasoning call
anywhere). Every driven CLI invocation is routed through ``harness.system_suite._run_cli`` (the
existing sandboxed, scrubbed-environment subprocess runner, EXT-037/REQ-7) -- reused, not
reimplemented.

**NEVER RAISES**, mirroring ``harness/server_oracle.py``'s discipline exactly: a missing db file, a
broken/crashing CLI, or malformed input is always an honest ``ok=False`` (or ``None`` for the
detector) with a diagnostic ``note`` -- never coerced to a pass, never an uncaught exception.

**Explicit, NOT-built-here extension seam (EXT-039 REQ-2, a separate later task):** this module is
sqlite-specific by design, but its public shape -- ``verify_persistence(root, *, db_path,
drive_cmds, assertions, python_exe) -> DatastoreResult`` -- is deliberately narrow enough that a
future ``ServiceProvisioner`` for a REAL running-service backend (Postgres, Redis, Qdrant,
Cassandra: bring the service up on localhost or connect to one already running, apply
connection/resource caps, tear it down cleanly in a ``finally`` block mirroring
``server_oracle._kill_tree``'s teardown discipline) could plug into the SAME verify contract
without this module's sqlite-specific internals (the ``sqlite3.connect``/clean-state/file-removal
logic) changing at all. That provisioner is NOT built here -- it needs an actual running service,
which this repo's offline/no-network test discipline cannot exercise honestly today (see
``.jarify/EXT-039/requirements.md`` REQ-2).
"""

from __future__ import annotations

import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# #EXT-039-REQ-1 Start
# TASK-1: reuse (not reimplement) the existing sandboxed, scrubbed-environment CLI runner every
# other black-box check in this codebase already goes through (EXT-037/REQ-7).
from harness.system_suite import _run_cli

_SQLITE_IMPORT_RE = re.compile(r"^\s*(?:import\s+sqlite3\b|from\s+sqlite3\s+import\b)", re.M)
_DB_LITERAL_RE = re.compile(r"""["']([\w./\\-]+\.db)["']""")

DEFAULT_ENTRY_NAME = "main.py"


@dataclass
class DatastoreInfo:
    """Best-effort result of :func:`detect_sqlite_datastore`. ``db_path`` is the filename (relative
    to the scanned root) the detector believes the system uses -- ``None`` when a sqlite import was
    found but no concrete path could be determined. ``uses_sqlite`` records whether a ``sqlite3``
    import was actually seen (as opposed to merely finding a stray ``*.db`` file)."""

    db_path: "str | None"
    uses_sqlite: bool
    note: str = ""


@dataclass
class DatastoreResult:
    """Result of :func:`verify_persistence`. ``ok`` is True only when the database file exists,
    every assertion passed BOTH immediately after the drive commands and again after a second,
    entirely fresh CLI invocation, and every driven CLI invocation exited cleanly. ``failures`` is
    a list of human-readable diagnostic strings (empty when ``ok`` is True); ``note`` always
    carries a short, honest summary of what happened -- never fabricated, never silently swallowed.
    """

    ok: bool
    rows_checked: int = 0
    failures: "list" = field(default_factory=list)
    note: str = ""


def count_all_rows(cursor: "sqlite3.Cursor") -> int:
    """Schema-agnostic row count: sum ``COUNT(*)`` across every user table in the currently
    connected database (skips sqlite's own internal ``sqlite_*`` tables). Useful as a generic
    "are there real persisted rows" assertion when the caller does not know (or does not want to
    assume) the exact table/column names a model-generated system chose. Never raises -- a
    malformed cursor or a query error is reported as ``0`` rather than propagated, since a caller
    using this inside an ``assertions`` callable expects a plain int back, not an exception."""
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()
                  if isinstance(row[0], str) and not row[0].startswith("sqlite_")]
        total = 0
        for table in tables:
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                row = cursor.fetchone()
                total += int(row[0]) if row else 0
            except Exception:
                continue
        return total
    except Exception:
        return 0


def detect_sqlite_datastore(root: Any) -> "DatastoreInfo | None":
    """Best-effort, NEVER-RAISE scan of ``root`` for sqlite3 usage: a ``sqlite3`` import in one of
    its ``.py`` sources, and/or an existing ``*.db`` file already present under ``root``. Returns a
    :class:`DatastoreInfo` naming the likely db file (an existing ``.db`` file under root takes
    priority; otherwise a string literal ending in ``.db`` found in a scanned source), or an honest
    ``None`` when no sqlite usage can be determined at all -- this is a best-effort detector, not a
    perfect one, and never fabricates a guess it cannot support."""
    try:
        root_path = Path(root)
    except (TypeError, ValueError):
        return None
    try:
        if not root_path.exists() or not root_path.is_dir():
            return None
    except OSError:
        return None

    uses_sqlite = False
    literal_db: "str | None" = None
    try:
        for py_file in sorted(root_path.rglob("*.py")):
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _SQLITE_IMPORT_RE.search(src):
                uses_sqlite = True
            if literal_db is None:
                m = _DB_LITERAL_RE.search(src)
                if m:
                    literal_db = m.group(1)
    except Exception:
        pass

    existing_db: "str | None" = None
    try:
        db_files = sorted(p.name for p in root_path.glob("*.db"))
        if db_files:
            existing_db = db_files[0]
    except Exception:
        pass

    db_path = existing_db or literal_db
    if not uses_sqlite and db_path is None:
        return None
    if db_path is None:
        return DatastoreInfo(db_path=None, uses_sqlite=True,
                              note="sqlite3 import found but no .db path could be determined")
    return DatastoreInfo(
        db_path=db_path, uses_sqlite=uses_sqlite,
        note="ok" if uses_sqlite else "found a .db file but no sqlite3 import in any scanned source",
    )


def _unpack_cmd(cmd: Any) -> "tuple[list, str | None]":
    """A drive/cross-invocation command is a 2-item ``(argv, stdin)`` sequence. Raises on a
    genuinely malformed entry -- caught by the caller's outer guard, never left to propagate to
    :func:`verify_persistence`'s caller."""
    argv, stdin = cmd
    argv = list(argv) if isinstance(argv, (list, tuple)) else ([] if argv is None else [str(argv)])
    stdin = stdin if (stdin is None or isinstance(stdin, str)) else str(stdin)
    return argv, stdin


def _check_assertions(db_file: Path, asserts: "list") -> "tuple[int, list]":
    """Open a FRESH ``sqlite3`` connection to ``db_file`` (never the CLI's own process/stdout) and
    evaluate every assertion in ``asserts`` -- each either a ``callable(cursor) -> bool`` or a
    ``(sql, expected_rows)`` tuple (``cur.execute(sql).fetchall() == expected_rows``). Returns
    ``(n_passed, failure_messages)``. Never raises -- a query error or a bad assertion spec is
    recorded as a failure message, not propagated."""
    passed = 0
    failures: "list" = []
    conn = None
    try:
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()
        for idx, spec in enumerate(asserts):
            try:
                if callable(spec):
                    ok = bool(spec(cur))
                else:
                    sql, expected = spec
                    cur.execute(sql)
                    rows = cur.fetchall()
                    ok = (rows == expected)
                if ok:
                    passed += 1
                else:
                    failures.append(f"assertion[{idx}] did not hold against the persisted db")
            except Exception as exc:
                failures.append(f"assertion[{idx}] raised while evaluating: {exc}")
    except Exception as exc:
        failures.append(f"could not open/query database file {db_file}: {exc}")
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
    return passed, failures


def verify_persistence(root: Any, *, db_path: Any, drive_cmds: "list", assertions: "list",
                        python_exe: "str | None" = None,
                        cross_invocation_cmd: "tuple | None" = None,
                        entry_name: str = DEFAULT_ENTRY_NAME) -> DatastoreResult:
    """The load-bearing oracle: drive the built system's CLI, then INDEPENDENTLY verify real
    persisted state -- never trusting the CLI's own stdout.

    1. **Clean state** -- any pre-existing file at ``root/db_path`` is removed first, so every run
       starts from a known-empty database (reproducible, Tenet 3).
    2. **Drive** -- each entry of ``drive_cmds`` (a list of ``(argv, stdin)`` pairs) is run as its
       OWN, separate ``harness.system_suite._run_cli`` subprocess invocation, in order (reused, not
       reimplemented -- the same sandboxed/scrubbed/DENY_ALL-egress runner every other black-box
       CLI check in this codebase already uses).
    3. **Independently verify** -- a FRESH ``sqlite3`` connection this module owns (never the
       CLI's) is opened against the resulting db file and every entry in ``assertions`` is
       evaluated against the REAL persisted rows.
    4. **Cross-invocation** -- one more, entirely fresh ``_run_cli`` invocation is run (defaulting
       to a re-run of the LAST ``drive_cmds`` entry when ``cross_invocation_cmd`` is not supplied),
       and the SAME assertions are re-evaluated via a second fresh connection -- proving the data
       survived a genuine process boundary, not just an in-process cache/dict, and catching a CLI
       that silently re-initializes its own storage on every run.

    Returns a :class:`DatastoreResult` with ``ok=True`` only when the db file exists, every driven
    CLI invocation exited cleanly, and every assertion held on BOTH independent checks. NEVER
    RAISES: any failure at any stage (missing entrypoint, missing db, a broken/crashing CLI,
    malformed ``drive_cmds``/``assertions``, or any unexpected exception) is reported as an honest
    ``ok=False`` with a diagnostic ``note`` -- never coerced to a pass.
    """
    try:
        try:
            root_path = Path(root)
        except (TypeError, ValueError) as exc:
            return DatastoreResult(ok=False, note=f"invalid root: {root!r}: {exc}")
        if not root_path.exists() or not root_path.is_dir():
            return DatastoreResult(ok=False, note=f"root does not exist: {root_path}")

        if not db_path:
            return DatastoreResult(ok=False, note="no db_path supplied")
        try:
            db_file = root_path / str(db_path)
        except Exception as exc:
            return DatastoreResult(ok=False, note=f"invalid db_path {db_path!r}: {exc}")

        entry_path = root_path / entry_name
        if not entry_path.is_file():
            return DatastoreResult(ok=False, note=f"entrypoint not found: {entry_path}")

        py_exe = python_exe or sys.executable or "python"

        # Step 1 -- clean state.
        try:
            if db_file.exists():
                db_file.unlink()
        except OSError as exc:
            return DatastoreResult(ok=False, note=f"could not clear pre-existing db file: {exc}")

        cmds = list(drive_cmds) if isinstance(drive_cmds, (list, tuple)) else None
        if not cmds:
            return DatastoreResult(ok=False, note="no drive_cmds supplied (must be a non-empty list)")

        asserts = list(assertions) if isinstance(assertions, (list, tuple)) else None
        if not asserts:
            return DatastoreResult(ok=False, note="no assertions supplied (must be a non-empty list)")

        # Step 2 -- drive each command as its own fresh subprocess invocation.
        for i, raw_cmd in enumerate(cmds):
            try:
                argv, stdin = _unpack_cmd(raw_cmd)
            except Exception as exc:
                return DatastoreResult(ok=False, note=f"malformed drive_cmds[{i}]: {exc}")
            ok, out = _run_cli(py_exe, entry_path, argv, stdin, root_path)
            if not ok:
                return DatastoreResult(
                    ok=False,
                    note=f"drive_cmds[{i}] CLI invocation failed (non-zero exit): {out[:500]!r}",
                )

        if not db_file.exists():
            return DatastoreResult(
                ok=False,
                note=(f"database file was never created at {db_file} -- the CLI never actually "
                      "wrote to a datastore (hollow-persistence: stdout may claim success, the "
                      "file does not exist)"),
            )

        # Step 3 -- independent check #1 (right after the drive commands).
        passed1, failures1 = _check_assertions(db_file, asserts)
        if failures1:
            return DatastoreResult(
                ok=False, rows_checked=passed1, failures=failures1,
                note="assertions failed against the independently-queried db right after the "
                     "drive commands -- the CLI's stdout may claim success but the real "
                     "persisted state does not match (hollow-persistence catch)",
            )

        # Step 4 -- cross-invocation: one more, entirely fresh CLI process.
        cross_cmd = cross_invocation_cmd if cross_invocation_cmd is not None else cmds[-1]
        try:
            cross_argv, cross_stdin = _unpack_cmd(cross_cmd)
        except Exception as exc:
            return DatastoreResult(ok=False, rows_checked=passed1,
                                    note=f"malformed cross_invocation_cmd: {exc}")
        ok, out = _run_cli(py_exe, entry_path, cross_argv, cross_stdin, root_path)
        if not ok:
            return DatastoreResult(
                ok=False, rows_checked=passed1,
                note=f"cross-invocation CLI call failed (non-zero exit): {out[:500]!r}",
            )

        if not db_file.exists():
            return DatastoreResult(
                ok=False, rows_checked=passed1,
                note="database file vanished after the cross-invocation CLI call",
            )

        passed2, failures2 = _check_assertions(db_file, asserts)
        if failures2:
            return DatastoreResult(
                ok=False, rows_checked=passed2, failures=failures2,
                note="assertions failed after a SECOND, entirely fresh CLI invocation -- the "
                     "state did not survive the process boundary (in-memory-only storage, or a "
                     "CLI that silently re-initializes its own storage on every run)",
            )

        return DatastoreResult(ok=True, rows_checked=passed2, failures=[],
                                note="ok: real persisted rows verified independently, both "
                                     "immediately and across a second fresh CLI invocation")
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return DatastoreResult(ok=False, note=f"verify_persistence failed unexpectedly: {exc}")
# #EXT-039-REQ-1 End
