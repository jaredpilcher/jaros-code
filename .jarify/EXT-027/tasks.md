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
