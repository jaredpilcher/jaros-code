# Implementation Tasks

### [TASK-1] Background job store + detached worker, wired into the CLI

Add `harness/bg_jobs.py` (durable job-record store: submit/list/get/stop/read-log/attach, pid
tree-kill mirroring `harness.secure_exec._kill_tree`) and `harness/bg_worker.py` (the detached
worker entrypoint that runs the EXISTING EXT-043 `_run_one_shot` as its unit of work); wire
`jcode --bg`/`jobs`/`logs <id>`/`attach <id>`/`stop <id>` into `harness/cli.py`'s `main()`, plus
`/jobs`/`/logs <id>`/`/stop <id>` REPL commands; update the Product-Parity Checklist honestly.

#### Steps
1. Create `harness/bg_jobs.py`: `@dataclass(frozen=True) JobRecord(id, request, status, pid,
   started_at, ended_at, log_path, exit_code)`. `_jobs_dir() -> Path` resolves
   `.jaros-data/bg_jobs` (overridable via `JCODE_BG_JOBS_DIR` env, mirroring
   `harness.heartbeat`'s `JCODE_HEARTBEAT_DIR`), `mkdir(parents=True, exist_ok=True)` guarded in
   `try/except`. `_job_path(job_id)`/`_log_path_for(job_id)` return the record/log file paths.
   `_new_job_id() -> str` generates an 8-char lowercase-hex id (`secrets.token_hex(4)`), retrying
   on the vanishingly rare collision against an existing record file. `_read_record(job_id)`/
   `_write_record(rec)` do the JSON load/dump, `_read_record` returning `None` on any missing/
   malformed file (never raising). `_pid_alive(pid)` (POSIX: `os.kill(pid, 0)`; Windows:
   `tasklist /FI "PID eq <pid>"` substring check — mirrors `tests/test_ext005_proc_treekill.py`'s
   `_pid_alive` helper) and `_kill_pid_tree(pid)` (mirrors `harness.secure_exec._kill_tree` /
   `.jaros-data/tools/shell_exec_tool.py::_kill_tree` exactly, adapted to a bare pid: Windows
   `taskkill /F /T /PID <pid>`, POSIX `os.killpg(os.getpgid(pid), signal.SIGKILL)`, falling back to
   `os.kill(pid, SIGKILL)` on any error) are private helpers.
2. In `harness/bg_jobs.py`: `submit_job(request: str) -> JobRecord` — generates a job id, builds
   `log_path`, persists a `JobRecord(status="running", pid=None, started_at=time.time(), ...)`
   BEFORE spawning (so a crash-during-spawn is observable), calls a separately-named
   `_spawn_worker(job_id, log_path) -> int` (monkeypatchable by tests) that
   `subprocess.Popen([sys.executable, "-m", "harness.bg_worker", job_id], cwd=str(ROOT),
   stdout=<opened log file, append>, stderr=subprocess.STDOUT, env=os.environ.copy(),
   start_new_session=True on POSIX / creationflags=subprocess.CREATE_NEW_PROCESS_GROUP on
   win32)`, then persists the record again with the resulting pid; any spawn exception is caught
   and the record is persisted as `status="failed"` instead of raising out of `submit_job`.
   `mark_finished(job_id, *, exit_code: int) -> None` (called by the worker) sets
   `status = "done" if exit_code == 0 else "failed"`, `ended_at=time.time()`, `exit_code=exit_code`
   and persists — a no-op (never raises) if the record is missing.
3. In `harness/bg_jobs.py`: `_reconcile(rec) -> JobRecord` — when `rec.status == "running"` and
   `rec.pid` is no longer `_pid_alive`, persists and returns the record with `status="failed"`
   (the worker crashed before calling `mark_finished`); otherwise returns `rec` unchanged.
   `get_job(job_id) -> JobRecord | None` reads + reconciles (returns `None` for an unknown id,
   never raising). `list_jobs() -> list[JobRecord]` globs `<jobs_dir>/*.json`, skips any file that
   fails to parse, reconciles each, and returns them sorted by `started_at` descending; an absent/
   empty jobs dir yields `[]`.
4. In `harness/bg_jobs.py`: `stop_job(job_id) -> dict` — `{"ok": False, "message": ..., "job":
   None}` for an unknown id; `{"ok": False, "message": ..., "job": rec}` (no kill signal sent) for
   a job whose (reconciled) status is not `"running"`; otherwise calls `_kill_pid_tree(rec.pid)`
   (only ever this one recorded pid — never a name-based kill), persists `status="stopped"`,
   `ended_at=time.time()`, and returns `{"ok": True, "message": ..., "job": <updated rec>}`.
   `read_log(job_id) -> str` returns an honest "no such job"-style message for an unknown id,
   else the log file's content (or an honest empty-log note if the job just started and has no
   output yet), never raising on a read failure. `format_jobs(jobs=None) -> str` renders a table
   (id, truncated request, status, started/ended) via `list_jobs()` when `jobs is None`, with an
   honest "(no background jobs ...)" message for an empty list.
