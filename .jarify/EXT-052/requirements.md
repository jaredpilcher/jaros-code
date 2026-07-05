---
id: EXT-052
title: Background runs surface
status: uncovered
priority: medium
---

# EXT-052 — Background runs surface

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #23 — expose the internal
runner/one-shot infra as a user-facing background-jobs surface: `jcode --bg "<request>"` submits
and returns a short job id immediately; `jcode jobs`/`logs <id>`/`attach <id>`/`stop <id>` (plus
`/jobs`, `/logs <id>`, `/stop <id>` in the REPL) manage it. The job itself is the EXISTING EXT-043
`_run_one_shot` path run detached — no new reasoning mechanism, no new process model.

### [REQ-1] Job record store — durable, deterministic bookkeeping

A new `harness/bg_jobs.py` module persists a durable job record (id, request, status, pid,
started/ended timestamps, log path, exit code) under `.jaros-data/bg_jobs/` — internal runtime
state (mirrors the session-store precedent), not a host-project write. All bookkeeping (create,
read, list, reconcile) is deterministic execution-plane code: no model call anywhere.

#### Acceptance Criteria
- [ ] `harness.bg_jobs.submit_job(request: str) -> JobRecord` generates a short job id, persists a
      `JobRecord` with `status="running"` BEFORE spawning the worker process (so a crash-during-
      spawn is still observable), spawns the worker detached, records its pid, and returns the
      record.
- [ ] `harness.bg_jobs.get_job(job_id) -> JobRecord | None` returns `None` for an unknown id
      (never raises); for a known id it returns the record, RECONCILED (see REQ-4).
- [ ] `harness.bg_jobs.list_jobs() -> list[JobRecord]` returns every persisted job, each
      reconciled, sorted newest-first; an empty/absent `.jaros-data/bg_jobs/` yields `[]`, never
      raises.
- [ ] A malformed/corrupt job record file is skipped by `list_jobs()`, never crashes discovery of
      the others (mirrors the EXT-046 malformed-skill-file discipline).
- [ ] The jobs directory is overridable via an env var (`JCODE_BG_JOBS_DIR`), mirroring
      `harness.heartbeat`'s `JCODE_HEARTBEAT_DIR` precedent, so tests are fully hermetic (no real
      `.jaros-data/` writes required).

### [REQ-2] Submission runs the EXISTING one-shot pipeline, detached — not a new mechanism

The backgrounded unit of work is `harness.cli._run_one_shot` (EXT-043), invoked by a new
`harness/bg_worker.py` entrypoint run as a separate OS process. No second reasoning/routing
mechanism is introduced; any host-project write the job performs still passes through the real
gated `code.write_file` Decision exactly as a foreground run would.

#### Acceptance Criteria
- [ ] `python -m harness.bg_worker <job_id>` loads the job's record, calls
      `harness.cli._run_one_shot(record.request, None, "text", None)` UNCHANGED, writes the
      response to the job's log, and calls `harness.bg_jobs.mark_finished(job_id, exit_code=code)`
      — status becomes `"done"` (exit code 0) or `"failed"` (nonzero) with an `ended_at` timestamp.
- [ ] The worker's own crash (an exception before `_run_one_shot` returns) is caught and recorded
      as `mark_finished(job_id, exit_code=1)` — never leaves the record stuck at `"running"`.
- [ ] Process spawn uses plain `subprocess.Popen` (the same primitive already used throughout this
      repo — `harness/secure_exec.py`, `harness/run_with_heartbeat.py`,
      `.jaros-data/tools/shell_exec_tool.py`) with the FULL inherited environment (not the
      `secure_exec` scrubbed sandbox — a different threat model; see design.md) and
      `start_new_session=True`/`CREATE_NEW_PROCESS_GROUP` so the child is its own process-group/
      tree root.
- [ ] The worker wraps its `_run_one_shot` call in `harness.heartbeat.heartbeat(...)` so a running
      background job is visible in `/status`'s activity trail — reusing EXT-040's existing
      mechanism, not a new observability channel.

### [REQ-3] `jcode --bg` / `jcode jobs` / `jcode logs <id>` — submit, list, read output

`jcode --bg "<request>"` submits and prints the new job id immediately (never blocks on the job's
completion). `jcode jobs` (alias `jcode bg list`) lists every job. `jcode logs <id>` prints that
job's recorded output.

