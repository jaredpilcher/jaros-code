# EXT-033 Tasks

## TASK-1 — Implement harness/eval_routed.py

**Status**: Completed

#### Implements
- REQ-1 (eval_routed, eval_single, compare_routed_vs_single with honest CI)
- REQ-2 (__main__ active-hours run protocol)

#### Steps
1. Write `eval_routed(n, bar, registry, *, route_fn=None, solve_fn=None, _tasks=None) -> dict`.
   - Build problem_dict from task stub (source/prompt keys).
   - Call `route_fn(problem_dict, registry)` to get decision (default: `model_router.route`).
   - Call `solve_fn(task, decision)` to get code (default: `_make_live_solve_fn(registry)`).
   - Score with `_score_task` (honest pass@1 gate — same as pass1_eval).
   - Return `{n, bar, routed_passed, routed_rate, wilson95, per_task}`.
2. Write `eval_single(n, bar, model, *, solve_fn=None, _tasks=None) -> dict`.
   - Default solve: `pass1_eval.solve_gated` (gemma, temp=0, deterministic).
   - Score with `_score_task`.
   - Return `{n, bar, model, passed, pass_rate, wilson95, per_task}`.
3. Write `compare_routed_vs_single(n, bar, ...) -> dict`.
   - Run both on the SAME task list.
   - Compute delta + Wilson95 CI (same `_wilson95`/`_ci_overlap` formulas as EXT-031).
   - Print comparison table + per-task routing table.
   - `significant_lift=True` only when delta outside CI overlap.
4. Write `_make_live_solve_fn(registry)` factory for the live path.
5. Write `_wilson95`, `_ci_overlap`, `_score_task`, `_load_tasks`, `_problem_dict_for_task` helpers.
6. Write `__main__` block with `--n`, `--bar`, `--single-model` args.
   - Document active-hours run command and gemma restore procedure.
7. Add `# #EXT-033-REQ-1 Start/End` and `# #EXT-033-REQ-2 Start/End` tags.

---

## TASK-2 — Implement tests/test_eval_routed.py

**Status**: Completed

#### Implements
- REQ-1 (offline test coverage)

#### Steps
1. Build `_StubTask` and `_make_tasks` helpers (same pattern as test_eval_strategy_easy).
2. Build `_stub_registry()` with model-gemma (82%) and model-qwen (92%) profiles.
3. Build `_always_qwen_route` and `_always_gemma_route` stub route_fns.
4. Write test (a): routing records routed_model per task in per_task.
5. Write test (b): routed_rate > single_rate when qwen's mock solve beats gemma's.
6. Write test (c): CI overlap -> "no (CI overlap)" at small n=3.
7. Write test (d): honest gate scores pass@1 correctly (real test_cmd executed).
8. Write test (e): syntax smoke (ast.parse).
9. Write test (f): import smoke (no Jetson at import time).
10. Write test (g): eval_routed result dict has all required keys.
11. Write test (h): compare result has per_task_routing with routed_model per task.
12. Write test (i): eval_single result dict has all required keys.
13. Write test (j): significant_lift=True when CI separates (large n mock).
14. Write Wilson95/CI_overlap pure-math tests.
15. Verify full test suite green.

---

## TASK-3 — Create .jarify/EXT-033/ spec files

**Status**: Completed

#### Implements
- REQ-1, REQ-2 (spec coverage)

#### Steps
1. Create `.jarify/EXT-033/requirements.md` with REQ-1 and REQ-2.
2. Create `.jarify/EXT-033/design.md` with ASCII flow diagrams.
3. Create `.jarify/EXT-033/tasks.md` (this file).
4. Create `.jarify/EXT-033/index.json` with traceability links.
