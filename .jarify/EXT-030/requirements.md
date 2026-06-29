---
id: EXT-030
title: Experiment-to-Understand Agentic Solve
status: covered
priority: high
implementation:
  - file: harness/experiment_solve.py
    ranges:
      - - 57
        - 354
      - - 358
        - 772
  - file: tests/test_experiment_solve.py
    ranges:
      - - 1
        - 433
---

Experiment-to-understand agentic solve loop — changes the SOLVE PROCESS rather
than the model combination.  The insight: strong coding agents (Claude Code,
SWE-agent) crack hard repo tasks by EXPLORING and OBSERVING before writing
the fix.  This module brings that pattern to jaros-code as a principled
experiment -> observe -> understand -> solve loop with a bounded, safe
experiment menu.

Connection to EXT-029 (collaborative-solve): collaboration returned 0/6 on the
hard multi-step-repo class.  That approach changed WHO writes the code (two
models), not whether the solver UNDERSTANDS the problem first.  EXT-030 changes
the SOLVE PROCESS — explore, observe, then fix.

Connection to EXT-028 (dependency-structure): E3 experiment reuses AST analysis
for related-function lookup.

Connection to EXT-024 / issue #24 (working memory): the understanding scratchpad
IS lightweight working memory — accumulated observations guide the final solve.

### [REQ-1] Experiment -> observe -> understand -> solve loop

`harness/experiment_solve.py` exposes `experiment_solve(problem, *, propose_fn,
run_experiment_fn, solve_fn, test_fn, max_experiments=3) -> dict` — the core
loop, all callables INJECTABLE for offline testability.

Loop semantics:
- Loop up to `max_experiments`:
  - `propose_fn(problem, understanding) -> dict` — model picks next experiment
    from the bounded menu; returns an inert Decision dict
    `{"type": "E1"|"E2"|"E3", "params": {...}}`. NEVER executes anything.
  - `run_experiment_fn(problem, decision) -> str` — execution plane runs the
    bounded experiment; returns an observation string.  Errors are caught and
    captured as observations (loop continues defensively).
  - Append `{"experiment": decision, "observation": str}` to `understanding`.
- `solve_fn(problem, understanding) -> str` — model writes the fix INFORMED by
  all accumulated observations.
- `test_fn(problem, code) -> {"passed": bool}` — deterministic oracle gate.
- Return `{solved, code, experiments, understanding}`.

TWO-PLANE DISCIPLINE (Tenet 1): propose_fn emits inert Decisions; the
execution plane (run_experiment_fn) runs bounded experiments only.
The SAFE BOUNDED MENU — no arbitrary code execution:
  E1: RUN the failing test nodes + capture real traceback/stdout.
  E2: CALL the target function with specific literal inputs (ast.literal_eval
      guarded) + capture return value or exception (subprocess, timeout).
  E3: READ the source of a named helper/related function (AST only).

HONEST: `test_fn` is the SOLE arbiter of `solved`. The oracle answer is NEVER
shown to `propose_fn` or `solve_fn`. Experiments build understanding only.

`_make_experiment_runner(repo, task, targets, orig)` — the DETERMINISTIC
bounded-experiment executor for a real repo task; returns `run_experiment_fn`.

#### Acceptance Criteria
- [ ] `experiment_solve` importable from `harness.experiment_solve`
- [ ] propose_fn and run_experiment_fn each called exactly `max_experiments` times
- [ ] understanding accumulates `{experiment, observation}` entries in order
- [ ] propose_fn receives the growing understanding scratchpad at each step
- [ ] solve_fn receives the full accumulated understanding after all experiments
- [ ] test_fn is the sole arbiter: test_fn=False -> solved=False regardless of
      what solve_fn produced
- [ ] An experiment that raises is captured as an observation; loop continues
- [ ] max_experiments=0: solve immediately with empty understanding
- [ ] experiments list in result has exactly max_experiments entries

### [REQ-2] Deferred active-hours probe protocol

`_make_jetson_fns(model, manager_url, *, swap_fn=None, llm_fn=None) ->
tuple[Callable, Callable]` — factory returning `(propose_fn, solve_fn)` backed
by the served model.  Both are injectable (offline tests pass no-ops).
The factory mirrors collaborative_solve's `_make_jetson_fns` batching pattern:
model is ALREADY LOADED when each fn is called; swapping is the caller's job.

`run_experiment_probe(n=6)` — loads n hard bigbar [fail] tasks, runs
experiment_solve per task (qwen2.5-coder-3b as proposer+solver,
max_experiments=3), scores with the `_run_nodes` oracle, restores gemma-4-e2b
after, reports cracked X/n vs the 0/6 collaborative-solve baseline.

Active-hours invocation:
    python -m harness.experiment_solve --n 6

#### Acceptance Criteria
- [ ] `_make_jetson_fns` importable and callable with injectable `swap_fn`/`llm_fn`
- [ ] Returns a 2-tuple `(propose_fn, solve_fn)` — both offline-injectable
- [ ] `run_experiment_probe` is documented as active-hours only; no live Jetson
      call from automated tests
- [ ] Module `__main__` entry accepts `--n` argument
- [ ] Active-hours probe reports honest X/n summary vs collab-solve 0/6 baseline
