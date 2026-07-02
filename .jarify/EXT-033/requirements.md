---
id: EXT-033
title: Routed-Eval Capstone -- System-Level Multi-Model Lift
status: covered
priority: high
implementation:
  - file: harness/eval_routed.py
    ranges:
      - - 1
        - 330
  - file: tests/test_eval_routed.py
    ranges:
      - - 1
        - 310
---

### [REQ-1] Routed vs single-model comparison with honest Wilson95 CI and per-task routing

Implement the end-to-end capstone evaluation that validates the PRIME-001 multi-model claim:
routing each problem to its measured-best model (via the deterministic router + tally) beats
running everything on the default single model (gemma-4-e2b).

Three functions compose the capstone:
- `eval_routed(n, bar, registry, *, route_fn=None, solve_fn=None) -> dict` — for the first
  n tasks of a benchmark (humaneval/mbpp), deterministically route each task (route() -> class
  -> best model via tally), solve with the routed model's adaptation, score pass@1 with the
  honest gate (task.test_cmd exit-code). Returns `{n, bar, routed_passed, routed_rate,
  wilson95, per_task: [{task_id, routed_model, problem_class, passed}]}`.
- `eval_single(n, bar, model, *, solve_fn=None) -> dict` — baseline: same n tasks, all solved
  by one fixed model (default gemma-4-e2b via solve_gated). Returns `{n, bar, model, passed,
  pass_rate, wilson95, per_task}`.
- `compare_routed_vs_single(n, bar, ...) -> dict` — runs both on the SAME task list, computes
  the delta and Wilson95 CI per the EXT-031/eval_strategy_easy convention, prints a comparison
  table + per-task routing table. `significant_lift=True` only when the delta falls OUTSIDE the
  CI overlap of both intervals (honest: within-CI = "no significant lift" — valid outcome).

All three accept injectable `route_fn`/`solve_fn`/`_tasks` for OFFLINE tests (no Jetson needed).

The per-task routing table shows WHICH model each task was routed to, demonstrating that the
routing is actually happening (not a black-box number).

#### Acceptance Criteria
- [x] `eval_routed(n, bar, registry, *, route_fn=None, solve_fn=None) -> dict` implemented with correct return shape.
- [x] `eval_single(n, bar, model, *, solve_fn=None) -> dict` implemented as the single-model baseline.
- [x] `compare_routed_vs_single(n, bar, ...) -> dict` implemented with Wilson95 CI table + per-task routing table printed.
- [x] `significant_lift=True` ONLY when delta is outside CI overlap; within-CI = "no (CI overlap)" reported plainly (Tenet 3).
- [x] All three functions accept injectable `route_fn`, `solve_fn`, `_tasks` for offline testing (no Jetson calls in tests).
- [x] Offline test suite (tests/test_eval_routed.py) with >= 15 tests covering: routing records, honest gate scoring, routed_rate > single_rate on stub, CI overlap -> no-lift, CI separation -> significant-lift, all required result dict keys.
- [x] Full pytest suite green after adding tests (no regressions).

### [REQ-2] Deferred active-hours run protocol (operator-invoked)

The `__main__` block provides the operator-invoked live run:
    python -m harness.eval_routed --n 20 --bar humaneval

On the live Jetson run (gemma + qwen2.5-coder-3b both available), HumanEval tasks with `>>>`
in their docstrings are classified as `standalone-fn-gen` by the deterministic router and
routed to qwen2.5-coder-3b (92% HumanEval measured vs gemma's 82%). The expected lift is
~+10 pp, but honest CI reporting: n=20 gives wide Wilson95 intervals; n>=30 for separation.

The gemma service is restored after the run:
    python -m harness.model_rewire gemma-4-e2b

The qwen3-4b-thinking hard-class escalation path (EXT-021 REQ-6) is explicitly excluded from
this default run (it is slow); this capstone focuses on the tractable synthesis-class routing.

#### Acceptance Criteria
- [x] `__main__` block implements `--n`, `--bar`, `--single-model` CLI arguments.
- [x] The run command `python -m harness.eval_routed --n 20 --bar humaneval` is documented in the module docstring and `__main__` help text.
- [x] "Restore gemma after" instruction documented in both the module docstring and `__main__` help text.
- [x] qwen3-4b-thinking excluded from default run with explanation (separate validated path).
- [x] Module imports are fully lazy (no Jetson/LLM call at import time — verified by import smoke test).

### [REQ-7] CLI auto-restores the default model after a routed eval (no dangling non-default serve)

The `python -m harness.eval_routed` CLI runs `compare_routed_vs_single`, which rewires the Jetson to
routed models (qwen2.5-coder, qwen3-thinking, etc.) during the eval — but it NEVER restores the registry
default (gemma-4-e2b) afterward. The docstring merely TELLS the operator to run
`python -m harness.model_rewire gemma-4-e2b` manually. So the CLI leaves a non-default model serving,
which (per the roster notes) desyncs the model-manager and starves RAM for the next default-model work.
This is a real operational bug (repeatedly hit). The deterministic plane must restore the default itself.

#### Acceptance Criteria
- [x] A small helper `harness/eval_routed.py::_restore_default_model(registry)` rewires the Jetson back to
      `registry.default_model()` (the gemma default), swallowing/logging any rewire error (best-effort; never
      raises — a restore failure must not mask the eval result). Tag `# #EXT-033-REQ-7`.
- [x] The CLI `__main__` block wraps the `compare_routed_vs_single(...)` call in `try/finally` and calls
      `_restore_default_model(_registry)` in the `finally`, so the default model is ALWAYS restored after a
      routed eval (success or exception). No behavior change to `compare_routed_vs_single`/`eval_routed`
      themselves (offline tests that inject solve_fns and never rewire are unaffected).
- [x] Offline unit test (`tests/`, NO Jetson): `_restore_default_model` with a fake registry (whose
      `default_model()` returns "gemma-4-e2b") and a monkeypatched `rewire` asserts `rewire` was called with
      `"gemma-4-e2b"`; and a variant where `rewire` raises confirms `_restore_default_model` does NOT propagate.
      Full suite stays green.
