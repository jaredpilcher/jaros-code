# Implementation Tasks

### [TASK-1] SQLite datastore acceptance oracle + a datastore creation-task tier (REQ-1)

Build the standalone `harness/datastore_oracle.py` module (pure stdlib `sqlite3` + reuse of
`harness.system_suite._run_cli`, no new dependency, no model call) implementing
`detect_sqlite_datastore` and `verify_persistence` as described in EXT-039 REQ-1, plus add one small
DATASTORE creation-task tier to `harness/system_suite.py`.

#### Steps
1. Create `harness/datastore_oracle.py` with a `DatastoreInfo` dataclass (`db_path`, `uses_sqlite:
   bool`, `note`) and a `DatastoreResult` dataclass (`ok`, `rows_checked`, `failures: list`, `note`).
2. Implement `detect_sqlite_datastore(root) -> DatastoreInfo | None`: a best-effort, NEVER-RAISE scan
   of the root's `.py` source files for `import sqlite3` / `from sqlite3 import`, and/or an existing
   `*.db` file already present under `root`; derive the likely `db_path` (an existing `.db` file
   under root, or a string literal ending in `.db` found in a scanned source file); return `None`
   honestly when nothing can be determined (no sqlite import found and no `.db` file present).
3. Implement `verify_persistence(root, *, db_path, drive_cmds, assertions, python_exe) ->
   DatastoreResult`: remove any pre-existing db file at `db_path` (clean-state start); resolve the
   CLI entrypoint using the same `root/main.py` convention `system_suite._run_single_check` already
   uses as its fallback; run the FIRST invocation's `drive_cmds` via `harness.system_suite._run_cli`
   (reused, not reimplemented); independently open `db_path` via a fresh `sqlite3.connect` call (this
   module's own connection, never the CLI's) and evaluate each entry in `assertions` (either a
   `callable(cursor) -> bool` or a `(sql, expected_rows)` tuple executed and compared), recording
   pass/fail counts into `rows_checked`/`failures`; then run a SECOND, entirely fresh `_run_cli`
   invocation (a read-only command, e.g. `list`/`count`) to prove cross-invocation persistence, and
   re-open `db_path` independently a second time to re-evaluate the same assertions against it;
   return `DatastoreResult(ok=True, ...)` only when the db file exists, every assertion passed on
   BOTH the first and the post-second-invocation check, and both CLI invocations exited cleanly (via
   `_run_cli`'s own `ok` flag) — any other outcome is `ok=False` with a diagnostic `note` listing
   which stage failed. Wrap the entire function body in a `try`/`except Exception` so it NEVER
   raises: any unexpected error becomes `DatastoreResult(ok=False, rows_checked=0, failures=[...],
   note=f"verify_persistence failed unexpectedly: {exc}")`.
4. Add a module-level docstring/comment documenting the named-but-NOT-built `ServiceProvisioner`
   extension seam for a future non-sqlite backend (Postgres/Redis), per `design.md` — describing how
   a future provisioner would plug into the same `verify_persistence`-shaped contract without this
   module's sqlite-specific internals changing, and explicitly stating that seam is not implemented
   here (that is EXT-039 REQ-2, a separate, later task).
5. Add one new DATASTORE `CreationTask` entry to `harness/system_suite.py`'s task list (a
   `notes.db`-backed notes CLI: single-file `main.py`, `add <text>` appends a note and persists it to
   a SQLite database file `notes.db` in the current directory, `list` prints all notes one per line,
   `count` prints the number of notes; contract-precise sentence — pinned `main.py`, exact commands,
   exact stdout format, `if __name__ == "__main__":` requirement — matching the suite's existing
   TASK-15 convention) whose `checks` include both ordinary black-box CLI checks (via the existing
   3-tuple `(argv, stdin, expected_substring)` shape) AND a callable check
   `(root, plan) -> bool` that invokes `harness.datastore_oracle.verify_persistence` against the
   built root and asserts real rows in `notes.db`.
6. Add `tests/test_ext039_datastore_oracle.py` (OFFLINE, stdlib `sqlite3` only, small hand-written CLI
   fixtures written to a temp dir — NEVER a live `build_system`/gemma run) covering: (a)
   `verify_persistence` returns `ok=True` for a KNOWN-GOOD hand-written sqlite-backed CLI fixture
   (real rows persist across two separate invocations); (b) THE LOAD-BEARING CATCH —
   `verify_persistence` returns `ok=False` for a FAKE CLI fixture that prints `"Saved!"` on `add` but
   never writes to the db file at all; (c) `verify_persistence` returns `ok=False` for a CLI that
   keeps its state only in an in-process/in-memory structure (never persists to the db file), caught
   specifically by the cross-invocation check; (d) `detect_sqlite_datastore` finds the db in a
   sqlite-using fixture system and returns `None` honestly when there is no datastore use at all; (e)
   neither function ever raises on a missing db file, a broken/non-zero-exit CLI, or malformed
   `assertions`/`drive_cmds` input — each is an honest `ok=False`/`None` result instead.
7. Run `python -m pytest tests/test_ext039_datastore_oracle.py -q` first (synchronously, in the
   foreground), then the full `python -m pytest tests/ -q` (synchronously, in the foreground) to
   confirm the whole suite is green with no regression to any existing test.

#### Implements
- [REQ-1] SQLite datastore acceptance oracle — catch the hollow-persistence-done class
