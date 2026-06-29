---
id: EXT-031
title: Strategy-vs-Easier-Tasks Eval Harness
status: covered
priority: high
implementation:
  - file: harness/eval_strategy_easy.py
    ranges:
      - - 1
        - 290
---

### [REQ-1] Core Evaluation Function

`eval_strategy_on_easy(strategy, *, n, bar, solve_fn=None, model=None) -> dict` must run a
chosen strategy's solve over the first n HumanEval (bar="humaneval") or MBPP (bar="mbpp")
tasks and score pass@1 with the SAME honest gate `pass1_eval` uses: write solution.py to an
isolated temp dir, run `task.test_cmd`, check exit-code 0.  The oracle (test_cmd) is the sole
arbiter — score-only, never shown to any strategy during generation.

`solve_fn` must be injectable: when provided, it replaces the registry's callable so offline
tests never touch the Jetson.  An `_tasks` parameter (private, offline-only) allows injecting
a preloaded task list to avoid loading the dataset from disk.

Returns `{strategy, n, passed, pass_rate, wilson95: [lo, hi], per_task: [...]}`.

#### Acceptance Criteria
- [ ] Function accepts strategy name, n, bar, optional solve_fn, optional model, optional _tasks
- [ ] Loads tasks from HumanEval or MBPP dataset when _tasks not provided
- [ ] Scores each task with the honest gate (writes solution.py, runs test_cmd, checks exit 0)
- [ ] Oracle never shown to strategy during code generation (score-only)
- [ ] Returns dict with keys: strategy, n, passed, pass_rate, wilson95, per_task
- [ ] solve_fn=None uses STRATEGY_REGISTRY[strategy]; solve_fn=<fn> overrides for offline tests
- [ ] Unknown strategy name with solve_fn=None raises KeyError (no silent pass)
- [ ] Wilson95 CI computed and included in return value

### [REQ-2] Strategy Registry

A `STRATEGY_REGISTRY` dict maps strategy names to solve callables.  The registry must include
at least three entries:

- `"bare"` — the established baseline: `pass1_eval.solve_gated` (greedy + self-gated
  thinking at temp=0).  Every other strategy is compared against this.
- `"decomposition"` — reuses `decomp_probe._g_plan` + `_g_code_from_plan` (EXT-020).
  For HumanEval/MBPP the stub serves as context; the task instruction as subject.
- `"experiment-to-understand"` — wraps `experiment_solve.experiment_solve` (EXT-030)
  with a task-adapted problem dict, bounded experiments (max=2), and a lightweight
  run_experiment_fn that reads the stub without arbitrary code execution (bounded menu).

Strategies must NOT be reimplemented — they must delegate to the existing EXT-020 and
EXT-030 modules.  All callable imports from those modules must be DEFERRED (no Jetson
connection at import time).  For offline tests the solve_fn parameter overrides the
registry; the registry callables are never invoked in tests.

#### Acceptance Criteria
- [ ] STRATEGY_REGISTRY has "bare", "decomposition", "experiment-to-understand" keys
- [ ] All values are callable
- [ ] "bare" delegates to pass1_eval.solve_gated (not reimplemented)
- [ ] "decomposition" delegates to decomp_probe._g_plan + _g_code_from_plan (not reimplemented)
- [ ] "experiment-to-understand" delegates to experiment_solve.experiment_solve (not reimplemented)
- [ ] All LLM/Jetson imports are deferred inside callables (no connection at import time)
- [ ] For experiment-to-understand: run_experiment_fn is bounded (reads stub, no arbitrary exec)

### [REQ-3] Compare Function and Honest CI Rule

`compare(n, bar) -> dict` must run "bare" vs each strategy on THE SAME n tasks, compute
the delta (`strategy_rate - bare_rate`) and its Wilson95 CI, then print a table.

HONEST CI RULE (non-negotiable): ONLY a delta where the strategy's Wilson95 CI does NOT
overlap with bare's Wilson95 CI counts as a statistically significant lift.  When CIs
overlap, the result MUST be reported as "no significant lift (CI overlap)" — this IS a
valid, informative outcome and must not be treated as a failure.  A prior negative (EXT-009:
retrieval-fewshot 67%->62%) shows non-results are important findings, not accidents.

The function must accept `_tasks` and `_solve_fns` injectable parameters for offline tests
so tests never need the Jetson or real dataset files on disk.

#### Acceptance Criteria
- [ ] compare() runs every registered strategy on the SAME task list
- [ ] Delta (strategy_rate - bare_rate) computed per strategy
- [ ] Wilson95 CI computed for both bare and each strategy
- [ ] CI overlap test determines significance: overlap -> "no significant lift"
- [ ] CI overlap MUST be reported explicitly (not silently dropped or hidden)
- [ ] Printed table shows: strategy, pass_rate, wilson95, delta, lift tag
- [ ] Returns dict with keys: bar, n, bare_rate, results, summary
- [ ] summary entries have: strategy, pass_rate, wilson95, delta, significant_lift, lift_tag
- [ ] _tasks and _solve_fns injectable for offline tests
- [ ] __main__ entry: python -m harness.eval_strategy_easy --n 20 --bar humaneval
- [ ] --strategy flag runs one strategy only; --bar selects humaneval or mbpp
