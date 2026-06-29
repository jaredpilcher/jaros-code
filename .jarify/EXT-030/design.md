# EXT-030: Experiment-to-Understand Agentic Solve — Design

## Overview

This spec introduces an agentic experiment -> observe -> understand -> solve loop
for hard repo-level tasks.  The key insight from studying strong coding agents
(Claude Code, SWE-agent, OpenHands): they do not one-shot generate a fix.  They
EXPLORE the codebase first — run tests, call functions with known inputs, read
helper sources — and THEN write the fix informed by what they actually observed.

EXT-030 brings this pattern to jaros-code within the two-plane discipline:
the model PICKS experiments (judgement); the execution plane RUNS them
(deterministic tools); the oracle JUDGES the final code (test_fn only).

## Architecture

```text
                    ┌─────────────────────────────────────────────────────┐
                    │            experiment_solve (core loop)              │
                    │                                                      │
   problem ────────►│  for i in range(max_experiments):                   │
                    │    decision = propose_fn(problem, understanding)     │
                    │    #  ↑ MODEL picks experiment (inert Decision)      │
                    │                                                      │
                    │    observation = run_experiment_fn(problem, decision)│
                    │    #  ↑ EXEC PLANE runs bounded experiment           │
                    │    #    errors caught → "experiment error: …"        │
                    │                                                      │
                    │    understanding.append({decision, observation})     │
                    │                                                      │
                    │  code = solve_fn(problem, understanding)             │
                    │  #  ↑ MODEL writes fix informed by observations      │
                    │                                                      │
                    │  result = test_fn(problem, code)                     │
                    │  #  ↑ ORACLE — the ONLY arbiter of solved            │
                    │  #    Oracle answer NEVER shown to model             │
                    │                                                      │
                    │  return {solved, code, experiments, understanding}   │
                    └─────────────────────────────────────────────────────┘

                          Two-Plane Boundary
                    ─────────────────────────────
        MODEL PLANE │                   │ EXECUTION PLANE
                    │                   │
        propose_fn  │                   │  _make_experiment_runner
         (picks     │                   │   E1: _run_nodes_fb (Docker)
          E1/E2/E3) │                   │   E2: subprocess + ast.literal_eval
                    │                   │   E3: AST source extraction
        solve_fn    │                   │
         (writes    │                   │  test_fn
          the fix)  │                   │   (_run_nodes oracle, score-only)
```

## Bounded Experiment Menu (E1 / E2 / E3)

```text
┌──────┬──────────────────────────────────────────────────────────────────┐
│ Type │ What the execution plane does                                    │
├──────┼──────────────────────────────────────────────────────────────────┤
│ E1   │ Run the failing red test nodes in Docker (_run_nodes_fb).        │
│      │ Returns the short traceback so the model sees WHY it fails.      │
│      │ params: {}  (no model input required)                            │
├──────┼──────────────────────────────────────────────────────────────────┤
│ E2   │ Call the target function with specific literal inputs.            │
│      │ args_repr validated by ast.literal_eval (safe literals only).    │
│      │ Runs in a subprocess with timeout.  Returns repr(result) or      │
│      │ exception text.  Files restored to orig state after.             │
│      │ params: {fn_name: str, args_repr: str}                           │
├──────┼──────────────────────────────────────────────────────────────────┤
│ E3   │ Read the source of a named helper/related function via AST.      │
│      │ Pure — no LLM, no network, no I/O beyond reading orig dict.      │
│      │ params: {fn_name: str}                                           │
└──────┴──────────────────────────────────────────────────────────────────┘
```

## Component Map

```text
harness/experiment_solve.py
│
├── experiment_solve()          — core injectable loop (all-mocked in tests)
│
├── _make_experiment_runner()   — factory: returns run_experiment_fn for a task
│   ├── _e1_run_failing_tests() — E1: Docker _run_nodes_fb + capture traceback
│   ├── _e2_call_function()     — E2: subprocess + ast.literal_eval safety gate
│   └── _e3_read_function_source() — E3: AST source extraction from orig dict
│
├── _parse_experiment_decision() — defensive JSON parser for propose_fn output
│
├── _make_jetson_fns()          — factory: (propose_fn, solve_fn) for Jetson
│   ├── propose_fn()            — prompts model to pick E1/E2/E3, parses JSON
│   └── solve_fn()              — prompts model to write fix given understanding
│
└── run_experiment_probe()      — active-hours probe (n hard [fail] tasks)

tests/test_experiment_solve.py
│
└── Offline tests with all-injectable mocks (no Jetson, no Docker, no git)
    (a) max_experiments calls → then solve  (b) understanding order
    (c) test_fn sole arbiter                (d) error captured, loop continues
    (e) solve sees full understanding       (f/g) syntax + import smoke
    (h/i) solved T/F from test_fn          (j) max=0  (k) list length
```

