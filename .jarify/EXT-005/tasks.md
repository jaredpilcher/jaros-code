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

### [TASK-5] Daily-driver runner: refactor category routing (two-plane; wire refactor.py into the parity instrument)

Continue closing REQ-13's category-coverage gap (docs/GAP-MAP.md: after TASK-4, coverage is 75/100 weight;
`refactor` weight-10 is still EMPTY). Wire the **refactor** category end-to-end through the ALREADY-BUILT
deterministic `harness/refactor.py::rename_symbol` (EXT-003 REQ-6, tokenize-scoped — renames only NAME tokens,
not comments/strings). TWO-PLANE (on-doctrine): the small model makes ONE narrow judgment — extract the
`(old_symbol, new_symbol)` rename pair from the natural-language instruction — and the DETERMINISTIC tool applies
it. Scope: rename-refactor ONLY (move_symbol / extract-method are separate follow-ups).

#### Steps
1. `harness/daily_driver.run_daily`: add a `category == "refactor"` branch (before the generic `test_cmd` branch).
   Solve path: (a) MODEL judgment — from `task["instruction"]`, extract the `(old, new)` symbol pair (a single
   grounded classify the 2B can do; use a narrow prompt + degeneracy guard; if extraction fails, `solved=False`,
   never crash); (b) DETERMINISTIC — write the task `files` to an isolated temp dir and call
   `harness.refactor.rename_symbol(cwd, old, new, ...)`; (c) GRADE — see the two-part oracle below. Keep all other
   category routing unchanged.
2. **Two-part oracle (HONESTY — Tenet 3, prevents a no-op passing):** a refactor is `solved` ONLY IF BOTH
   (i) the behavior `test_cmd` still passes (behavior preserved — the test exercises a STABLE public entry point that
   is NOT the renamed symbol, so a correct rename keeps it green), AND (ii) the structural change actually happened
   (the OLD symbol name is gone as a definition and the NEW name is present in the target file). A no-op (model fails
   to rename) fails part (ii); a rename that breaks behavior fails part (i). Do NOT grade on behavior alone.
3. Seed **2 held-out refactor dev tasks** under `evals/daily_driver/dev/` — e.g. rename an INTERNAL helper
   (`_calc` → `_compute_total`) while the public function the test calls stays stable; the instruction names the
   rename in natural language WITHOUT giving the literal tokenized diff. Genuine, not gamed; the model must parse the
   instruction and the tool must apply the scoped rename. schema `{id, category:"refactor", split, instruction,
   files:{...}, target, test_cmd, oracle:{type:"refactor", old_absent, new_present}}` (or reuse existing fields —
   match whatever the runner reads; keep it minimal).
4. `tests/test_ext005_daily_driver.py`: OFFLINE test (monkeypatch the model extraction to return a known `(old,new)`,
   let the REAL `rename_symbol` run deterministically) asserting run_daily routes `category=="refactor"`, applies the
   rename, and enforces BOTH oracle parts (add a no-op case that must score `solved=False`). Full `tests/` stays green.

#### Implements
- [REQ-13] The Pursuit scoreboard is the parity instrument (refactor category routing → 85/100 weighted-category coverage)

### [TASK-6] Daily-driver runner: write-tests category routing (NEW capability — model writes tests, graded by MUTATION testing)

Fill the `write-tests` weight-10 category (docs/GAP-MAP.md: coverage 85/100 after TASK-5; write-tests + ops remain).
Unlike multi-file/refactor (which WIRE existing capabilities), this adds a GENUINELY NEW capability jaros-code lacks:
generating tests for given code. The honest grader is **MUTATION TESTING** (the gold standard — the ONLY way to prove
generated tests are real, not trivial): the model's tests must PASS on the reference/correct code AND KILL a seeded
mutant. A degenerate `assert True` test passes on the reference but fails to kill any mutant → correctly `solved=False`.

#### Steps
1. `harness/daily_driver.run_daily`: add a `category == "write-tests"` branch (before the generic `test_cmd` branch).
   Solve path: (a) MODEL generates the test-file CONTENT from `task["instruction"]` + the reference code (mirror the
   build-module/answer model-call convention: build_llm/LlmRequest or the existing answer path); (b) DETERMINISTIC
   grading via the mutation oracle below. If the model emits no usable test code, `solved=False`, never crash.
