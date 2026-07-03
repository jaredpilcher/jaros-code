# Implementation Tasks — Multi-Model Routing Harness

### [TASK-1] Model registry + ModelProfile + founding Gemma profile

Build the data layer the whole feature rests on.

#### Steps
1. Create `harness/model_registry.py` with a `ModelProfile` dataclass: `id`, `alias`, `serve` ({gguf, ctx, ngl, fits_jetson}), `classes` (list of {name, bar, score, date}), `adaptation` ({tools, agents, config, prompts}).
2. Implement `ModelRegistry` that loads every `.jaros-data/config/models/*.json` into profiles; expose `lookup_by_id(id)`, `lookup_by_class(class_name) -> [ids]`, and `default_model() -> id`.
3. Write the founding profile `.jaros-data/config/models/gemma-4-e2b.json` — Gemma 4 2B (`e2b`): serve params from the current Jetson serve.sh, `classes` seeded ONLY with classes it has measured evidence for (e.g. standalone-fn-gen on HumanEval/MBPP), `adaptation` = the current default tools/agents/config/prompts.
4. Add `tests/test_model_registry.py`: load the founding profile, lookup by id/class, default_model resolves, and a profile with no evidence for a class is NOT returned by `lookup_by_class`.

#### Implements
- [REQ-1] Model registry with per-model profiles

### [TASK-2] Model-router judge (class → model Decision)

The on-device judge that picks the model.

#### Steps
1. Create `harness/model_router.py` with `route(problem, registry, llm=None) -> Decision` returning inert `{model_id, problem_class, confidence, rationale}` (no side effects).
2. Implement classification: derive cheap deterministic features of the problem (standalone vs repo, has-docstring-examples, multi-file, function-size) + an optional small-LLM class label; map the class to a model via `registry.lookup_by_class`, breaking ties/low-confidence with `registry.default_model()`.
3. Guarantee a routed result always (deterministic default fallback); attach `confidence` + `rationale`.
4. Add `tests/test_model_router.py` with a fake LLM + stub registry: a class covered only by model B routes to B; an unknown/low-confidence class routes to the default; the return is inert data.

#### Implements
- [REQ-2] Model-router judge (class → model Decision)

### [TASK-3] Deterministic rewire + guarded Jetson swap

Make the harness actually become the chosen model.

#### Steps
1. Create `harness/model_rewire.py` with `rewire(model_id, registry) -> result` that resolves the profile, checks the currently-served model, and only swaps when different (idempotent).
2. Implement the guarded Jetson swap: update the llama.cpp serve params (`-m`/`--alias`) for the target and restart `gemma.service`, via a constrained helper that cannot run an arbitrary command (Tenet 1) and never escalates off-device (Tenet 2); a swap failure returns an honest error (Tenet 3).
3. After (or without) a swap, point the active LLM client at the model's alias and activate its `adaptation` set (the active tools/agents/config/prompts).
4. Add `tests/test_model_rewire.py`: re-rewiring to the already-served model is a no-op (no swap call); rewiring to a different model invokes the swap helper (mocked); a mocked swap failure surfaces honestly.

#### Implements
- [REQ-3] Deterministic rewire to the selected model

### [TASK-4] Per-model profiling / roster exploration loop

Earn the profiles by measurement; grow the roster best-first.

#### Steps
1. Create `harness/model_profiler.py` with `profile_model(model_id, classes, registry)` that serves the model, runs each held-out class eval, and appends only cleared classes (with bar/score/date evidence) to the profile JSON.
2. Define the roster order (best-first, Jetson-fitting only) in `.jaros-data/config/models/_roster.json` and a `fits_jetson` admission check (~8 GB budget).
3. Document the candidate Jetson-fitting models to explore best-first (e.g. a strong coding 3B that fits, down to Gemma 2B) in `.jarify/EXT-021/design.md` appendix; profile at least one non-Gemma candidate honestly.
4. Add `tests/test_model_profiler.py` (offline, stub evals): a class clearing the bar is written with evidence; a class below the bar is NOT added (honest).

#### Implements
- [REQ-4] Per-model profiling / roster exploration loop

### [TASK-5] End-to-end wiring: route → rewire → solve, two classes / two models

Prove the whole loop and wire it into the solve entry point.

#### Steps
1. Add a `solve_routed(problem)` entry (in `harness/model_router.py` or the existing solve entry) that calls `route` → `rewire` → the existing behavioral/orchestrator solve using the active model's adaptation.
2. Route the standalone-fn-gen class to the Gemma profile and a hard repo class to a stronger profiled model; demonstrate both end-to-end (logged Decisions + rewire records).
3. Ensure the whole path runs native on Jaros (inert routing Decision → gate → clerk rewire → hash-chain log → replay) and is honest (the profile evidence gates which model owns which class).
4. Add `tests/test_solve_routed.py` (offline): two problems of two classes route+rewire to two different models and invoke the corresponding adaptation (mocked solve).

#### Implements
- [REQ-2] Model-router judge (class → model Decision)
- [REQ-3] Deterministic rewire to the selected model
- [REQ-4] Per-model profiling / roster exploration loop

