---
id: EXT-032
title: Test-feedback repair scaffold
status: covered
priority: high
implementation:
  - file: harness/repair_solve.py
    ranges:
      - - 25
        - 133
---

### [REQ-1] Bounded test-feedback repair loop

`repair_solve(spec, name, context, *, gen_fn, test_fn, max_retries=2) -> dict` is the core
repair scaffold.  It runs: attempt = gen_fn(spec, name, context); test = test_fn(attempt)
-> {passed, failure_text}.  If passed -> {solved:True, code:attempt, retries:0}.  Otherwise
loop up to max_retries times: re-call gen_fn with the failure_text appended to the context
("Your previous attempt:\n<code>\nThe test FAILED with:\n<failure_text>\nFix it."); test again;
return on pass.  Returns {solved, code, retries, attempts:[...]}.

**test_fn is the SOLE arbiter.**  gen_fn never sees the oracle's pass/fail except via the
deterministic failure_text that test_fn returns from the VISIBLE failing test.  This preserves
Tenet 3: the oracle result is never leaked into the generation loop.

All callables are INJECTABLE (gen_fn, test_fn as parameters) so the loop is fully
offline-testable with mocks — no Jetson, no Docker required.

#### Acceptance Criteria
- [ ] repair_solve(spec, name, context, *, gen_fn, test_fn, max_retries=2) -> dict
- [ ] Returns {solved: bool, code: str, retries: int, attempts: list[str]}
- [ ] First attempt passes -> retries=0, gen_fn called exactly once
- [ ] On fail: re-calls gen_fn with failure_text appended to context
- [ ] Repair context contains "Your previous attempt:", the code, and "The test FAILED with:" + failure_text
- [ ] At most max_retries repair iterations (1 initial + max_retries retries = max_retries+1 total calls)
- [ ] test_fn is sole arbiter: gen_fn never sees oracle pass/fail directly
- [ ] attempts list contains every generated code string in order
- [ ] make_r1_gen_fn() factory returns r1_code from harness.r1_adapt as a drop-in gen_fn
- [ ] make_r1_gen_fn() import is deferred (module importable offline)

### [REQ-2] qwen3-4b-thinking hard-class repair probe

`.jaros-data/qwen3_repair_probe.py` (throwaway, gitignored) measures cell #35:
scaffold x strong base (qwen3-4b-thinking) x right class (hard-repo).  For each of the
N hard bigbar [fail] tasks, run repair_solve with r1_code as gen_fn + _run_nodes_fb on
the VISIBLE test nodes as test_fn (failure_text from visible test only).  Report cracked
X/n vs qwen3-bare's 1/4 baseline.  Operator-invoked (deferred; live Jetson required).

**HONESTY:** the repair loop sees the VISIBLE failing test's output only (the red->green
nodes from the commit = the spec the developer is given).  The hidden grading oracle
(_run_nodes for final scoring) is called once at the end and is NEVER shown to the model.
This is the #35 cell (the untested cell from the #36 reframe in EXT-031 design.md):
scaffold x strong base x right class; the cheapest fitting scaffold for a slow reasoner.

Context: the #36 measurement (EXT-031) settled that scaffolds don't lift from-scratch
synthesis.  The refined reframe: a scaffold multiplies WITHIN its class.  The one
promising untested cell is scaffold x qwen3-4b-thinking x hard-repo-repair.

#### Acceptance Criteria
- [ ] .jaros-data/qwen3_repair_probe.py mirrors r1_decorrelation.py structure
- [ ] Loads N hard bigbar [fail] tasks; default N=4
- [ ] gen_fn = make_r1_gen_fn() (r1_code for qwen3's <think> parsing + max_tokens budget)
- [ ] test_fn wraps _run_nodes_fb on task["redgreen"] (VISIBLE test nodes only)
- [ ] failure_text from visible test only, never from a separate hidden oracle
- [ ] max_retries=2 (cost bound: at most 3 LLM calls per function)
- [ ] Final scoring via _run_nodes (oracle, score-only, never shown to model)
- [ ] Reports cracked X/n vs qwen3-bare 1/4 baseline
- [ ] Gitignored (throwaway probe, not part of the versioned harness)
- [ ] Operator run: R1_MAX_TOKENS=9000 LLAMACPP_TIMEOUT_S=900 python .jaros-data/qwen3_repair_probe.py 4
