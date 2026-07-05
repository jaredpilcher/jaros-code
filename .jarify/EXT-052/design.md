# EXT-052 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #23 names Claude Code's background-runs surface: a
long task can be kicked off, the terminal stays free, and the user checks on it later (status,
logs, live attach, cancel). jaros-code already has the internal pieces — the EXT-043 headless
one-shot path (`harness.cli._run_one_shot`), a hash-chain-logged gated `Runtime`, and
observability primitives (`harness/heartbeat.py`, `harness/run_with_heartbeat.py`,
`scripts/run_forever.py`) — but they are all internal/developer-facing. There is no user command
that submits a request, returns immediately with something to hold onto, and lets the user come
back to it.

The fix must not invent a second execution mechanism or a new process model: the unit of work a
background job performs is the EXACT SAME `_run_one_shot(request, ...)` call a foreground
`jcode "<request>"` already makes (EXT-043) — running it "in the background" only changes WHERE
that call executes (a detached child process instead of the current one), never what it does or
what gates it passes through. Process spawn/kill likewise reuses the repo's existing
tree-kill discipline (`harness.secure_exec._kill_tree` / `.jaros-data/tools/shell_exec_tool.py::
_kill_tree`) rather than hand-rolling a new one.

## Mechanism

```
  SUBMIT                                             DETACHED WORKER (separate OS process)
  ┌─────────────────────────────────────┐            ┌───────────────────────────────────────┐
  │ jcode --bg "<request>"               │            │ python -m harness.bg_worker <job_id>   │
  │  (harness.cli.main, new leading      │  spawns    │                                         │
  │   subcommand check BEFORE the        │───────────▶│  rec = bg_jobs.get_job(job_id)         │
  │   existing --resume/-c/headless      │  (Popen,   │  text, code = _run_one_shot(            │
  │   flag parsing)                      │  detached,  │      rec.request, None, "text", None)  │
  │                                       │  stdout/    │      <-- THE SAME EXT-043 one-shot     │
  │  bg_jobs.submit_job(request)         │  stderr ->  │          path a foreground run uses;   │
  │    - new short job id                │  log file)  │          constructs a REAL JcodeCli +  │
  │    - persist JobRecord (running,     │            │          gated Runtime -- any host      │
  │      pid=None) BEFORE spawn           │            │          write still goes through a     │
  │    - _spawn_worker() -> pid           │            │          real code.write_file Decision  │
  │    - persist JobRecord (pid=<pid>)   │            │  bg_jobs.mark_finished(job_id, code)    │
  │    - print "job <id> submitted"      │            │      -> status = done | failed          │
  └─────────────────────────────────────┘            └───────────────────────────────────────┘
                    │                                                    │
                    ▼                                                    ▼
       ┌───────────────────────────────────────────────────────────────────────┐
       │ .jaros-data/bg_jobs/<id>.json   (durable JobRecord — plain Python I/O, │
       │ .jaros-data/bg_jobs/<id>.log    internal runtime state, NOT a         │
       │                                 host-project write; mirrors the      │
       │                                 session-store precedent)            │
       └───────────────────────────────────────────────────────────────────────┘
                    ▲                          ▲                    ▲
                    │                          │                    │
     ┌──────────────┴──────┐   ┌───────────────┴─────┐   ┌──────────┴───────────┐
     │ jcode jobs / bg list │   │ jcode logs <id>      │   │ jcode attach <id>     │
     │ /jobs (REPL)         │   │ /logs <id> (REPL)    │   │ streams new log bytes │
     │ -> bg_jobs.list_jobs │   │ -> bg_jobs.read_log  │   │ until status != running│
     │    (reconciles: dead │   │                      │   │ or Ctrl-C (detach only,│
     │    pid + no finish   │   │ jcode stop <id>      │   │ never stops the job)  │
     │    marker -> failed) │   │ /stop <id> (REPL)    │   └───────────────────────┘
     └──────────────────────┘   │ -> bg_jobs.stop_job  │
                                 │   kills pid TREE only │
                                 │   (mirrors secure_exec │
                                 │   ._kill_tree, adapted │
                                 │   to a bare recorded   │
                                 │   pid -- never by name)│
                                 └───────────────────────┘
```

- **No second execution mechanism.** `harness/bg_worker.py`'s entire job is one call to the
  UNCHANGED `harness.cli._run_one_shot` — the exact function a foreground one-shot request already
  calls. Backgrounding is purely a question of WHERE that call runs (a detached `subprocess.Popen`
  child) and HOW its result is observed afterward (a durable `JobRecord` + log file), not a new
  reasoning or routing path.
- **No new process model.** Spawn uses plain `subprocess.Popen` — the same primitive
  `harness/secure_exec.py`, `harness/run_with_heartbeat.py`, and `.jaros-data/tools/
  shell_exec_tool.py` already use throughout this repo — with `start_new_session=True` (POSIX) /
  `CREATE_NEW_PROCESS_GROUP` (Windows) so the child becomes its own process-group/tree root,
  exactly the precondition `_kill_tree`-style teardown already relies on elsewhere. Termination
  mirrors `harness.secure_exec._kill_tree` / `.jaros-data/tools/shell_exec_tool.py::_kill_tree`
  line-for-line (Windows: `taskkill /F /T /PID`; POSIX: `os.killpg(os.getpgid(pid), SIGKILL)`),
  adapted to take a bare recorded `pid` (a job record crosses process boundaries — by the time
  `stop_job` runs there is no live `Popen` handle to call `.pid` on) instead of a `Popen` object.
  **Never kill-by-name** — only the one recorded pid (and its process-group descendants) is ever
  targeted.