#### Acceptance Criteria
- [ ] `harness.cli.main()` recognizes `--bg <request...>` as a leading token BEFORE the existing
      `_parse_headless_args`/session-flag parsing, submits via `bg_jobs.submit_job`, prints the job
      id + pid + a one-line usage hint (`logs`/`attach`/`stop`), and returns exit code 0 — it never
      constructs a foreground `JcodeCli` or blocks on the submitted work.
- [ ] `jcode jobs` (bare) and `jcode bg list` both render every job (id, truncated request,
      status, started/ended) via `harness.bg_jobs.format_jobs`; an empty job set renders an honest
      "(no background jobs ...)" message, never a blank string or a crash.
- [ ] `jcode logs <id>` prints that job's log content via `harness.bg_jobs.read_log`; an unknown id
      renders an honest error message and a non-crashing (non-zero, but never a traceback) result.
- [ ] `/jobs` and `/logs <id>` are added as `JcodeCli.cmd_jobs`/`cmd_logs` REPL commands delegating
      to the same `bg_jobs` functions; `/help` documents `--bg`/`jobs`/`logs`/`attach`/`stop` and
      `/jobs`/`/logs`.

### [REQ-4] `jcode attach <id>` — stream until the job ends or the user detaches

`jcode attach <id>` streams a running job's new output as it is produced. Ctrl-C detaches (returns
control to the terminal) WITHOUT stopping the job — the job keeps running in the background.

#### Acceptance Criteria
- [ ] `harness.bg_jobs.attach_job(job_id, ...)` polls the job's log file for newly-appended bytes
      and prints them, re-checking the job's (reconciled) status each poll; it returns cleanly the
      moment the job's status is no longer `"running"` (prints a final "job finished: <status>"
      line).
- [ ] A `KeyboardInterrupt` during the poll loop is caught, prints a "(detached — job keeps
      running)" message, and returns WITHOUT calling `stop_job` — the job's own process/record is
      completely untouched by a detach.
- [ ] An unknown job id degrades to an honest error message, never a crash or an infinite loop.
- [ ] `attach_job` accepts injectable `sleep_fn`/`print_fn` (defaulted to `time.sleep`/`print`) so
      tests can drive it deterministically without a real sleep or a real subprocess.

### [REQ-5] `jcode stop <id>` — cancel by recorded pid/tree only, never by name

`jcode stop <id>` (and REPL `/stop <id>`) terminates a running job's process TREE and marks it
`"stopped"`. Only the job's own recorded pid (and its process-group descendants) is ever targeted
— never a blanket kill by process name or command line.

#### Acceptance Criteria
- [ ] `harness.bg_jobs.stop_job(job_id) -> dict` returns `{"ok": False, ...}` with an honest
      message for an unknown id or a job that is not currently `"running"` (already done/failed/
      stopped) — it never sends a kill signal in that case.
- [ ] For a genuinely `"running"` job, `stop_job` kills the process tree rooted at the job's
      RECORDED pid — mirroring `harness.secure_exec._kill_tree` /
      `.jaros-data/tools/shell_exec_tool.py::_kill_tree` (Windows: `taskkill /F /T /PID`; POSIX:
      `os.killpg(os.getpgid(pid), SIGKILL)`) — then persists `status="stopped"` with an
      `ended_at` timestamp.
- [ ] The tree-kill call is a separately-named, monkeypatchable function so tests can prove
      `stop_job` invokes it with the correct pid WITHOUT spawning or killing any real process.
- [ ] `/stop <id>` (REPL) and `jcode stop <id>` (CLI) both delegate to `stop_job` and render its
      `message` honestly (success or the honest not-running/unknown-id refusal).

### [REQ-6] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=23` (Background runs surface) reflects EXACTLY what this spec
delivers — flipped to `"works"` only if `--bg`/`jobs`/`logs`/`attach`/`stop` are ALL genuinely
delivered and test-covered; if any piece does not land, the row stays `"partial"` and
`current_state`/`next_lever` name precisely what is delivered vs. deferred. `docs/GAP-MAP.md` row
#23 and `tests/test_ext041_product_parity.py`'s honesty pin are updated to match.

#### Acceptance Criteria
- [ ] `harness/product_parity.py` row `id=23`'s `state`, `current_state`, and `next_lever` honestly
      reflect what actually landed in this pass (never inflated).
- [ ] `docs/GAP-MAP.md` row #23's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [ ] If row #23 is flipped to `"works"`, `tests/test_ext041_product_parity.py`'s `works == [...]`
      pin and the `n_total`/`n_works`/`n_partial`+`n_missing` aggregate assertions are updated to
      include it (kept sorted); if it stays `"partial"`, no such pin change is made (honesty over
      inflation).
