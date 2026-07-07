# Implementation Tasks

### [TASK-1] Gated-thinking in behavioral_solve_jaros

When `think=True`, after the first direct code generation in `behavioral_solve_jaros`, the
target function's visible docstring examples are parsed from `current_src`; if examples
exist and the generated code fails them, the code is regenerated exactly once using a
`<think>` reasoning prompt (`_g_code_think`). If no examples exist, or the direct result
already passes them, the direct result is kept. When `think=False` (the default), the path
is byte-identical to the pre-existing behavior. The hidden red→green oracle is never read
during solve — only the visible docstring examples gate when to think.

#### Steps
1. Add a `think: bool = False` keyword argument to `behavioral_solve_jaros` in
   `harness/behavioral_solve.py` (lines 300-314).
2. After the first direct code generation, when `think=True`, parse the target function's
   visible docstring examples from `current_src` using `_doctest_asserts` (from
   `pass1_eval`).
3. When examples exist and the generated code fails them (`_visible_ok == False`), call
   `_g_code_think` (defined in `harness/commit_replay.py`, lines 372-403) exactly once to
   regenerate using a `<think>` reasoning prompt, producing valid Python or an empty string.
4. When the generated code already passes the visible examples, or when no examples exist
   in the docstring, skip `_g_code_think` entirely and keep the direct result.
5. When `think=False`, run no think logic at all, so the default path stays byte-identical
   to the pre-EXT-018 behavior.

#### Implements
- [REQ-1] Gated-thinking in behavioral_solve_jaros

### [TASK-2] --think CLI flag for the commit-replay evaluator

An opt-in `--think` flag activates the gated-thinking path for all gherkin-loop + jaros
runs, in both the single-repo and multi-repo (`--bar big`) CLI paths, mirroring the
existing `--retrieve` and `--jaros` flag wiring; when absent, the default path is
unchanged.

#### Steps
1. Recognize `--think` in `commit_replay`'s `__main__` for both the single-repo
   (`--gherkin-loop --jaros`) and multi-repo (`--bar big --gherkin-loop --jaros`) CLI paths
   (`harness/commit_replay.py`, lines 738-740, 749-756, 1424-1426, 1437-1444, 1515-1522,
   1547-1549, 1576-1582).
2. Thread a `think: bool = False` parameter down through `attempt_gherkin_jaros`,
   `run_gherkin_jaros`, and `run_gherkin_jaros_multi` to `behavioral_solve_jaros`.
3. Include a `+think` tag in the result banner when `--think` is active, mirroring the
   existing `+retrieve` tag.
4. Verify `python -m harness.commit_replay --bar big --gherkin-loop --jaros --think` runs
   without error.

#### Implements
- [REQ-2] --think CLI flag for the commit-replay evaluator
