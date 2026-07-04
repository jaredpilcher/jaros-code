---
id: EXT-039
title: Datastore Setup + Acceptance
status: partial
priority: high
implementation:
  - harness/datastore_oracle.py
  - tests/test_ext039_datastore_oracle.py
  - harness/system_suite.py
---

**Owner directive (2026-07-04, PRIME-001 real-systems roadmap, `docs/GAP-MAP.md` task #86):** the
prompt->system product must eventually set up + verify REAL external datastores (Postgres, Redis,
Qdrant, Cassandra) as part of the systems it builds — but those all need a running service, which
this repo's offline/no-network test discipline (Tenet 3) cannot exercise honestly today. `sqlite3`
is the one datastore stdlib already ships, is fully deterministic, and needs no running service —
so it is the first, offline-testable rung: it proves the ACCEPTANCE-ORACLE PATTERN (independently
verify real persisted state, never trust the CLI's own stdout) that a later, real-service
provisioner (REQ-2, named below, not built here) will plug into unchanged.

**The gap this closes (Tenet 3, exactly analogous to the server oracle):** `harness.server_oracle`
(EXT-036 REQ-22) proved that `build_system` could report `done=True` for a FastAPI service that
only *imported* successfully, never actually verified over real HTTP — a hollow pass. The same
hollow-done class exists for persistence: a generated CLI can print `"Saved!"` on every `add`
command and never touch a database file at all, or keep its state in an in-process dict that
vanishes the instant the process exits — and today's checklist/stdout-based acceptance has no way
to catch either case, because it only ever reads what the CLI prints, never what actually landed on
disk. This spec's oracle closes that gap for the sqlite case by INDEPENDENTLY opening the resulting
`.db` file with stdlib `sqlite3` and asserting real rows/values — never trusting stdout — and by
proving persistence survives a **second, fresh CLI invocation** (a process boundary), which an
in-memory-only fake cannot fake.

### [REQ-1] SQLite datastore acceptance oracle — catch the hollow-persistence-done class  (partial)

Build a standalone, deterministic (execution-plane only — no model call anywhere in this module)
`harness/datastore_oracle.py` providing:

- `detect_sqlite_datastore(root) -> DatastoreInfo | None` — a best-effort, NEVER-RAISE scan of the
  built system's sources/root for `sqlite3` usage (an `import sqlite3` / `from sqlite3 import ...`)
  and/or a declared or derivable `.db` file path (a string literal ending in `.db`, or an existing
  `.db` file already present under `root`). Returns what DB file the system appears to use; returns
  an honest `None` when no sqlite usage can be determined — this is a best-effort detector, not a
  perfect one, and never fabricates a guess it cannot support.
- `verify_persistence(root, *, db_path, drive_cmds, assertions, python_exe) -> DatastoreResult` —
  the load-bearing oracle. It (a) starts from a clean state (removes any pre-existing `db_path` so
  the run begins from a known-empty database); (b) DRIVES the built system's CLI entrypoint through
  `harness.system_suite._run_cli` (the existing sandboxed, scrubbed-environment CLI runner — reused,
  not reimplemented) to perform the write operations named in `drive_cmds`; (c) then INDEPENDENTLY
  opens the resulting `db_path` with stdlib `sqlite3` (a fresh connection this module owns, never
  the CLI's own process) and evaluates `assertions` against the real on-disk rows/values — NOT the
  CLI's stdout; (d) additionally proves CROSS-INVOCATION persistence: it drives a SECOND, entirely
  fresh CLI invocation (a new subprocess, no shared in-process state with the first) and re-checks
  that state written by the first invocation is visible to/through the second — proving the data
  actually reached disk, not just an in-process dict that happened to still be alive.
- `DatastoreResult{ok, rows_checked, failures, note}` — `ok` is only `True` when the database file
  exists, every assertion passes against the independently-queried rows, AND the cross-invocation
  check passes. NEVER RAISES (mirrors `harness/server_oracle.py`'s discipline exactly): a missing db
  file, a broken/crashing CLI, a malformed `assertions`/`drive_cmds` argument, or a failed assertion
  is always reported as an honest `ok=False` with a diagnostic `note` — never coerced to a pass and
  never an uncaught exception.
- An explicit, named, **NOT-built-here** extension seam: the module is structured (a narrow
  `verify_persistence`-shaped interface, sqlite-specific detail isolated to this one module) so a
  future non-sqlite backend — a `ServiceProvisioner` for Postgres/Redis (bring a real service up on
  localhost, cap it, tear it down) — can plug into the SAME verify contract without this module's
  sqlite-specific internals changing. Building that real-service provisioner is out of scope here
  (see REQ-2) because it needs an actual running service and cannot be proven by this repo's
  offline test discipline.
- A small DATASTORE creation-task tier added to `harness/system_suite.py` (or a sibling task list):
  1-2 sentence->system tasks that REQUIRE a sqlite-backed CLI with cross-invocation persistence,
  contract-precise (pinned `main.py` entrypoint, exact commands, exact stdout) per the existing
  suite's convention (TASK-15's proven fix for vague-sentence false negatives), so a failure is
  never a vague-sentence artifact. Each such task's checks run BOTH the existing black-box CLI
  oracle AND `verify_persistence`, so acceptance requires both a correct CLI surface and real rows.

**HONEST STATUS (Tenet 3, TASK-1):** `harness/datastore_oracle.py` lands standalone, pure stdlib
(`sqlite3`, `re`, `pathlib` — no new dependency), reusing `harness.system_suite._run_cli` (the
existing sandboxed CLI runner) rather than reimplementing subprocess handling. `detect_sqlite_datastore`
and `verify_persistence` never raise on any tested failure mode (missing db, broken CLI, malformed
input). A single new `notes-cli` DATASTORE task is added to `harness/system_suite.py`'s task list,
with checks covering both the black-box CLI surface and `verify_persistence`. Proven by an offline
test suite (`tests/test_ext039_datastore_oracle.py`) using small hand-written CLI fixtures (never a
live `build_system`/gemma run in pytest) — including the LOAD-BEARING catch: a fake CLI that prints
`"Saved!"` but never writes to the db is correctly rejected (`ok=False`), and a CLI that keeps state
only in-memory (never persists to the file) is correctly rejected by the cross-invocation check.

**HONEST SCOPE:** this module is additive and self-contained. It is NOT wired into `build_system`'s
acceptance pipeline or the orchestrator — that wiring (so a real sentence->system build of a
persistence-requiring task actually calls this oracle as part of `done`) is an explicit, separate,
later follow-up, not silently deferred. A live `build_system` + gemma smoke run of the new datastore
creation task is likewise a manual follow-up, not part of the offline pytest suite.

#### Acceptance Criteria
- [x] `detect_sqlite_datastore(root) -> DatastoreInfo | None` exists in `harness/datastore_oracle.py`,
  never raises on malformed/missing input, finds the db file for a sqlite-using system (via source
  scan and/or an existing `.db` file under root), and returns an honest `None` when no datastore use
  can be determined
- [x] `verify_persistence(root, *, db_path, drive_cmds, assertions, python_exe) -> DatastoreResult`
  starts from a clean state (any pre-existing `db_path` is removed first), drives the built CLI
  through `harness.system_suite._run_cli` (reused, not reimplemented) to perform `drive_cmds`, then
  INDEPENDENTLY opens `db_path` via stdlib `sqlite3` (a fresh connection, never the CLI's own
  process/stdout) and evaluates `assertions` against the real persisted rows/values
- [x] **THE LOAD-BEARING CATCH:** a CLI that prints a success message (e.g. `"Saved!"`) but never
  writes to the database file is correctly rejected — `verify_persistence` returns `ok=False`, not
  fooled by stdout
- [x] Cross-invocation persistence is verified: state written by one CLI invocation is checked via a
  SECOND, entirely fresh CLI invocation (new subprocess) plus the independent `sqlite3` query — a CLI
  that only keeps state in an in-process structure (never reaching disk) is correctly rejected
- [x] `DatastoreResult{ok, rows_checked, failures, note}` never raises: a missing db file, a broken
  CLI (non-zero exit / crash), or malformed `assertions`/`drive_cmds` input is an honest `ok=False`
  with a diagnostic `note`, never an uncaught exception and never a fabricated pass
- [x] The module names, but explicitly does NOT build, a `ServiceProvisioner` extension seam for a
  future real-service (Postgres/Redis) backend that would plug into the same `verify_persistence`
  contract — documented in code + this spec, not silently omitted
- [x] A small DATASTORE creation-task tier is added to `harness/system_suite.py`'s task list: a
  contract-precise sentence->system task (pinned `main.py`, exact commands, exact stdout) requiring a
  sqlite-backed CLI with cross-invocation persistence, whose checks exercise both the black-box CLI
  oracle and `verify_persistence`
- [x] Proven by an OFFLINE, deterministic test suite (`tests/test_ext039_datastore_oracle.py`) using
  small hand-written CLI fixtures in a temp directory — no external service, no live
  `build_system`/gemma run in pytest (that is an explicit, separate manual smoke)

### [REQ-2] Real-service datastore provisioning (Postgres/Redis/Qdrant/Cassandra) — not started

A later requirement/task: a `ServiceProvisioner` that brings a REAL external datastore service up
on localhost (or connects to an already-running one), applies resource/connection caps, and tears
it down cleanly — plugging into the SAME `verify_persistence`-shaped acceptance contract REQ-1
established for sqlite. This genuinely needs a running service (Postgres/Redis/Qdrant/Cassandra) and
so cannot be proven by this repo's offline/no-network test discipline the way REQ-1 was; it is named
here honestly as the next rung, not silently deferred, and is explicitly OUT OF SCOPE for this spec's
first task.
