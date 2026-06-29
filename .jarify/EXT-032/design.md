# EXT-032 Design: Test-feedback repair scaffold

## Motivation

EXT-031 MEASURED RESULT #2 (cell #36) settled: scaffolds do NOT lift from-scratch synthesis.
The refined reframe: **a scaffold multiplies WITHIN its class**.  The one promising untested
cell is **#35: scaffold x strong base (qwen3-4b-thinking) x right class (hard-repo-repair)**.

qwen3-4b-thinking cracked 1/4 of the hard bigbar class bare (single-shot).  The harness had
no scaffold for this combination.  The cheapest, best-fitting scaffold for a slow reasoner
(~10 tok/s, long `<think>` traces) is a TEST-FEEDBACK REPAIR loop:

    attempt → run the failing visible test → on fail, re-solve given the real traceback → retest

Bounded to 1-2 retries (cost guard: at most 3 LLM calls per function).

## Architecture

```text
  harness/repair_solve.py
  ┌──────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │  repair_solve(spec, name, context, *, gen_fn, test_fn,              │
  │               max_retries=2) -> dict                                 │
  │  ┌────────────────────────────────────────────────────────────────┐  │
  │  │  attempt = gen_fn(spec, name, context)    ← model plane       │  │
  │  │  result  = test_fn(attempt)               ← execution plane   │  │
  │  │    -> {passed: bool, failure_text: str}                        │  │
  │  │  if result["passed"]:                                          │  │
  │  │      return {solved:True, retries:0, ...}                      │  │
  │  │  for retry in range(max_retries):                              │  │
  │  │      repair_ctx = context + previous_attempt + failure_text    │  │
  │  │      attempt = gen_fn(spec, name, repair_ctx)  ← model plane  │  │
  │  │      result  = test_fn(attempt)               ← execution     │  │
  │  │      if result["passed"]: return {solved:True, ...}           │  │
  │  │  return {solved:False, retries:max_retries, ...}               │  │
  │  └────────────────────────────────────────────────────────────────┘  │
  │                                                                      │
  │  make_r1_gen_fn() -> r1_code  (deferred import, offline-safe)       │
  │                                                                      │
  └──────────────────────────────────────────────────────────────────────┘

  .jaros-data/qwen3_repair_probe.py  (throwaway, gitignored)
  ┌──────────────────────────────────────────────────────────────────────┐
  │  for each hard [fail] task:                                          │
  │    targets = _target_funcs(repo, task)                               │
  │    for cf, fn, parent_src in targets:                                │
  │      gen_fn = make_r1_gen_fn()           ← r1_code (qwen3)          │
  │      test_fn = _make_test_fn(cf, fn)                                 │
  │        -> applies code to repo, runs _run_nodes_fb(task["redgreen"]) │
  │        -> returns {passed, failure_text}  (VISIBLE test only)        │
  │      repair_solve(spec, fn, ctx, gen_fn=gen_fn, test_fn=test_fn)    │
  │    final oracle: _run_nodes(task["redgreen"])  (score-only)          │
  └──────────────────────────────────────────────────────────────────────┘

  tests/test_repair_solve.py  (fully offline, all mocked)
  ┌─────────────────────────────────────────────────────────────────────┐
  │  (a) first attempt passes  → retries=0, gen_fn called once          │
  │  (b) fail then retry passes → failure_text in 2nd gen_fn context    │
  │  (c) all attempts fail     → solved=False, max_retries respected     │
  │  (d) test_fn sole arbiter  → gen_fn "claims success", test_fn=fail  │
  │                              → solved=False                         │
  │  + attempts list ordering, make_r1_gen_fn callable factory,         │
  │    import/return-key smoke tests                                     │
  └─────────────────────────────────────────────────────────────────────┘
```

## Two-Plane Discipline (Tenet 1)

- **Model plane**: `gen_fn(spec, name, context)` emits a code string — pure inert data.
- **Execution plane**: `test_fn(code)` runs the visible test deterministically and returns
  `{passed, failure_text}`.  No model call inside `test_fn`.

