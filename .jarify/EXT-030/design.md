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