2. **MUTATION ORACLE (HONESTY — Tenet 3, the whole point):** `solved` is True ONLY IF BOTH
   (i) the generated tests PASS when run against the REFERENCE (correct) code — write reference files + the generated
   test into a temp dir, run `test_cmd`, must be green (the tests are valid, not broken), AND
   (ii) the generated tests KILL every seeded mutant — for each mutant in `task["mutants"]`, write the MUTANT version
   (replacing the corresponding reference file) + the generated test, run `test_cmd`, and it MUST FAIL (the tests
   catch the bug). solved = passes-on-reference AND every-mutant-killed. A trivial/degenerate test fails (ii).
   NEVER show the mutant or the reference test to the model — only the reference code + instruction go into the prompt.
3. Seed **2 held-out write-tests dev tasks** under `evals/daily_driver/dev/` — e.g. reference `is_prime(n)` (correct)
   + instruction "write pytest tests for is_prime in primes.py" + 1-2 mutants (`n % i == 0`→`n % i != 0`, or an
   off-by-one on the range bound) that CORRECT tests would catch. Genuine, not gamed; the mutants must be behavior-
   changing bugs a competent test suite kills. schema `{id, category:"write-tests", split, instruction,
   files:{reference}, target (test filename to write), test_cmd, mutants:[{file, content}] }` (adapt field names to
   what the runner reads; keep minimal).
4. `tests/test_ext005_daily_driver.py`: OFFLINE test (monkeypatch the model test-generation to return (a) a KNOWN-GOOD
   test that passes reference + kills the mutant → asserts solved=True, and (b) a degenerate `assert True` test →
   asserts solved=False because no mutant is killed). Full `tests/` stays green.

#### Implements
- [REQ-13] The Pursuit scoreboard is the parity instrument (write-tests category via mutation oracle → 95/100 weighted-category coverage)

### [TASK-7] Daily-driver runner: ops category routing (the LAST category → 100/100 weighted coverage)

Fill the final empty category `ops` (weight 5) → completes REQ-13's declared 8-category coverage (100/100). Unlike the
algorithmic categories, `ops` is about producing correct CONFIG / FILE-STATE artifacts (gitignore, config files,
requirements, directory/file structure) — a distinct everyday capability graded by the ALREADY-BUILT `check_state`
oracle (`file_exists` / `file_contains` regex list / `cmd_exit0`). The oracle side is done; this task builds the SOLVE
path + seed tasks.

#### Steps
1. `harness/daily_driver.run_daily`: the `oracle.type == "state"` branch currently just `_write_files` the GIVEN files
   then `check_state` — with NO model step producing the artifact. Add an `ops` SOLVE path: for `category == "ops"`,
   the MODEL generates the required artifact CONTENT from `task["instruction"]` (mirror the answer_fn/build model-call
   convention; the model returns the file body, or a small map of filename→content for multi-file ops), the harness
   writes it into the temp dir, THEN `check_state` grades. If the model emits nothing usable, `solved=False`, no crash.
   Keep the existing non-ops state-oracle path (pre-given files) working for back-compat.
2. **HONESTY (Tenet 3):** `check_state` must grade REAL produced state — never write the expected artifact for the
   model, and never leak the oracle's exact regex/expected file into the model prompt (only the instruction). A wrong
   or empty artifact must fail. Prefer discriminating oracles: `cmd_exit0` (the artifact must actually work) or
   MULTI-pattern `file_contains`, not a single trivially-echoed string.
3. Seed **2 held-out ops dev tasks** under `evals/daily_driver/dev/` — genuine config/ops artifacts, e.g. (a) "create a
   `.gitignore` that ignores `__pycache__/`, `*.pyc`, and a `.env` file" → `file_contains` with 3 regex patterns; (b)
   "create `setup.cfg` with a `[flake8]` section setting `max-line-length = 100`" → `file_contains` (section + setting)
   or `cmd_exit0`. Instructions describe the requirement in prose; the model must produce the correctly-formatted file.
4. `tests/test_ext005_daily_driver.py`: OFFLINE test (monkeypatch the model ops-generation) — a KNOWN-GOOD artifact →
   solved=True, a WRONG/empty artifact → solved=False. Full `tests/` stays green.

#### Implements
- [REQ-13] The Pursuit scoreboard is the parity instrument (ops category routing → 100/100 weighted-category coverage complete)

### [TASK-8] write-tests SELF-REPAIR loop (validated capability lift, 6/8→7/8 on probe)

