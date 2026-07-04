# EXT-039 — Datastore Setup + Acceptance: Architecture

The datastore oracle closes the same class of Tenet-3 gap the server/HTTP oracle
(`harness/server_oracle.py`, EXT-036 REQ-22) already closed for web services: a build that only
LOOKS done ("it imports" / "it prints Saved!") is not necessarily done. For a system that claims to
persist data, `done=True` must mean the data is REALLY on disk — verified independently of the
program's own stdout, and independently of the program's own in-process memory.

```text
   verify_persistence(root, db_path, drive_cmds, assertions, python_exe)
        │
        ▼
   ┌───────────────────────── STEP 1 — CLEAN STATE ─────────────────────────────────────┐
   │  remove any pre-existing db_path under root                                        │
   │  (every run starts from a known-empty database -- reproducible, Tenet 3)           │
   └───────────────────────────────────────┬───────────────────────────────────────────┘
                                            ▼
   ┌───────────────────────── STEP 2 — DRIVE INVOCATION #1 ────────────────────────────┐
   │  harness.system_suite._run_cli(python_exe, entry, argv, stdin, cwd=root)           │
   │    -- REUSED, not reimplemented: sandboxed (run_sandboxed), scrubbed env,          │
   │       DENY_ALL egress, timeout + process-tree kill (EXT-037/REQ-7)                 │
   │  runs drive_cmds' first invocation's write commands (e.g. `add <note>`)            │
   │  <process exits -- any in-memory-only state is now GONE>                           │
   └───────────────────────────────────────┬───────────────────────────────────────────┘
                                            ▼
   ┌───────────────────────── STEP 3 — INDEPENDENT QUERY #1 ────────────────────────────┐
   │  a FRESH stdlib sqlite3.connect(db_path) opened by THIS module                     │
   │    (never the CLI's own process, never its stdout)                                 │
   │  evaluate `assertions` against the REAL persisted rows                             │
   │  db file missing / query error -> ok=False, note, never raised                     │
   └───────────────────────────────────────┬───────────────────────────────────────────┘
                                            ▼
   ┌───────────────────────── STEP 4 — DRIVE INVOCATION #2 (FRESH PROCESS) ─────────────┐
   │  a SECOND, entirely separate `_run_cli` subprocess (e.g. `list` / `count`)          │
   │  no shared in-process state with invocation #1 -- proves persistence crossed a     │
   │  PROCESS BOUNDARY, not just "the same running program remembered it"               │
   └───────────────────────────────────────┬───────────────────────────────────────────┘
                                            ▼
   ┌───────────────────────── STEP 5 — INDEPENDENT QUERY #2 + FINAL VERDICT ───────────┐
   │  re-open db_path fresh, re-check the SAME (or extended) assertions                 │
   │  ok = True  IFF  db exists AND every assertion passed AND invocation #2 confirms   │
   │  ok = False otherwise -- always with a diagnostic `note`, NEVER an exception       │
   └─────────────────────────────────────────────────────────────────────────────────────┘
```

## Why cross-invocation persistence matters

A CLI can trivially fake "persistence" within a single run: keep everything in a module-level
`list`/`dict`, print `"Saved!"` after every `add`, and `list`/`count` will look perfectly correct —
because it is all still sitting in the SAME process's memory. The only way to distinguish "real
disk persistence" from "convincing in-process illusion" is to force a PROCESS BOUNDARY between the
write and the read: a second, freshly-started CLI invocation (or, symmetrically, this module's own
independent `sqlite3` connection) has zero access to the first invocation's memory — if the data is
still there, it can only be because it genuinely reached the `.db` file. This is the datastore
analogue of the server oracle's "actually start uvicorn and hit the endpoint over real HTTP" — never
trust the artifact's own self-report, always cross a real boundary and check independently.

## Relationship to existing modules

- **`harness.system_suite._run_cli`** (EXT-037 REQ-7) is REUSED, not reimplemented, for every CLI
  invocation this oracle drives — the same sandboxed, scrubbed-environment, `DENY_ALL`-egress,
  timeout + process-tree-kill subprocess runner every other black-box CLI check in this codebase
  already goes through. This oracle adds zero new subprocess-handling code.
- **`harness.server_oracle`** (EXT-036 REQ-22) is the direct architectural analogue in a different
  domain (HTTP instead of a datastore file): "don't trust the artifact's self-report; independently
  verify the real effect; never raise; always tear down/report honestly." This module mirrors that
  house discipline exactly (never-raise, honest `ok=False` + `note` on any failure mode).
- **`harness.system_suite.CreationTask`** — the new DATASTORE task tier is just more entries in the
  existing task list, using the existing `checks` list shape (a callable check can call
  `verify_persistence` directly with `(root, plan)`), so no change to the suite's run loop is needed.

## Explicit, NOT-yet-built follow-ups (named honestly)

- **REQ-2 — real-service datastore provisioning.** A `ServiceProvisioner` for Postgres/Redis/
  Qdrant/Cassandra: bring a real service up on localhost (or connect to one already running),
  apply connection/resource caps, tear it down cleanly in a `finally` block (mirroring
  `server_oracle._kill_tree`'s teardown discipline) — and plug into the SAME `verify_persistence`-
  shaped contract this module established for sqlite. Not built here: it needs an actual running
  service, which this repo's offline/no-network test discipline cannot exercise honestly today.
- **Wiring into `build_system`/the orchestrator.** This oracle is standalone; making a real
  sentence->system build's `done` verdict actually call it for a persistence-requiring task is a
  separate, later follow-up, not silently deferred.