### [TASK-25] Migrate routing layer to Jaros-native Runtime (TASK-25)

Make the multi-model routing layer Jaros-native: routing decisions and rewire
side effects flow through Runtime.apply (gate -> executor -> DecisionLog) exactly
like the core behavioral solve, so they are hash-chain logged and replayable.

#### Steps
1. Create `harness/_rewire_config.py` — stable singleton for injectable state
   (registry, swap_fn, serving_state, activate_fn) shared between solve_routed_native
   and ModelRewireTool across the importlib dynamic-loading boundary.
2. Create `.jaros-data/tools/model_route_tool.py` — Jaros tool (NAME="model.route")
   that lets the inert routing Decision flow through Runtime.apply: validate() checks
   model_id + problem_class + confidence; execute() returns the routing info (no side
   effects — this tool is a pass-through logger for the hash chain).
3. Create `.jaros-data/tools/model_rewire_tool.py` — Jaros tool (NAME="model.rewire")
   with validate() (checks model_id resolves in registry + fits_jetson=True, Tenet 1/2)
   and execute() (calls harness.model_rewire.rewire() via injected state from
   harness._rewire_config). Keep existing rewire() as the implementation called by execute().
4. Add `route_native(problem, registry, runtime, *, tally, record)` to
   `harness/model_router.py`: calls route() for the inert dict, wraps it as a Jaros
   Decision (type="model.route"), applies through Runtime.apply, returns the dict.
5. Add `solve_routed_native(problem, registry, *, runtime, solve_fn, swap_fn,
   serving_state, activate_fn)` to `harness/solve_routed.py`: route_native() ->
   Runtime.apply(model.rewire Decision) -> solve_fn, all on ONE Runtime
   (shared DecisionLog, hash-chain logged, replayable). Keep existing solve_routed()
   for back-compat.
6. Create `tests/test_jaros_native_routing.py` (OFFLINE, no live Jetson): 20 tests
   covering route_native logged Decision, ModelRewireTool.validate() rejects (unknown
   id + off-device), execute() mocked swap, and solve_routed_native full flow with
   DecisionLog replayability.

#### Implements
- [REQ-2] Model-router judge (class → model Decision)
- [REQ-3] Deterministic rewire to the selected model

### [TASK-26] Admit Qwen2.5-Coder-7B as measured complex-build specialist

Admit Qwen2.5-Coder-7B to the roster catalog + registry, honestly, with exactly the ONE class it
has earned held-out evidence for. Owner greenlit "proceed with 7B if it fits" (it fits the Jetson at
ctx=4096: 5.3GB used / 2.0GB free, no OOM, ~7 tok/s). A matched head-to-head of gemma-4-e2b vs
Qwen2.5-Coder-7B on 3 complex sentence-to-system BUILD tasks (`harness/system_builder.build_system`,
measured 2026-07-03) found: jobqueue — gemma ships 0/2 runs (fails the py_compile/build gate), 7B
ships 2/2 runs (reproducible positive decorrelation); kvstore — both ship; pipeline — both ship
(gemma reaches done=True, 7B done=False). Totals: gemma 2/3 shipped / 1 fully done; 7B 3/3 shipped /
0 fully done — a real but NARROW marginal coverage win at ~3x latency + 2x RAM, never fully
completing. This task ALSO fixes a real bug the measurement surfaced: the model-manager's
`READY_TIMEOUT_S` default (120s) was too short for a 7B load and left `_current` desynced.

**FOLLOW-UP, explicitly OUT of scope for this task:** wiring actual `build_system` routing to
consult the new `complex-system-build-specialist` class (needs a separate build_system-routing
analysis/task) — this task is admission + catalog + profile + the timeout bug fix only.

#### Steps
1. `scripts/jetson_model_manager.py`: raise the default `READY_TIMEOUT_S` from `"120"` to `"300"` —
   a 7B load exceeds 120s and desyncs `_current` (real bug, measured 2026-07-03).
2. `scripts/jetson_models.json`: add a `"qwen2.5-coder-7b"` catalog entry (gguf path, alias, ctx
   4096, ngl 99, `extra_args: ["--threads","4"]`), with a `_note` recording the fit + admission
   evidence, mirroring the existing entries' style.
3. `.jaros-data/config/models/qwen2.5-coder-7b.json`: new `ModelProfile` mirroring
   `qwen2.5-coder-3b.json` / `deepseek-r1-distill-qwen-7b.json` — `serve` (gguf, ctx 4096, ngl 99,
   `fits_jetson: true`), `adaptation.prompts = "qwen-instruct-direct"`, `classes` holding EXACTLY
   ONE earned class (`complex-system-build-specialist`) with the jobqueue head-to-head bar/score,
   date 2026-07-03, and an explicit honest caveat (narrow — 1 of 3 sentences; 7B never reaches
   done=True; ~3x latency + 2x RAM; routed specialist only, not a default). No invented classes
   (Tenet 3).
4. `docs/GAP-MAP.md`: record the measured admission (numbers + caveats) under the 7B roster-lever
   section.

#### Implements
- [REQ-4] Per-model profiling / roster exploration loop
