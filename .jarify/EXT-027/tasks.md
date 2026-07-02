# EXT-027 Tasks

## TASK-1: Build solution_memory.py scaffold + tests (DONE)

#### Implements
REQ-1

#### Steps
1. Create `harness/solution_memory.py` with `record_verified`, `recall_similar`, `inject_verified_example`.
2. Reuse `new_class_log._build_signature` + `_normalise` for the deterministic signature.
3. Create `tests/test_solution_memory.py` (OFFLINE, temp path) covering all acceptance criteria.
4. Run `python -m pytest tests/test_solution_memory.py tests/ -q` -- all green.
5. Add traceability comments (`#EXT-027-REQ-1 Start/End`) and update `.jarify/EXT-027/index.json`.

**Status: DONE** (implemented in this session)

---

## TASK-2: Kill-test -- measure WITH vs WITHOUT inject (ACTIVE HOURS ONLY)

#### Implements
REQ-2

#### Steps
1. Seed the store: run `pass1_eval` or any passing-solve path to accumulate records in
   `.jaros-data/artifacts/solution_memory.jsonl`.
2. Run the honest bar WITHOUT memory injection (baseline).  Record result in
   `.jarify/EXT-027/requirements.md` under REQ-2.
3. Wire `inject_verified_example` into the `pass1_eval` solve prompt temporarily.
4. Re-run on the SAME problems; compare WITH vs WITHOUT honestly.
5. If confirmed lift (>= +2pp, outside Wilson overlap, held-out): adopt into default solve;
   mark REQ-2 [x] in requirements.md and status -> covered.
   If non-result: record faithfully; leave inject unwired; note the negative in REQ-2.

**Status: NOT STARTED** (requires active hours + Jetson running)

### [TASK-2] Wire auto-capture of verified solves into run_daily (REQ-3)

`record_verified` is built+tested but called nowhere — the flywheel corpus is empty. Wire CAPTURE
(persistence only; NOT injection) into the daily-driver runner so every verified solve is recorded.

