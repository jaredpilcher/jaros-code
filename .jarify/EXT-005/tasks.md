# Implementation Tasks — EXT-005 Convergence Evaluation Harness

### [TASK-1] Shared process-tree-kill helper for the remaining local pytest-timeout sites

Close the REQ-12 coverage gap: the proven tree-kill fix (`harness/pass1_eval.py::_run_with_treekill`)
covers the eval-harness sites, but four local `shell=True` + timeout pytest sites in the
behavioral-solve / CLI paths still use a bare `subprocess.run(..., timeout=...)` and orphan the pytest
grandchild on a Windows timeout. Extract the proven logic into a SHARED helper (single source of truth,
Tenet 3) and rewire those four sites. Fully offline + test-gated; no Jetson / Docker.

#### Steps
1. Add `harness/proc_treekill.py` exposing `run_with_treekill(cmd: str, cwd: str, timeout: int) -> bool`
   — lift the EXACT proven implementation from `harness/pass1_eval.py::_run_with_treekill` (Popen +
   `communicate(timeout)`; on `TimeoutExpired`: Windows `taskkill /F /T /PID`, POSIX
   `os.killpg(os.getpgid(pid), SIGKILL)` with `start_new_session=True`; then a short reap
   `communicate(timeout=5)`; return `returncode == 0`). Preserve the same stdout/stderr handling the
   call sites currently rely on (they capture output — accept an optional `capture: bool=False` param, or
   provide a variant that returns `(ok, output)`, matching what each site needs; inspect each site).
2. Rewire the four bare-`subprocess.run` pytest sites to use the shared helper so a Windows timeout kills
   the whole tree: `harness/agent_loop.py` (~L118), `harness/cli.py` (~L451, and the `_run` at ~L507 if
   it wraps the same call), `harness/intent_loop.py` (~L107), `harness/build_eval.py` (~L160). Keep each
   site's existing return/΅semantics (ok bool / captured text) unchanged apart from the timeout-safety.
   Tag the shared helper `# #EXT-005-REQ-12` for traceability.
3. Do NOT change the already-correct `pass1_eval.py` (`run_pass1`/`run_gated`/`_run_with_treekill`) or
   `multi_file.py` behavior — they work and are covered; leave their proven code intact (optionally they
   may delegate to the shared helper ONLY if byte-for-byte behavior-preserving, but priority is the four
   unfixed sites + zero regression to the working eval paths).
4. Add `tests/test_ext005_proc_treekill.py` (offline, cross-platform-aware): spawn via the shared helper
   a shell command that starts a long-lived child (e.g. `python -c "import time; time.sleep(60)"`) with a
   short timeout; assert the call returns `False` within a few seconds AND that the spawned child process
   is dead afterward (poll by PID). Guard any Windows-only / POSIX-only assertions with `os.name`.
   Run the full suite green (baseline 1055 passing).

#### Implements
- [REQ-12] Robust test-exec — hang-proof process tree kill (shared helper + remaining sites)

### [TASK-2] Weighted daily-driver runner (loader + category oracle router + weighted scoring)

Implement the daily-driver parity-suite runner (REQ-13), extending `harness/eval_runner` WITHOUT
regressing the authored path. Fully offline + test-gated: the only model-calling piece (asking the
CLI a navigate question) is INJECTABLE (`answer_fn`) so the core is testable with no Jetson. The
schema + category weights are defined in `evals/daily_driver/README.md` (already committed) and two
seed tasks exist under `evals/daily_driver/dev/`.

#### Steps
1. New `harness/daily_driver.py`:
   - `load_daily_tasks(root="evals/daily_driver", split=None) -> list[dict]` — load every `*.json`
     under `dev/` and `holdout/` (or just the given split); each task is `{id, category, split,
     instruction, files, ...}` with EXACTLY ONE oracle: `test_cmd` (pytest) OR `oracle{type,match,
     expect}` (answer/state). Sort by `(category, id)`. Tolerate a missing `holdout/` dir.
   - `check_answer(answer: str, oracle: dict) -> bool` — deterministic answer-oracle. `match="set"`:
     extract identifier-like tokens (`[A-Za-z_][A-Za-z0-9_]*`) from `answer`, compare as a SET to
     `set(oracle["expect"])` (order-insensitive, must match exactly — no missing, no extra from the
     expect universe; ignore stop-words/plain English by intersecting only against a candidate set is
     NOT allowed — the model must name exactly the right identifiers). `match="exact"`: normalized
     (strip/casefold) equality. `match="regex"`: every pattern in `expect` found in `answer`. Pure.
   - `check_state(workdir, oracle) -> bool` — run the oracle's state assertion in `workdir`
     deterministically (dispatch implemented even if no `ops` seed exists yet).
   - `run_daily(tasks, *, answer_fn=None, max_iters=3) -> dict` — route by oracle: pytest-oracle tasks
     (`test_cmd` present) reuse the PROVEN isolated `fix_loop` path (reuse `eval_runner.setup_task` +
     `fix_loop`); answer-oracle tasks call `answer_fn(task) -> str` (INJECTABLE; default stub returns
     `""` so the core runs offline) then `check_answer`; state-oracle tasks call `check_state`. Return a
     scorecard: per-category `{passed,total,rate,wilson}`, the WEIGHTED headline
     `Σ(wᵢ·rateᵢ)/Σwᵢ`, and a `dev` vs `holdout` breakdown.
2. Category weights map in the module: navigate 20 · edit 20 · fix 15 · write-tests 10 · refactor 10 ·
   build 10 · multi-file 10 · ops 5 (single source; matches the README table).
3. `tests/test_ext005_daily_driver.py` (offline, no Jetson): load the two seed tasks; `check_answer`
   TRUE on `"start and reload"` and FALSE on `"start"` alone and on `"start reload helper"`; the edit
   seed routes to the pytest path; `run_daily(tasks, answer_fn=stub)` returns a scorecard carrying
   per-category + weighted + dev/holdout fields. Full suite stays green.
4. Do NOT change `run_task_list` / `run_suite` / the authored path (zero regression).

#### Implements
- [REQ-13] The Pursuit scoreboard is the parity instrument (daily-driver runner: loader, category oracle router, weighted scoring)
