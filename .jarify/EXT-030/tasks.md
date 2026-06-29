# Implementation Tasks

### [TASK-1] Implement the experiment_solve core loop, bounded executor, Jetson factory, probe, and spec

The complete EXT-030 implementation: the injectable core loop, the three bounded
experiment runners (E1/E2/E3), the Jetson factory for propose_fn/solve_fn, the
active-hours probe, offline tests, and the spec folder.

#### Steps
1. Write `harness/experiment_solve.py` with:
   - `experiment_solve(problem, *, propose_fn, run_experiment_fn, solve_fn, test_fn, max_experiments=3) -> dict` — fully injectable core loop; accumulates `{experiment, observation}` in `understanding`; calls `solve_fn` after all experiments; `test_fn` is the sole arbiter.
   - `_make_experiment_runner(repo, task, targets, orig)` — factory returning `run_experiment_fn`; dispatches to `_e1_run_failing_tests`, `_e2_call_function`, `_e3_read_function_source`.
   - `_e1_run_failing_tests(repo, task)` — runs red test nodes via `_run_nodes_fb` in Docker; returns captured traceback.
   - `_e2_call_function(repo, targets, orig, fn_name, args_repr)` — validates `args_repr` with `ast.literal_eval`; calls function in subprocess; returns `repr(result)` or exception text; restores orig files.
   - `_e3_read_function_source(orig, fn_name)` — extracts function source via AST from `orig` dict; pure, no I/O.
   - `_parse_experiment_decision(raw, fn_name)` — defensive JSON parser for model output; fallback to E1.
   - `_make_jetson_fns(model, manager_url, *, swap_fn=None, llm_fn=None) -> (propose_fn, solve_fn)` — injectable factory; `propose_fn` builds bounded-menu prompt + parses decision; `solve_fn` builds understanding-informed prompt + applies indentation repair.
   - `run_experiment_probe(n=6)` — active-hours probe: loads n hard [fail] tasks, runs experiment_solve per task (qwen, max_experiments=3), scores with `_run_nodes` oracle, restores gemma, prints honest X/n summary.
   - `__main__` with `--n` argument.
2. Write `tests/test_experiment_solve.py` — all offline, all mocked:
   - (a) loop runs exactly max_experiments then calls solve_fn once.
   - (b) understanding accumulates in order; propose_fn sees growing scratchpad.
   - (c) test_fn sole arbiter: test_fn=False -> solved=False.
   - (d) experiment that raises -> captured as observation; loop continues.
   - (e) solve_fn receives full accumulated understanding.
   - Plus: syntax smoke (f), import smoke (g), solved T/F (h/i), max=0 (j), list length (k).
3. Create `.jarify/EXT-030/` with `requirements.md`, `design.md`, `tasks.md`, `index.json`.
4. Wrap the core loop and bounded executor in `# #EXT-030-REQ-1 Start/End`; wrap factory and probe in `# #EXT-030-REQ-2 Start/End`.
5. Run `python -m pytest tests/ -q` — full suite green, no regressions; run `python -m py_compile harness/experiment_solve.py` and `ast.parse` check.
6. Commit with footer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

#### Implements
- [REQ-1] Experiment -> observe -> understand -> solve loop
- [REQ-2] Deferred active-hours probe protocol