MEASURED (docs/GAP-MAP.md 2026-07-03): the write-tests capability is 75% (6/8 varied fns); the misses are the model
writing a WRONG test ASSERTION (e.g. `assert clamp(-5,-10,-1)==-10` when the correct code returns -5) → the tests fail
on the REFERENCE code → the mutation oracle correctly scores unsolved. PROBED a self-repair loop
(`.jaros-data/writetests_repair_probe.py`): when generated tests FAIL on the reference, feed the pytest failure back and
ask the model to fix the wrong assertion. RESULT: lifts `palindrome` FAIL→SOLVED in 1 repair (the failure output shows
the concrete actual value, a strong hint); `clamp` stays unsolved (a persistent model reasoning error repair can't fix).
So it's a PARTIAL, real, no-downside lever (repair only ever helps: if it can't fix, the task stays unsolved as before).
Productionize it into the write-tests solve path.

#### Steps
1. `harness/daily_driver.py`: in `_run_write_tests_task` (or a helper it calls), BEFORE final grading, add a bounded
   self-repair loop: run the generated tests against the REFERENCE code; if they FAIL (don't pass on correct code),
   feed the pytest failure output back to the model with a prompt to fix ONLY the incorrect assertion(s) (mirror the
   `.jaros-data/writetests_repair_probe.py::repair` prompt), re-parse, re-run on reference; repeat up to
   `max_repair` (default 2) times. Then grade with the EXISTING two-part mutation oracle (`_write_tests_oracle_ok`)
   unchanged. HONESTY (Tenet 3): the repair prompt gets the REFERENCE-run failure ONLY — NEVER the mutant or the
   oracle's expected patterns (a wrong assertion is diagnosed from the correct code, not from any mutant). Repair is
   strictly non-degrading: a task that was solved stays solved; a task repair can't fix stays unsolved.
2. Keep the model call count bounded (default 2 repairs) so a stubborn task can't loop forever; on any model/parse
   failure, fall through to grading the last good tests (never crash).
3. `tests/test_ext005_daily_driver.py`: OFFLINE test (monkeypatch the generation to first return a test with a WRONG
   assertion that fails on the reference, then on the repair call return a corrected test) — assert the repair loop
   runs, the corrected tests are graded, and the task scores solved=True; AND a case where repair never fixes it →
   stays solved=False (non-degrading). Full `tests/` stays green.

#### Implements
- [REQ-13] The Pursuit scoreboard is the parity instrument (write-tests self-repair → lifts the test-gen capability, no-downside)

### [TASK-9] Amortization-ratio telemetry instrument

Build the standalone deterministic AMORTIZATION-RATIO instrument (PRIME-001 scoreboard instrument #5,
REQ-14). A new, self-contained module — no model calls, no dependency on the daily-driver runner or
other scoreboard code — that tags serve/solve events as `MEMORY_HIT` (a reused verified artifact) or
`MODEL_CALL` (fresh inference) and computes the reuse ratio. Fully offline + test-gated.

#### Steps
1. Create `harness/amortization.py`:
   - `record_event(source, *, kind=None, tokens=None, meta=None)` — appends `{source, kind, tokens,
     meta, ts}` to an append-only in-process event log; also appends the same record as one JSON line
     to an optional JSONL sink file under the data dir (best-effort, swallow I/O errors). Never raises,
     even on a garbage/unknown `source` or malformed `meta` — unknown sources are still recorded (not
     silently dropped) but counted separately from `MEMORY_HIT`/`MODEL_CALL` in the ratio calculation.
   - `amortization_ratio(events=None) -> dict` — computes over the given events (or the in-process log
     when `events=None`): `total`, `memory_hits`, `model_calls`, `ratio = memory_hits/total` (`0.0`
     when `total==0`, no exception), and `model_calls_avoided` (= `memory_hits`). Optionally, when every
     event carries a `tokens` value, also include a token-weighted variant. Always returns a
     well-formed dict; never raises.
   - `reset()` — clears the in-process event log so a fresh measurement window can start; a small
     scoped-collector helper (context manager or class) isolates a window of recorded events without
     disturbing any other caller's log, for use in tests and per-run reporting.
2. Create `tests/test_amortization.py`: record a mix of `MEMORY_HIT`/`MODEL_CALL` events and assert
   `amortization_ratio` returns the exact `total`/`memory_hits`/`model_calls`/`ratio`/
   `model_calls_avoided`; assert `total==0` yields `ratio == 0.0` with no exception; assert `reset()`/the
   scoped collector isolates counts across windows; assert `record_event` never raises on a garbage
   `source` value or malformed `meta`/`tokens` input. Full `tests/` suite stays green.
3. Do not wire `harness/amortization.py` into `system_builder.py`, `coherence_suite.py`, `cli.py`, or
   any other harness module in this task — this task is the instrument only; wiring real serve paths
   to emit events (so the live ratio reflects actual reuse) is an explicit follow-up task.

#### Implements
- [REQ-14] Amortization-ratio telemetry instrument

### [TASK-10] Shadow-mode parity replay harness (REQ-15)

Build the shadow-mode parity REPLAY MECHANISM + transcript FORMAT (PRIME-001 scoreboard instrument
#6): the harness that will replay the owner's REAL Claude Code task prompts against jcode and score
whether jcode achieves a comparable result. This task builds the harness only — it does NOT contain
real Claude Code transcript data (that is an explicit follow-up the owner seeds later); the module
must be fully offline-testable with synthetic transcripts. Reuse the existing black-box oracle shapes
from `harness/system_suite.py` rather than duplicating subprocess/tree-kill logic (Tenet 3).

#### Steps
1. Create `harness/shadow_replay.py` with a `ShadowTask` dataclass (`task_id: str`, `prompt: str`,
   `kind: str`, `acceptance: dict`) and document the JSONL transcript FORMAT in the module docstring:
   one shadow task per line, `{task_id, prompt, kind ("build"|"modify"|"answer"|...), acceptance}`.
   For `kind in ("build","modify")`, `acceptance = {"entry": <optional relative path, default
   "main.py">, "checks": [[argv, stdin, expect], ...]}` — a list of black-box CLI checks in the same
   `(argv, stdin, expected_substring)` shape used by `harness.system_suite.CreationTask.checks`. For
   `kind == "answer"`, `acceptance = {"expect_substring": "..."}` (or `{"expect_all": [...]}` for
   multiple required substrings).
2. Implement `load_transcripts(path) -> list[ShadowTask]`: read the file line by line, `json.loads`
   each non-blank line, and construct a `ShadowTask`; wrap parsing of each line in its own
   `try/except Exception` so a malformed line is skipped (never raises) and everything that does
   parse is returned; a missing/unreadable file returns `[]` rather than raising.
3. Implement `run_shadow_replay(tasks, solve_fn, python_exe=None) -> dict`: for each task, create an
   isolated temp dir via `tempfile.mkdtemp()`, call `solve_fn(task.prompt, root)` inside a
   `try/except Exception` (any exception scores that task `passed=False` and the loop continues —
   never raises). For `build`/`modify` tasks, resolve the entrypoint (the acceptance's `entry`, else
   `_resolve_entry` on a `solve_fn`-returned plan dict, else `root/main.py`) and run every
   `(argv, stdin, expect)` check via `harness.system_suite._run_cli`, importing rather than
   reimplementing that function and `_resolve_entry`; `passed` is True only if every check's process
   exits 0 and contains its expected substring. For `answer` tasks (and any other kind, as a
   substring-check fallback), score via the acceptance's `expect_substring`/`expect_all` against
   `str(solve_fn(...))`. Best-effort tag each task's solve as a `MODEL_CALL` via
   `harness.amortization.record_event` inside a `harness.amortization.ScopedCollector` window (wrapped
   in `try/except Exception` so amortization telemetry can never break the replay), and include the
   window's `amortization_ratio()` result in the returned dict when available. Clean up each task's
   temp dir best-effort after scoring. Return `{total, passed, parity_rate, per_task: [{task_id, kind,
   passed}, ...], per_kind: {<kind>: {total, passed, rate}, ...}, amortization?}` where `parity_rate`
   is `passed/total` and is `0.0` (never a divide error) when `total == 0`.
4. Tag the new module's code with `# #EXT-005-REQ-15 Start` / `# #EXT-005-REQ-15 End` traceability
   comments.
5. Create `tests/test_shadow_replay.py` (offline, synthetic transcripts only — no real Claude Code
   data): (a) a JSONL fixture with 2-3 build tasks with CLI-check acceptance plus one malformed line,
   asserting `load_transcripts` returns only the tasks that parse; (b) a stub `solve_fn` that writes a
   correct `main.py` for one task and a wrong/empty one for another, asserting `run_shadow_replay`
   scores the right per-task `passed` values and an exact aggregate `parity_rate` (e.g. `1/2 == 0.5`);
   (c) a `solve_fn` that raises, asserting `run_shadow_replay` never raises and scores that task
   `passed=False`; (d) `run_shadow_replay([], solve_fn)` returns a well-formed aggregate with
   `parity_rate == 0.0` and no divide error; (e) an `answer`-kind task scored by substring match. Run
   `python -m pytest tests/test_shadow_replay.py -q` then the full `python -m pytest tests/ -q` suite
   and keep both green.

#### Implements
- [REQ-15] Shadow-mode parity replay harness
