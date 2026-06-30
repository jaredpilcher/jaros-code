# EXT-033 Design: Routed-Eval Capstone

## Purpose

The routed-eval capstone is the end-to-end validation of the multi-model harness's
core claim (PRIME-001): routing each problem to its measured-best Jetson-fitting model
delivers a higher pass@1 than running everything on the default single model.

We have measured the COMPONENTS separately (qwen2.5-coder-3b: 92% HumanEval / 65% MBPP
vs gemma-4-e2b: 82% HumanEval / 25% MBPP) but this eval measures the END-TO-END system:
does the router + solve actually deliver best-per-class results?

## Architecture

```text
                    EXT-033 Routed-Eval Capstone
                    ==============================

  ROUTED PATH (eval_routed)
  ──────────────────────────────────────────────────────────────────────
  [Benchmark task t]
       |
       v
  _problem_dict_for_task(t)         -- extract stub source, instruction
       |
       v
  route_fn(problem_dict, registry)  -- deterministic classifier (EXT-021 REQ-2)
       |                               features: has_examples(>>>) -> standalone-fn-gen
       v                               tally argmax -> qwen2.5-coder-3b (score=92%)
  decision{model_id, problem_class}
       |
       v
  solve_fn(task, decision)          -- model's adaptation code-gen (EXT-021 REQ-3)
       |                               rewire to model, code_gen_for(adaptation) -> code
       v
  _score_task(task, code)           -- honest pass@1 gate (same as pass1_eval)
       |                               setup_task -> solution.py -> test_cmd -> exit-code
       v
  per_task{task_id, routed_model, problem_class, passed}


  SINGLE-MODEL BASELINE (eval_single)
  ──────────────────────────────────────────────────────────────────────
  [Benchmark task t]
       |
       v
  solve_fn(task)                    -- default: solve_gated (gemma, temp=0)
       |
       v
  _score_task(task, code)           -- same honest gate
       |
       v
  per_task{task_id, model, passed}


  COMPARISON (compare_routed_vs_single)
  ──────────────────────────────────────────────────────────────────────
  eval_single(n, bar, gemma)   -> single_rate  +  Wilson95 [s_lo, s_hi]
  eval_routed(n, bar, registry)-> routed_rate  +  Wilson95 [r_lo, r_hi]
                                                          |
                                                          v
                                  delta = routed_rate - single_rate
                                  overlap = _ci_overlap(s_lo,s_hi, r_lo,r_hi)
                                  significant_lift = (not overlap) and delta > 0
                                          |
                                          v
                           Printed table + per-task routing table


  HONEST CI RULE (EXT-031 / eval_strategy_easy convention)
  ──────────────────────────────────────────────────────────────────────
  "lift?" = "yes (CI separates)"    only when delta outside CI overlap
  "lift?" = "no (CI overlap)"       when CIs share any point (valid, not a failure)
  n >= 30 needed for narrow CIs; n=20 gives wide CIs (stated, Tenet 3)
```

## Injectable Interfaces

All three functions accept injectable callables for OFFLINE testing:

```text
  route_fn(problem_dict, registry) -> decision_dict
      Default: harness.model_router.route (deterministic classifier)
      Injected: stub returning fixed {model_id, problem_class, ...}

  solve_fn(task, decision) -> str              [eval_routed]
      Default: _make_live_solve_fn(registry)   (requires Jetson: rewire + code_gen)
      Injected: mock returning correct/wrong code

  solve_fn(task) -> str                        [eval_single]
      Default: pass1_eval.solve_gated          (requires Jetson: gemma gated)
      Injected: mock returning correct/wrong code

  _tasks: list
      Default: loaded from disk (HumanEval.jsonl / mbpp.jsonl)
      Injected: in-memory _StubTask objects (offline tests)
```

## Live Run Data Flow

For the operator-invoked run (`python -m harness.eval_routed --n 20 --bar humaneval`):

```text
  HumanEval tasks
  (stub source has ">>>" in docstrings)
       |
       | route() deterministic feature extraction:
       |   has_examples=True (>>>) -> standalone-fn-gen
       |   tally argmax: qwen2.5-coder-3b (score=92%) > gemma (score=82%)
       v
  decision{model_id="qwen2.5-coder-3b", problem_class="standalone-fn-gen"}
       |
       | rewire(qwen2.5-coder-3b, registry)  -- swap on Jetson if needed
       v
  qwen_adapt.qwen_code(instruction, fn_name, stub_context)
       |
       v
  _score_task -> test_cmd exit-code  -- honest pass@1

  After run: python -m harness.model_rewire gemma-4-e2b  (restore)
```

## Relationship to Other Specs

| Spec     | Role in EXT-033                                              |
|----------|--------------------------------------------------------------|
| EXT-021  | Provides route(), CoverageTally, ModelRegistry, rewire()    |
| EXT-031  | Wilson95 CI convention; _ci_overlap; honest reporting style  |
| pass1_eval | solve_gated (baseline), _run_with_treekill (honest gate)  |
| PRIME-001 | Multi-model claim this capstone validates end-to-end        |

## Test Strategy

Offline tests mock both the routing and solve sides:
- `route_fn` = `_always_qwen_route` (deterministic stub)
- `solve_fn` = lambda returning correct or wrong code
- `_tasks` = in-memory `_StubTask` objects with real pytest tests
- The HONEST GATE (`_score_task`) IS executed with real temp dirs — verifying
  it actually runs test_cmd and checks exit-code (not mocked)

## RUN #1 (2026-06-29) — INVALID (harness bug caught); NOT a routing-negative
First live run (n=20 HumanEval): single-gemma=1.000 (easy slice, ceiling), routed=0.400 => delta -0.600 "NEGATIVE". This is a HARNESS BUG, NOT a real result (sanity: qwen alone is 92% on HumanEval, so routed-via-qwen scoring 40% is absurd). ROOT CAUSE: qwen_code slices from `def` and DROPS the HumanEval stub's import preamble (e.g. `from typing import List`); harness/profile_qwen.py `_real_humaneval_eval` (the honest 92% measurement) COMPENSATES by prepending the stub preamble before scoring, but eval_routed does NOT — so typed solutions fail to import -> false 40%. The gemma path (solve_gated) assembles correctly (100%), exposing the asymmetry. The 92% qwen claim STANDS (correct HumanEval assembly = stub-preamble + completion, standard methodology; and in real production qwen adds functions to files that already have the imports). FIX: eval_routed must assemble the testable program uniformly (prepend the stub preamble/prompt to the generated function for ALL model adaptations, mirroring _real_humaneval_eval). Also: the first-20 HumanEval slice is at gemma's CEILING (100%) so it cannot show a routing lift regardless — the informative bar is MBPP (gemma 25% vs qwen 65%, real headroom). Re-run on MBPP after the fix. NO routing-negative is recorded; this run is discarded as a measurement-harness defect (honest measurement, Tenet 3).