5. In `harness/bg_jobs.py`: `attach_job(job_id, *, poll_interval: float = 0.5, sleep_fn=None,
   print_fn=print) -> int` — resolves `sleep_fn` to `time.sleep` by default (injectable for tests);
   returns `1` with an honest error via `print_fn` for an unknown id; otherwise loops: read any
   newly-appended log bytes (track a byte offset) and `print_fn` them, re-fetch `get_job(job_id)`
   to pick up the reconciled status, and stop looping the instant status is not `"running"`
   (prints a final "job finished: `<status>`" line via `print_fn`, returns `0`) — for an ALREADY
   non-running job this exits after exactly one log read, no sleep. A `KeyboardInterrupt` raised
   from `sleep_fn` is caught, prints a "(detached — job keeps running)" message via `print_fn`, and
   returns `0` WITHOUT calling `stop_job` or touching the job's record.
6. Create `harness/bg_worker.py`: `main(argv) -> int` — reads `argv[0]` as the job id (usage error
   on a missing arg), calls `harness.bg_jobs.get_job(job_id)` (an unknown id is a reported, non-
   crashing failure), then wraps ONE call to `harness.cli._run_one_shot(rec.request, None, "text",
   None)` inside `harness.heartbeat.heartbeat("bg_job", run_id=job_id, detail=rec.request[:80])`
   (EXT-040 reuse — visible in `/status`'s activity trail), prints the returned text to stdout
   (captured into the job's log by the parent `Popen`'s stdout redirect), and calls
   `harness.bg_jobs.mark_finished(job_id, exit_code=code)`. Any exception raised before
   `_run_one_shot` returns is caught, printed to stderr, and reported via
   `mark_finished(job_id, exit_code=1)` rather than letting the worker process crash unreported.
   `if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))`.
7. In `harness/cli.py`: add a private `_dispatch_bg_subcommand(args: list[str]) -> int | None` that
   returns `None` (no match — caller falls through to today's exact existing parsing) unless
   `args` matches one of: `args[0] == "--bg"` (submit `" ".join(args[1:])` via
   `bg_jobs.submit_job`, print the job id/pid + `logs`/`attach`/`stop` usage hints, return `0`; an
   empty joined request after `--bg` is a reported, non-zero-exit refusal — `submit_job` is never
   called with an empty string); `args == ["jobs"]` or `args[:2] == ["bg", "list"]` or
   `args[:2] == ["bg", "jobs"]` (print `bg_jobs.format_jobs()`, return `0`); `args[0] == "logs" and
   len(args) == 2` (print `bg_jobs.read_log(args[1])`, return `0`); `args[0] == "attach" and
   len(args) == 2` (return `bg_jobs.attach_job(args[1])`); `args[0] == "stop" and len(args) == 2`
   (call `bg_jobs.stop_job(args[1])`, print its `message`, return `0` if `ok` else `1`). Call
   `_dispatch_bg_subcommand(sys.argv[1:])` at the very top of `main()`, BEFORE
   `_parse_headless_args` — returning its result immediately when non-`None`, otherwise proceeding
   exactly as today (byte-identical fallthrough). Update `main()`'s docstring with the new
   `--bg`/`jobs`/`logs`/`attach`/`stop` usage lines.
8. In `harness/cli.py`: add `JcodeCli.cmd_jobs(self, _arg: str) -> str` (returns
   `bg_jobs.format_jobs()`), `cmd_logs(self, arg: str) -> str` (returns
   `bg_jobs.read_log(arg.strip())`, an honest "usage: /logs <id>" message when `arg` is blank),
   and `cmd_stop(self, arg: str) -> str` (an honest usage message when `arg` is blank; otherwise
   `bg_jobs.stop_job(arg.strip())["message"]`). Update the module docstring's command list to
   document `/jobs`, `/logs <id>`, `/stop <id>`, and the command-line `--bg`/`jobs`/`logs
   <id>`/`attach <id>`/`stop <id>` surface (mirroring how EXT-044's `-c`/`-r`/`--fork` are
   documented alongside their REPL equivalents).
9. Update `harness/product_parity.py` row `id=23` (Background runs surface): set `state` to
   `"works"` ONLY IF all of `--bg`/`jobs`/`logs`/`attach`/`stop` (CLI) landed with passing tests in
   this task — `current_state` names exactly the two-tier (durable `JobRecord` store + detached
   `bg_worker` reusing the unchanged EXT-043 `_run_one_shot`) mechanism delivered, and
   `next_lever` names only the genuinely residual gap (e.g. a REPL `/attach`, job resource limits/
   quotas, a fully-namespaced `jcode bg <verb>` family beyond the `bg list` alias). If any listed
   surface does NOT land working+tested, `state` stays `"partial"` instead, and `current_state`/
   `next_lever` say exactly what shipped vs. what remains — never inflated. Mirror the same
   honest wording into `docs/GAP-MAP.md` row #23's `State`/`Current honest state`/`Next lever`
   columns.
10. If (and only if) row #23 is flipped to `"works"` in Step 9, update
    `tests/test_ext041_product_parity.py`: add `23` to the `works == [...]` pin (kept sorted) and
    update `test_score_default_rows_reflects_honest_current_baseline`'s `n_total`/`n_works` (and
    the derived `n_partial + n_missing`) assertions to match the new works-count. If row #23 stays
    `"partial"`, this file is left untouched.
11. Write `tests/test_ext052_background.py` (deterministic, hermetic — `monkeypatch.setenv`
    `JCODE_BG_JOBS_DIR` to a `tmp_path` subdirectory for every test; NEVER spawn a real
    long-lived process): `submit_job` (with `bg_jobs._spawn_worker` monkeypatched to a fake
    returning a synthetic pid, never a real `Popen`) creates a persisted record and returns a
    `JobRecord` with `status="running"`; `list_jobs()` includes it; writing to the job's log path
    directly plus calling `mark_finished(job_id, exit_code=0)` (simulating what the real worker
    would do) makes `get_job`/`list_jobs` report `status="done"` and `read_log` return the written
    content; `mark_finished(job_id, exit_code=1)` reports `"failed"`; `stop_job` on a `"running"`
    job (with `bg_jobs._kill_pid_tree` monkeypatched to a call-recording stub) marks it `"stopped"`
    and invokes the stub with exactly the job's recorded pid, never touching a real process;
    `stop_job` on an already-`"done"`/unknown id returns `{"ok": False, ...}` and never calls the
    kill stub; `get_job`/`read_log`/`stop_job` on a nonexistent id all degrade to an honest
    result, never raising; `list_jobs()`/`format_jobs()` on an empty jobs dir report a clean empty
    state; `attach_job` on an already-completed job (log pre-written, status already `"done"`)
    returns after exactly one read with no `sleep_fn` call; a `_reconcile` case — a `"running"`
    record whose pid is a value `_pid_alive` is monkeypatched to report dead — is honestly
    downgraded to `"failed"` by `get_job`/`list_jobs`. Also cover the `harness.cli` wiring:
    `_dispatch_bg_subcommand` recognizes `--bg`/`jobs`/`bg list`/`logs <id>`/`attach <id>`/
    `stop <id>` and returns `None` (unhandled) for an ordinary multi-word plain request, with
    `harness.bg_jobs`'s functions monkeypatched so no real subprocess is ever spawned by these CLI-
    level tests; `JcodeCli.cmd_jobs`/`cmd_logs`/`cmd_stop` delegate correctly (constructed via
    `JcodeCli.__new__` to avoid a real model/Runtime, mirroring `test_ext041_product_parity.py`'s
    `test_cli_parity_command_renders`).

#### Implements
- [REQ-1] Job record store — durable, deterministic bookkeeping
- [REQ-2] Submission runs the EXISTING one-shot pipeline, detached — not a new mechanism
- [REQ-3] `jcode --bg` / `jcode jobs` / `jcode logs <id>` — submit, list, read output
- [REQ-4] `jcode attach <id>` — stream until the job ends or the user detaches
- [REQ-5] `jcode stop <id>` — cancel by recorded pid/tree only, never by name
- [REQ-6] Honest Product-Parity Checklist update
