# Implementation Tasks

### [TASK-1] Build test-feedback repair scaffold, qwen3 hard-class probe, offline tests, and EXT-032 spec

Complete EXT-032 implementation: injectable repair loop, live qwen3 factory, throwaway probe,
offline test suite, and spec folder.

#### Steps
1. Write `harness/repair_solve.py` with:
   - `repair_solve(spec, name, context, *, gen_fn, test_fn, max_retries=2) -> dict` — bounded
     test-feedback repair loop; gen_fn is injectable; test_fn is the sole arbiter; on fail
     re-calls gen_fn with failure_text appended to original context; returns
     {solved, code, retries, attempts}.
   - `make_r1_gen_fn() -> callable` — factory that returns r1_code from harness.r1_adapt;
     import deferred (offline-safe).
   - Wrap repair_solve in `# #EXT-032-REQ-1 Start/End`; wrap make_r1_gen_fn in
     `# #EXT-032-REQ-2 Start/End`.
2. Write `.jaros-data/qwen3_repair_probe.py` (throwaway, gitignored):
   - Mirrors r1_decorrelation.py structure (loads hard bigbar [fail] tasks).
   - gen_fn = make_r1_gen_fn(); test_fn wraps _run_nodes_fb on task["redgreen"]
     (VISIBLE test nodes only).
   - repair_solve per function; final oracle _run_nodes (score-only).
   - Reports cracked X/n vs qwen3-bare 1/4 baseline.
   - Documents: serve qwen3 first, restore gemma after.
3. Add `.jaros-data/r1_decorrelation.py` and `.jaros-data/qwen3_repair_probe.py` to .gitignore.
4. Write `tests/test_repair_solve.py` (all offline, all mocked):
   - (a) first attempt passes → retries=0, gen_fn called once.
   - (b) fail then retry passes → failure_text in 2nd gen_fn context.
   - (c) all attempts fail → solved=False, max_retries respected.
   - (d) test_fn sole arbiter: code "looks correct" but test_fn=fail → not solved.
   - Plus: attempts ordering, make_r1_gen_fn callable factory, import smoke, return-keys smoke.
5. Create `.jarify/EXT-032/` with requirements.md, design.md, tasks.md, index.json.
6. Run `python -m pytest tests/ -q` — full suite green (917+ tests), no regressions.
7. Commit with footer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

#### Implements
- [REQ-1] Bounded test-feedback repair loop
- [REQ-2] qwen3-4b-thinking hard-class repair probe
