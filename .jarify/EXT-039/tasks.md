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

### [TASK-2] Real-service (Redis) provisioner + independent persistence oracle (REQ-2)

Build the first REAL-service rung of REQ-2: a `ServiceProvisioner` that brings a real Redis service up
on localhost via Docker, caps + tears it down cleanly, and an independent Redis persistence oracle that
plugs into the SAME `verify_persistence`-shaped contract `harness/datastore_oracle.py` (REQ-1) established
for sqlite — proving a datastore CLI's data REALLY reached the service, never trusting its stdout. Redis
is the chosen first target (simplest real service; its RESP wire protocol is speakable over a raw stdlib
socket, so the whole module stays PURE STDLIB — no `redis-py` dependency — matching `datastore_oracle`'s
no-new-dependency discipline). Postgres/Qdrant/Cassandra remain named-but-later under REQ-2. Honest offline
discipline (Tenet 3): every test skips when Docker is absent, so offline CI NEVER fails or falsely passes.

#### Steps
1. Create `harness/service_provisioner.py` (execution-plane only — NO model call anywhere) with:
   `ServiceHandle` dataclass (`kind: str`, `host: str`, `port: int`, `container_id: str | None`,
   `ok: bool`, `note: str`) and `ServiceResult` dataclass mirroring `datastore_oracle.DatastoreResult`
   (`ok: bool`, `rows_checked: int`, `failures: list`, `note: str`).
2. Implement `docker_available() -> bool`: best-effort, NEVER-RAISE check that the `docker` CLI exists
   AND its daemon answers (`docker info`/`docker ps` exits 0, short timeout); returns `False` on any
   error. This is the single gate every test and every provision call consults.
3. Implement `provision_redis(*, image="redis:7-alpine", host_port=0, mem_cap="128m", ready_timeout_s=20.0)
   -> ServiceHandle`: if `docker_available()` is False return `ServiceHandle(ok=False, note="docker unavailable")`
   immediately (never raise); else `docker run -d --rm --memory=<mem_cap> -p <host_port>:6379 <image>`
   (host_port=0 → let Docker pick a free port, then read it back via `docker port <id> 6379`), poll a raw
   socket RESP `PING`→`+PONG` until ready or `ready_timeout_s` elapses, and return a populated
   `ServiceHandle(ok=True, host="127.0.0.1", port=<mapped>, container_id=<id>)`. On any failure (image
   pull fail, no ready PONG in time) tear down the partial container and return `ok=False` + a diagnostic
   note — NEVER raise, NEVER leak a container.
4. Implement `teardown(handle: ServiceHandle) -> None`: `docker stop <container_id>` (best-effort, short
   timeout, `--rm` auto-removes) — never raise, safe to call on a `None`/failed handle (mirrors
   `server_oracle._kill_tree`'s teardown discipline). Every provision site MUST call this in a `finally`.
5. Implement a tiny stdlib RESP-over-socket client (module-private helpers `_resp_command(host, port,
   *args, timeout_s=...) -> Any` encoding a RESP array request + parsing the reply: `+OK`/`-ERR`/`:int`/
   `$bulk`/`*array`), used for both readiness `PING` and the independent verification below. No third-party
   client; NEVER raise (socket/parse errors → an honest sentinel the caller treats as failure).
6. Implement `verify_redis_persistence(root, *, handle, drive_cmds, assertions, python_exe,
   entry_name="main.py") -> ServiceResult`, mirroring `datastore_oracle.verify_persistence`'s stages
   exactly but against the provisioned Redis instead of a `.db` file: (a) clean state — independently
   `FLUSHDB` via the RESP client; (b) resolve `root/<entry_name>`; (c) drive the FIRST invocation's
   `drive_cmds` via `harness.system_suite._run_cli`, exposing the service to the CLI-under-test through
   `REDIS_HOST`/`REDIS_PORT` env vars added to that invocation's environment (documented contract); (d)
   INDEPENDENTLY evaluate each `assertions` entry against real Redis state via the module's OWN RESP client
   (a `callable(resp_call)->bool`, or a `(resp_argv_tuple, expected)` pair), never the CLI's stdout;
   (e) cross-invocation check — a SECOND fresh `_run_cli` read command, then re-evaluate the same
   assertions against Redis again; return `ServiceResult(ok=True, ...)` ONLY when the handle is ok, both
   CLI invocations exited cleanly, and every assertion passed on both checks — any other outcome is
   `ok=False` + a stage-identifying note. Wrap the whole body in `try/except` so it NEVER raises.
7. Add `tests/test_ext039_service_provisioner.py` — EVERY test decorated
   `@pytest.mark.skipif(not service_provisioner.docker_available(), reason="docker unavailable")` so the
   file is a full no-op offline (never fails, never false-passes). With Docker present, cover: (a)
   `provision_redis`→ready `PING`/`+PONG`→`teardown` leaves no running container (assert via `docker ps`);
   (b) LOAD-BEARING GOOD: `verify_redis_persistence` returns `ok=True` for a small hand-written Redis-backed
   CLI fixture (uses raw-socket RESP, reads `REDIS_HOST`/`REDIS_PORT`) whose data really persists to Redis
   across two invocations; (c) LOAD-BEARING CATCH: `ok=False` for a FAKE CLI fixture that prints `"Saved!"`
   on `add` but never writes to Redis; (d) cross-invocation catch for an in-process-only fake; (e) never-raise
   on a missing entrypoint / broken CLI / malformed `assertions`/`drive_cmds` — honest `ok=False`; (f) a
   `finally`-teardown even when verification fails leaves no leaked container. Use `host_port=0` so parallel
   runs never collide.
8. Add a `DATASTORE`/`service` creation-task entry is OUT OF SCOPE here (needs a live service in the suite
   run loop) — document that as a named follow-up in the module docstring, consistent with REQ-1's seam note.
9. Run `python -m pytest tests/test_ext039_service_provisioner.py -q` (foreground) — with Docker present it
   exercises a real Redis; then the full `python -m pytest tests/ -q` (foreground) to confirm no regression
   (2410 baseline). Report both the with-Docker and the skip counts honestly.

#### Implements
- [REQ-2] Real-service datastore provisioning (Postgres/Redis/Qdrant/Cassandra)
