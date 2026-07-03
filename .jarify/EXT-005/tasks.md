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

### [TASK-3] Daily-driver runner: build-module routing (generative, held-out oracle)

Extend `harness/daily_driver.py` so the **build-module** category is scored end-to-end — the first
DISCRIMINATING category (generative build from a spec, no failing test handed to the model; contrast
the fix/edit categories which lean on `fix_loop`'s given failing test). Reuse the proven
`harness/intent_loop.build_from_intent` + a HELD-OUT oracle. Offline + test-gated. Two seed
build-module tasks already exist: `evals/daily_driver/dev/build_stack.json`, `.../build_word_freq.json`
(schema: `{id, category:"build-module", split, intent, target, func, signature, test_cmd, oracle_test}`
— `intent` is shown to the model; `oracle_test` is the held-out grader, NEVER shown).

#### Steps
1. `load_daily_tasks`: accept build-module tasks — they carry `intent` + `oracle_test` (+ `target`,
   `func`, `signature`, `test_cmd`) instead of a simple `test_cmd`-only or `oracle` block. Do NOT
   misroute them as pytest-oracle tasks. Keep edit/fix (`test_cmd`) and navigate/state (`oracle`)
   loading unchanged.
2. `run_daily`: route `category == "build-module"` through `harness.intent_loop.build_from_intent(task,
   max_iters=max_iters)` in an isolated temp dir (mirror how `build_eval`/`intent_loop` invoke it),
   then grade by running the held-out `oracle_test` against the built solution (write `oracle_test` to
   the temp dir as a test file and run `test_cmd`; solved = oracle passes). **HONESTY (critical, Tenet
   3):** `oracle_test` must NEVER be written into the build dir before/while the model builds, and must
   never be passed into `build_from_intent` / any prompt — verify `build_from_intent` only receives
   `intent`/`signature`/`func`, not `oracle_test`. The oracle is written + run ONLY for grading, after
   the build. Record per-task `solved` (oracle pass) exactly like the other categories.
3. The weighted headline + per-category + dev/holdout scorecard must now include a `build-module` row
   when such tasks are present. No change to edit/fix/navigate/state scoring.
4. `tests/test_ext005_daily_driver.py`: add offline tests — monkeypatch `build_from_intent` to write a
   KNOWN-correct solution (so no live model), load the two build seeds, assert `run_daily` routes them
   to the build path, runs the held-out oracle, and scores them; AND an anti-leak assertion that the
   oracle_test content is not passed into the (monkeypatched) `build_from_intent` call args. Full suite
   stays green; the known-unrelated `logs/` doctest failure is not ours.

#### Implements
- [REQ-13] The Pursuit scoreboard is the parity instrument (build-module generative category routing + held-out oracle)

### [TASK-4] Daily-driver runner: multi-file category routing (wire the multi_file_fix capability into the parity instrument)

MEASURED GAP (docs/GAP-MAP.md, 2026-07-02): the daily-driver runner declares 8 frequency-weighted
categories but the suite populates only 4 (navigate/edit/fix/build-module) — **multi-file (weight 10),
refactor, write-tests, ops are EMPTY**, so REQ-13's weighted headline silently covers only 65% of the
declared workload. This task fills the highest-capability-value missing category, **multi-file**, by
routing it through the already-built `harness/multi_file.multi_file_fix` (EXT-010, incl. the REQ-6
minimal-diff pass) — a cross-file fault where the fix must touch a DIFFERENT file than the failing test
(the fix/edit categories are single-file via `fix_loop`; multi-file is the discriminating cross-file
class). Scope is multi-file ONLY (refactor/write-tests/ops are separate follow-up tasks).

#### Steps
1. `harness/daily_driver.run_daily`: add a `category == "multi-file"` branch (BEFORE the generic
   `test_cmd`→`fix_loop` branch so it isn't misrouted) that sets up the task's `files` in an isolated
   temp dir and calls `harness.multi_file.multi_file_fix(cwd, test_cmd, ...)` (mirror how the fix branch
   sets up `Task`/`setup_task`, but use the multi_file entry point that localizes across the import
   closure). `solved = bool(result all-green)`. Keep build-module/edit/fix/navigate/state routing
   unchanged.
2. `load_daily_tasks`: accept multi-file tasks — schema `{id, category:"multi-file", split, instruction,
   files:{path:content,...} (≥2 files: the failing test file + ≥1 source file holding the bug in a
   DIFFERENT file), test_cmd}`. Do not misroute as a single-file fix.
3. Seed **2 held-out multi-file dev tasks** under `evals/daily_driver/dev/` (e.g. a bug in
   `geometry.py` surfaced by `test_shapes.py` importing `shapes.py` importing `geometry.py`; and a
   second distinct cross-file scenario). HONEST (Tenet 3): the task is a GENUINE cross-file fault the
   model must localize+fix; the `test_cmd` is the grader; do NOT leak the fix or tune the task to pass.
   Tasks must be real (not trivially solvable, not gamed) and representative of everyday multi-file work.
4. The weighted headline + per-category scorecard must include a `multi-file` row when such tasks are
   present. `tests/test_ext005_daily_driver.py`: add an OFFLINE test (monkeypatch `multi_file_fix` to a
   known result) asserting run_daily routes `category=="multi-file"` to the multi_file path and scores
   it; full suite stays green.

#### Implements
- [REQ-13] The Pursuit scoreboard is the parity instrument (multi-file category routing → full weighted-category coverage)