## Batching and Model Swap Design

The production probe uses the same batching principle as collaborative_solve
(EXT-029): the solver model is swapped ONCE at the start, used for ALL propose
and solve calls, then swapped back.  Total swaps = 2 (load solver + restore
gemma), independent of n.

## Connections to Other Specs

- EXT-029 (collaborative_solve): experiment loop is the NEXT lever after
  collaboration returned 0/6.  _http_swap is reused from collaborative_solve.
- EXT-028 (dependency_structure): E3 uses AST; the same analysis can extend
  to method_dependencies for callee discovery.
- EXT-024 / issue #24 (working memory): the understanding scratchpad is a
  form of working memory — bounded, task-scoped, fed progressively.
- EXT-011 (commit_replay): _run_nodes_fb, _apply_func, oracle infrastructure
  all reused.

## HARD-CLASS SYNTHESIS (2026-06-29) — experiment-to-understand = 0/6; SIX distinct approaches now all 0
EXT-030 experiment-to-understand (qwen proposes bounded E1/E2/E3 -> observes -> accumulates understanding -> solves, max_experiments=3, oracle sole test-gate): **0/6** on the hard bigbar [fail] tasks. The loop RAN correctly (6 probed, exps=3 each; the NameError was caught + fixed first, not a false 0).
This is the **SIXTH** distinct, independent solving approach to return 0 on this hard multi-step-repo class:
  1. pass@k sampling (best-of-N, temp): 0/7
  2. deterministic decomposition: 0/8
  3. maximal-help (context + worked example + plan): 0
  4. decorrelated reasoner (R1-Distill-1.5B, the fitting one): 0/6
  5. cross-model collaboration (qwen draft -> gemma critique -> qwen revise): 0/6
  6. experiment-to-understand (agentic run-observe-understand-then-solve): 0/6
HONEST VERDICT: the weight of evidence across SIX diverse mechanisms strongly favors a genuine ROOT-CAPABILITY wall for the current Jetson-fitting roster (gemma-4-e2b 2B + qwen2.5-coder-3b) on this class — NOT a thin-solve/harness gap. The owner's collaboration/richer-solve hypotheses (2026-06-29) were worth testing + were tested rigorously; the data says combining/sampling/decomposing/exploring does not supply a capability the models lack at the root. The tasks are REAL more-itertools feature commits (new algorithms: interleave_randomly, multidimensional reshape, random derangements) — a high bar for 2-3B models from a commit subject + failing test.
CAVEAT (honest): each mechanism could be deepened (#33 team-discussion untested); but no single thin implementation explains all SIX independent 0s. Consistent with the multi-model pivot's REVISED principle: per-roster/device ceilings are MEASURED honestly (Tenet 3); system-level no-ceiling means GROW THE ROSTER — but fitting models don't reach it (R1-7B that might doesn't fit the 7.3GB device; R1-1.5B too weak).
BANKED + REAL: the multi-model harness (complete) + the qwen breadth win (92% HE/65% MBPP vs gemma 82%/25%, routed per-class) + SIX general mechanisms (registry/router/rewire/tally/test-gate, memory, dependency-structure, collaboration, experiment-loop) that lift the EASIER/MEDIUM classes. The hard class is the ONE mapped ceiling.
DECISION (auto-steer): STEP BACK from grinding the hard class (6 zeros = diminishing returns on a 7th obvious attempt). PIVOT to BANKING + HARDENING the wins (routed solve_routed eval on the 101-bar showing the per-class floor rose). The hard class needs a hardware upgrade or a genuinely novel mechanism — an OWNER strategic call, surfaced not auto-pursued. #33 + #32 remain available but lower-probability.