The failure_text is the ONLY information that crosses from the execution plane back to the
model plane (via the repair context on the next gen_fn call).  This is deterministic, bounded,
and observable — consistent with Tenet 1.

## Honesty Invariant (Tenet 3)

The repair loop sees ONLY the VISIBLE failing test's output:

- `task["redgreen"]` = the pytest node IDs that go red→green in the commit.  These ARE the
  visible spec (the test the developer is given).
- `_run_nodes_fb(repo, task["redgreen"])` returns `(fails, failure_text)` from running THOSE
  nodes.  It is NOT a separate hidden oracle.
- The hidden oracle (`_run_nodes` called once at the end for scoring) is NEVER shown to the
  model.  It is score-only.

This mirrors the `r1_decorrelation.py` honesty comment: "oracle score-only; R1 gets the same
context the coders got."

## Cost Model

qwen3-4b-thinking at ~10 tok/s with max_tokens=9000:
- 1 attempt = ~900s worst case.
- max_retries=2 → 3 attempts → ~45 min worst case per function.
- Hard N=4 tasks → ~3 hours worst case.
- Operator runs with LLAMACPP_TIMEOUT_S=900 guard.

This is the CHEAPEST multi-call scaffold for a slow reasoning model (vs. 4-call
experiment_solve which is impractical at this token rate).

## Measured Result

(To be filled in by the operator after running qwen3_repair_probe.py.)

Baseline: qwen3-bare 1/4 (r1_decorrelation.py single-shot).
Hypothesis: repair scaffold lifts qwen3 to ≥2/4 on the hard class.

## MEASURED RESULT (2026-06-29) — #35 (repair scaffold × qwen3) is DEVICE-BLOCKED on the Jetson, not cleanly measurable
Ran the repair scaffold (attempt -> visible-test failure -> retry, max_retries=2) on qwen3-4b-thinking over the 4 hard tasks (R1_MAX_TOKENS=8000, LLAMACPP_TIMEOUT_S=700). Tasks 1 & 2 both => err:RuntimeError = TIMEOUTS, and free RAM hit 336MB (OOM-imminent). Task 1 (cca32949) is a task qwen3 CRACKS BARE single-shot — its err here CONFIRMS the errors are harness/device limits, NOT model failures (per the honest-measurement rule: err/timeout/OOM != a model 0).
ROOT CAUSE (a real DEVICE constraint, honestly recorded): qwen3-4b-thinking is SLOW (~10 tok/s) and every call emits a long <think> trace; bare single-shot already needed ~1200s + 10000 tokens for the runaway tasks (and 1/4 were inconclusive from timeouts). A MULTI-CALL scaffold (repair = up to 3 calls/task) multiplies that time AND the RAM pressure (ctx 16384 KV + multiple long gens -> 336MB free -> OOM). So multi-call scaffolds on the slow thinking model do not fit the 7.3GB Jetson's time+RAM budget. This echoes the R1-7B OOM and the bare-qwen3 1/4-conclusive (3 timed out).
HONEST VERDICT on the #35 cell ("scaffold × strong base × right class"): NOT CLEANLY MEASURABLE ON THIS DEVICE — the device (RAM + ~10tok/s) blocks the multi-call scaffold, so we cannot say whether repair would lift qwen3 (it's neither confirmed nor refuted). The PRACTICAL hard-class solver on this hardware is SINGLE-SHOT qwen3 (1/4, via REQ-6 escalation), which already works. Answering #35 cleanly needs a faster/bigger device (more RAM for KV headroom + faster gen so a multi-call loop completes). This is a DEVICE constraint, not a model limit and not "repair doesn't help". repair_solve (EXT-032) remains a SOUND general mechanism (917 tests) — it is simply impractical to run on qwen3 on THIS Jetson; it is usable with the FAST models (gemma/qwen2.5) where the hard-repair class doesn't apply, so its on-class home awaits faster hard-class hardware.
COMBINED #35+#36 CONCLUSION: scaffolds do not lift easy/medium SYNTHESIS (#36, measured); and scaffolds on the strong base's hard class (#35) are device-blocked here. The banked, real hard-class win stands: single-shot qwen3 cracks it via escalation. Further scaffold lift on the hard class is a future-hardware question.