#### Steps
1. In `harness/daily_driver.py::run_daily`, after a code-producing task (category in
   {edit, fix, build-module, multi-file}) is marked SOLVED, call
   `harness.solution_memory.record_verified(problem, code)` best-effort where:
   - `problem = {"source": <the original buggy file content or the build spec/intent>,
     "problem_class": <map category: edit/fix/build-module -> "standalone-fn-gen",
     multi-file -> "multi-file">}` (pass problem_class explicitly so it's not misinferred),
   - `code = <the winning solution>`: for fix_loop-path tasks read the solved target file's final
     content from the isolated temp dir BEFORE it's cleaned; for build-module read the built module.
   Wrap in try/except (record_verified is already best-effort, but never let capture affect the
   task result or scorecard). Do NOT capture navigate/answer tasks (no code) or UNSOLVED tasks.
2. Do NOT wire `recall_similar`/`inject_verified_example` anywhere (injection stays REQ-2-gated;
   default solve prompt unchanged). Capture-only.
3. `tests/test_ext027_autocapture.py` (offline, no model): monkeypatch `record_verified` to collect
   calls; run `run_daily` with a stubbed solve (some solved, some not, incl. a navigate task); assert
   record_verified was called ONLY for solved code-producing tasks, with `code` + `problem_class`
   present, and NOT for the navigate task or unsolved tasks. Full suite stays green.
4. Tag wired lines `# #EXT-027-REQ-3`; add the traceability entry to `.jarify/EXT-027/index.json`.

#### Implements
- [REQ-3] Auto-capture verified solves into the store (the flywheel corpus — start NOW)

**Status: DONE** (implemented in this session — `harness/daily_driver.py` calls
`record_verified` best-effort for solved edit/fix/multi-file/build-module tasks;
`harness/intent_loop.py` gained `IntentResult.code` so the built module content is
capturable; `tests/test_ext027_autocapture.py` proves capture-only, no recall/inject
wired; full suite green)

### [TASK-3] Test hygiene: daily-driver tests must not pollute the real flywheel store (REQ-3)

test_ext005_daily_driver.py's run_daily tests fake the solve (monkeypatched fix_loop/build_from_intent)
but leave `record_verified` REAL, so every pytest run appends fixture solves (Stack/clamp/word_freq)
to the real corpus `.jaros-data/artifacts/solution_memory.jsonl` — polluting the §7 distillation data
with non-genuine, heavily-duplicated test entries.

#### Steps
1. In tests that call `run_daily` with a faked/passing solve and do NOT already control capture
   (test_ext005_daily_driver.py: the run_daily scorecard tests + build-module route/score tests),
   prevent real-store writes — either monkeypatch `harness.daily_driver.record_verified` to a no-op
   collector, or monkeypatch `harness.solution_memory._DEFAULT_PATH` (and daily_driver's imported ref
   if bound) to a `tmp_path` file. Do NOT change production capture behavior; tests only.
2. Do NOT weaken test_ext027_autocapture.py (it already controls record_verified correctly) — only add
   store isolation where missing.
3. Clear the currently-polluted real store once (it is gitignored runtime state, all test-fixture
   noise, no genuine pursuit solves): truncate `.jaros-data/artifacts/solution_memory.jsonl`.
4. Run `python -m pytest tests/test_ext005_daily_driver.py tests/test_ext027_autocapture.py -q` (pass)
   + full suite (no NEW failures); confirm a full pytest run leaves the real store file empty/absent
   (no fixture writes). Tag any test changes; no index.json change needed (tests-only, no new REQ code).

#### Implements
- [REQ-3] Auto-capture verified solves — test-hygiene: capture must not pollute the corpus from tests

**Status: DONE** (implemented in this session — `tests/test_ext005_daily_driver.py`'s five
`run_daily` callers now monkeypatch `harness.daily_driver.record_verified` to a no-op before
calling `run_daily`; `test_ext027_autocapture.py` left unchanged; the polluted real store
`.jaros-data/artifacts/solution_memory.jsonl` (gitignored runtime state) was truncated once;
`pytest tests/test_ext005_daily_driver.py tests/test_ext027_autocapture.py -q` (23 passed) and
the full suite (1090 passed, 1 pre-existing unrelated failure in untracked `logs/`) both leave
the real store at 0 lines afterward — tests only, no production code or index.json changed)

### [TASK-4] Auto-capture verified SWE-bench solves via a solve-pipeline callback (REQ-4)

`record_verified` (REQ-1) still has no hook into the hardest-external-bar solve path
(`harness/swebench_live.py`), so the highest-value flywheel fuel (real SWE-bench test-verified
resolves) is not captured. Add a clean, decoupled `on_verified` callback fired ONLY at the
real-test-verified moment.

#### Steps
1. Add `_notify_verified(on_verified, diff)` — a best-effort helper (never raises) that invokes
   `on_verified(diff)` when given, mirroring `record_verified`'s never-raise contract.
2. Add an optional `on_verified: Callable[[str], None] | None = None` param to `solve_gated`;
   invoke it with the winning diff ONLY in the test-PASS branch, before returning — never on the
   self-consistency fallback (unverified) and never on the empty-candidate return.
3. Add the same `on_verified` param to `solve_with_repair`; invoke it with the passing diff at
   the verified moment (initial solve or a repair round passing the gated test), never on the
   give-up (last-attempt) return.
4. Add `tests/test_ext027_swebench_capture.py` (offline, no live model, canned `gen_fn`/
   `run_test_fn`): spy fires on pass, does not fire on self-consistency fallback or empty/give-up
   returns, a raising callback never changes the returned diff, default `None` is unaffected.
5. Tag the added lines `# #EXT-027-REQ-4 Start/End`; update `.jarify/EXT-027/index.json`.

#### Implements
- [REQ-4] Auto-capture verified SWE-bench solves via a solve-pipeline callback

**Status: DONE** (implemented in this session — `harness/swebench_live.py` gained
`_notify_verified` + `on_verified` params on `solve_gated`/`solve_with_repair`, invoked only at
the real-test-verified moment, best-effort, default `None` (backward compatible — no caller is
wired to it here per REQ-4 scope, the gitignored SWE-bench grind will pass
`on_verified=lambda diff: record_verified(...)` itself); `tests/test_ext027_swebench_capture.py`
(10 tests) proves fire-on-pass / no-fire-on-fallback / no-fire-on-give-up / raising-callback-safe
/ default-None-unaffected; full suite 1122 passed)
