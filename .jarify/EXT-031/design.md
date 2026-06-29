# EXT-031 Design: Strategy-vs-Easier-Tasks Eval Harness

## Motivation

The 6 solve strategies were built and evaluated ONLY on the hard bigbar class (all returned 0/N).
Their effect on EASIER tasks (HumanEval/MBPP) is UNTESTED.  A scaffold is a MULTIPLIER — on
easier tasks the base model HAS capability to amplify, so a lift is PLAUSIBLE.  But a non-result
is equally plausible (retrieval-fewshot was a prior negative at -5%).  This harness measures that.

## Architecture

```text
  eval_strategy_easy.py
  ┌───────────────────────────────────────────────────────────────────────────┐
  │                                                                           │
  │  eval_strategy_on_easy(strategy, n, bar, solve_fn=None) -> dict          │
  │  ┌─────────────────────────────────────────────────────┐                 │
  │  │  1. Load tasks: humaneval._read_problems() or mbpp   │                 │
  │  │  2. For each task:                                   │                 │
  │  │     solve_fn(task) -> code       ← model plane       │                 │
  │  │     _score_task(task, code)      ← execution plane   │                 │
  │  │       setup_task() + write solution.py               │                 │
  │  │       _run_with_treekill(test_cmd) -> bool           │                 │
  │  │  3. Aggregate: passed, pass_rate, wilson95           │                 │
  │  └─────────────────────────────────────────────────────┘                 │
  │                                                                           │
  │  STRATEGY_REGISTRY: name -> (task -> code)                               │
  │  ┌────────────────┐  ┌───────────────────┐  ┌─────────────────────────┐  │
  │  │ bare           │  │ decomposition     │  │ experiment-to-understand │  │
  │  │ pass1_eval     │  │ decomp_probe      │  │ experiment_solve         │  │
  │  │ .solve_gated() │  │ _g_plan +         │  │ .experiment_solve()      │  │
  │  │ (greedy+think) │  │ _g_code_from_plan │  │ (explore->observe->fix)  │  │
  │  └────────────────┘  └───────────────────┘  └─────────────────────────┘  │
  │                                                                           │
  │  compare(n, bar) -> dict                                                 │
  │  ┌─────────────────────────────────────────────────────────────────┐     │
  │  │  Load tasks ONCE; feed THE SAME task list to all strategies     │     │
  │  │  bare result -> bare_rate, bare_wilson95                        │     │
  │  │  for each non-bare strategy:                                    │     │
  │  │    result -> rate, wilson95                                     │     │
  │  │    delta = rate - bare_rate                                     │     │
  │  │    overlap = _ci_overlap(bare_wilson95, strategy_wilson95)      │     │
  │  │    if overlap: "no significant lift (CI overlap)"    ← HONEST   │     │
  │  │    else if delta > 0: "LIFT *"                                  │     │
  │  │    else: "NEGATIVE *"                                           │     │
  │  └─────────────────────────────────────────────────────────────────┘     │
  └───────────────────────────────────────────────────────────────────────────┘
```

## Two-Plane Discipline (Tenet 1)

Every strategy follows the same boundary:
- Model plane: the strategy callable emits code (string) — a pure data Decision.
- Execution plane: `_score_task()` runs the test_cmd deterministically.  The oracle result is
  NEVER fed back to the strategy during generation (score-only).

For "experiment-to-understand": the `run_experiment_fn` is bounded — it only reads the task
stub (pure data, no arbitrary code execution).  `propose_fn` emits an inert Decision dict;
`run_experiment_fn` executes the bounded read.

## Scoring Gate (Honest — Tenet 3)

Identical to `pass1_eval`:
1. `setup_task(task, tmpdir)` — materialise all task support files.
2. Write `solution.py` with the strategy's code.
3. `_run_with_treekill(task.test_cmd, tmpdir, timeout=60)` — exit-code 0 = PASS.

The hidden test (task.test_cmd) is the sole arbiter.  No visible-test gating affects the score.

## Honest CI Rule

Wilson95 CI is mandatory.  A strategy is only declared to show a "significant lift" if its CI
does NOT overlap with the bare CI.  With small n (e.g. n=20), CIs are wide and overlap is
common.  "No significant lift" is printed explicitly — never silently dropped.  This mirrors
the retrieval-fewshot finding (EXT-009) where the result was -5% and was reported honestly.

## Active-Hours Command

```
python -m harness.eval_strategy_easy --n 20 --bar humaneval
python -m harness.eval_strategy_easy --n 20 --bar mbpp
python -m harness.eval_strategy_easy --strategy decomposition --n 10 --bar humaneval
```

The full `compare()` run on n=20 HumanEval tasks makes ~60 LLM calls (3 strategies × 20 tasks);
each HumanEval task is simpler than a bigbar task so latency should be lower than the hard probes.

## MEASURED RESULT #1 (2026-06-29) — easy HumanEval is at the BARE CEILING; hard-task scaffolds HURT here
Ran bare vs decomposition vs experiment-to-understand on n=12 HumanEval (gemma, honest Wilson95 CI, 0 errors):
- **bare = 1.000** (12/12) — gemma aces this easy slice; there is NO headroom for a multiplier to lift.
- decomposition = 0.083 (1/12, delta -0.917) · experiment-to-understand = 0.167 (2/12, delta -0.833) — NET-NEGATIVE.
HONEST INTERPRETATION (genuine, not a wiring crash — strategies produced real but wrong code):
1. This slice CANNOT test "do scaffolds lift easier tasks" — bare is at 100% (ceiling). It refutes the earlier UNVERIFIED assumption "scaffolds lift easier classes" *at least where bare is already maxed*.
2. The scaffolds are net-NEGATIVE on easy synthesis: decomposition over-engineers a trivial function; experiment-to-understand is CATEGORY-MISMATCHED (a REPAIR scaffold — runs the failing test / calls the existing fn — applied to FROM-SCRATCH synthesis, so its probes are noise). Mis-applying a hard-task scaffold to easy synthesis HURTS, it isn't merely neutral.
3. LESSON (vindicates routing): scaffolds are CLASS-SPECIFIC multipliers — apply the right scaffold to the right class. The harness's bare/light default for easy synthesis is correct; do NOT wire heavy/repair scaffolds onto it.
CAVEAT: n=12, and the informative test needs a slice WITH headroom. Follow-up: MBPP (gemma ~25% bare = lots of room) with the synthesis-appropriate scaffold (decomposition), to see if a scaffold lifts where the base is weak. Wired NOTHING from this run (the "winner" for easy synthesis is bare).