- **Durable record, not a live handle.** Because `jcode jobs`/`logs`/`stop` are typically invoked
  from a BRAND NEW process (not the one that spawned the worker), there is no in-memory `Popen`
  object to poll. `JobRecord` is persisted as JSON (`.jaros-data/bg_jobs/<id>.json`) at submit time
  (before spawn, so a crash-during-spawn is still observable) and updated by the WORKER ITSELF on
  completion (`bg_jobs.mark_finished`) — a self-reporting pattern, not a parent `wait()`. A stale
  "running" record whose pid is no longer alive (the worker crashed before it could call
  `mark_finished`) is honestly reconciled to `"failed"` the next time it is read
  (`list_jobs`/`get_job`), never left as a permanent false "running" ghost.
- **Reuses existing observability, not a new one.** `harness/bg_worker.py` wraps its
  `_run_one_shot` call in `harness.heartbeat.heartbeat(...)` (EXT-040's existing mechanism) so a
  running background job shows up in `/status`'s activity trail exactly like any other long
  operation — no parallel observability channel invented.
- **Full environment, not a sandboxed one.** `harness/secure_exec.py`'s scrubbed-environment
  sandbox exists for a DIFFERENT threat model (running MODEL-GENERATED code untrusted). A
  background job is OUR OWN trusted `jcode` invocation — scrubbing its environment (dropping
  `LLAMACPP_HOST` etc.) would silently make a backgrounded run behave differently from the exact
  same request run in the foreground, which is itself a correctness bug, not a safety win. The
  isolation this spec provides is pid/tree-scoped lifecycle management (spawn, detect, kill) and
  the pre-existing Decision-gate on any host write the job performs — not process sandboxing.

## Reserved bare-subcommand words (deliberate, honestly scoped)

`jcode jobs`, `jcode logs <id>`, `jcode attach <id>`, `jcode stop <id>` (and `--bg`) are matched
BEFORE the existing headless/session flag parsing in `main()`, exactly like `-c`/`--resume` already
take priority over being read as plain request text. This means a one-word/two-word plain request
that happens to collide EXACTLY with one of these reserved shapes (e.g. a lone unquoted `jcode
jobs`, or `jcode logs <8-hex-char-token>`) is now read as the subcommand, not a plain request —
mirroring how Claude Code itself reserves bare subcommand words (`claude mcp`, `claude config`,
...). This is a deliberate, narrow, honestly-documented trade-off (job ids are 8-char lowercase hex
tokens, chosen specifically to make an accidental collision with natural-language request text
vanishingly unlikely), not a silent behavior change to the general multi-word one-shot path.

## Two-plane / honesty

`harness/bg_jobs.py` and `harness/bg_worker.py`'s bookkeeping (job-record read/write, log
read, pid liveness check, tree-kill) are pure execution-plane code (Tenet 1) — no model call
anywhere in either module. The JOB's OWN reasoning/execution — whatever `_run_one_shot` does with
the submitted request — is completely unchanged from the foreground path: the same orchestrator
routing, the same gated `Runtime.apply` choke point, the same hash-chain Decision log for any
host-project write. Per Tenet 3, `harness/product_parity.py` row #23 is flipped to `"works"` only
for the subset of `--bg`/`jobs`/`logs`/`attach`/`stop` that is genuinely delivered and
test-covered; anything not landed in this pass is named honestly as the residual gap rather than
folded into an inflated claim.

## Backward compatibility (no regression)

- A `jcode "<request>"` invocation whose first token is NOT `--bg`/`jobs`/`logs`/`attach`/`stop`
  is completely unaffected — `main()`'s new subcommand check returns `None` immediately and falls
  through to the existing `_parse_headless_args` path byte-identically.
- `JcodeCli.__init__`/`dispatch()`'s existing behavior for every current built-in command and
  custom skill is unchanged; `/jobs`, `/logs`, `/stop` are new additive `cmd_*` methods that only
  ever get reached via their own exact slash-command name, exactly like every other built-in.
- No existing test, agent, or tool changes behavior; `.jaros-data/bg_jobs/` is a brand-new,
  gitignored runtime directory (mirrors `.jaros-data/sessions/`, `.jaros-data/artifacts/
  heartbeat/`) — a repo that has never run a background job has an empty/absent directory and
  every function degrades to an honest empty result, never raising.

## Out of scope (this pass)

A `jcode bg` fully-namespaced subcommand family beyond the `bg list` alias explicitly named in the
requirements; job resource limits/quotas; multiple concurrent attach sessions to the same job;
persisting jobs across a host reboot in a way that re-validates orphaned pids against a PID-reuse
race (a vanishingly rare, honestly-unaddressed edge case — a reused pid from an unrelated process
could theoretically be reported alive; not defended against in this pass); a REPL `/attach`
command (not requested — attach is a CLI-only surface in this pass). These remain named as the
residual gap in `docs/GAP-MAP.md` row #23's "Next lever" rather than silently left unstated.
