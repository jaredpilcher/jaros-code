# Implementation Tasks

### [TASK-1] Core evaluation function

`eval_strategy_on_easy(strategy, *, n, bar, solve_fn=None, model=None) -> dict` runs a
chosen strategy's solve over the first n HumanEval or MBPP tasks and scores pass@1 with the
same honest gate `pass1_eval` uses, with `solve_fn` and `_tasks` injectable so offline tests
never touch the Jetson or the dataset on disk.

#### Steps
1. Implement `eval_strategy_on_easy` in `harness/eval_strategy_easy.py` (lines 103-176),
   accepting a strategy name, `n`, `bar` (`"humaneval"` or `"mbpp"`), and optional
   `solve_fn`, `model`, and `_tasks` parameters.
2. Load tasks from the HumanEval or MBPP dataset per `bar` when `_tasks` is not supplied.
3. Score each task with the honest gate `pass1_eval` uses: write `solution.py` to an
   isolated temp dir, run `task.test_cmd`, and check for exit code 0 — the oracle is the
   sole arbiter and is never shown to the strategy during generation.
4. Return `{strategy, n, passed, pass_rate, wilson95: [lo, hi], per_task: [...]}`.
5. Resolve the solve callable from `STRATEGY_REGISTRY[strategy]` when `solve_fn` is `None`,
   override it with the supplied `solve_fn` when provided (for offline tests), and raise
   `KeyError` for an unknown strategy name with no `solve_fn` override (no silent pass).

#### Implements
- [REQ-1] Core Evaluation Function

### [TASK-2] Strategy registry

`STRATEGY_REGISTRY` maps strategy names to solve callables that delegate to existing
EXT-020/EXT-030 modules rather than reimplementing them, with all Jetson-dependent imports
deferred so importing the registry module never opens a connection.

#### Steps
1. Define `STRATEGY_REGISTRY` in `harness/eval_strategy_easy.py` (lines 180-308) with keys
   `"bare"`, `"decomposition"`, and `"experiment-to-understand"`, each mapped to a callable.
2. Implement `"bare"` as a thin wrapper delegating to `pass1_eval.solve_gated` (greedy +
   self-gated thinking at temp=0), the established baseline every other strategy is compared
   against.
3. Implement `"decomposition"` as a thin wrapper delegating to `decomp_probe._g_plan` +
   `_g_code_from_plan` (EXT-020), using the HumanEval/MBPP stub as context and the task
   instruction as subject.
4. Implement `"experiment-to-understand"` as a thin wrapper delegating to
   `experiment_solve.experiment_solve` (EXT-030) with a task-adapted problem dict, bounded
   experiments (max=2), and a lightweight `run_experiment_fn` that reads the stub without
   arbitrary code execution.
5. Defer every LLM/Jetson-touching import inside the wrapper callables (not at module import
   time), so `import harness.eval_strategy_easy` never opens a Jetson connection, and ensure
   offline tests always go through the `solve_fn` override rather than invoking the registry
   callables.

#### Implements
- [REQ-2] Strategy Registry

### [TASK-3] Compare function and honest CI rule

`compare(n, bar) -> dict` runs `"bare"` against every registered strategy on the same n
tasks, computes each strategy's delta and Wilson95 CI against bare, and applies the
non-negotiable CI-overlap rule: only a delta whose CI does not overlap bare's counts as a
significant lift, with overlap explicitly reported as "no significant lift" rather than
hidden or treated as failure.

#### Steps
1. Implement `compare(n, bar)` in `harness/eval_strategy_easy.py` (lines 312-436) to run
   `eval_strategy_on_easy` for `"bare"` and every other registered strategy on the identical
   task list (accepting injectable `_tasks` and `_solve_fns` for offline tests).
2. Compute the delta (`strategy_rate - bare_rate`) and the Wilson95 CI for both `bare` and
   each strategy.
3. Apply the CI-overlap significance rule: a strategy's CI not overlapping bare's CI is
   tagged as a significant lift; an overlapping CI is explicitly tagged and reported as "no
   significant lift (CI overlap)", never silently dropped.
4. Print a table (strategy, pass_rate, wilson95, delta, lift tag) and return
   `{bar, n, bare_rate, results, summary}`, where each `summary` entry has `{strategy,
   pass_rate, wilson95, delta, significant_lift, lift_tag}`.
5. Wire a `__main__` entry (`python -m harness.eval_strategy_easy --n 20 --bar humaneval`)
   with a `--strategy` flag to run a single strategy and a `--bar` flag to select
   `humaneval` or `mbpp`.

#### Implements
- [REQ-3] Compare Function and Honest CI Rule
