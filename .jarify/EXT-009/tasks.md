# Implementation Tasks

### [TASK-1] Route the master loop through the specialist agent swarm

Broaden `execute_step` beyond find/read/run/fix so the loop WIELDS the full set of Jaros
specialist agents (the owner's swarm). A file-edit step dispatches to the right specialist by
file type; a build step dispatches to the generative spine.

#### Steps
1. Add an `edit` action to `execute_step` in `harness/agent_loop.py` that maps the target file to a specialist agent — `.md` -> `markdown_editor_agent.py`, `Dockerfile` -> `dockerfile_editor_agent.py`, `.yaml/.yml/.ini/.cfg/.toml` -> `config_editor_agent.py`, else `editor_agent.py` — loads it via `_load_agent`, and applies its `code.write_file` Decision through a `Runtime` (two-plane).
2. Add a `build` action that dispatches to `harness.intent_loop.build_in_dir`.
3. Extend `_KNOWN` and the planner's verb vocabulary to include `edit` and `build`.
4. Add deterministic tests in `tests/test_agent_loop.py`: an `edit` step routes a `.md` file to the markdown specialist (planner injected; assert the right agent fires and the file changes).

#### Implements
- [REQ-1] Master loop: plan -> act -> observe -> replan

### [TASK-2] Multi-step agentic eval (SWE-bench-like, local)

The honest metric for the agentic layer — HumanEval (single-function) cannot measure planning.

#### Steps
1. Create `harness/agentic_eval.py` with >=3 multi-step scenarios: each seeds a small repo with a fault (exception or logic bug across >=2 files) and a high-level NL request.
2. Run each scenario end-to-end through `agent_loop`; score solved iff the loop drives `pytest` to green within the step budget.
3. Append each run to `history.jsonl` with `suite="agentic"` so `/trend` tracks agentic progress separately from pass@1.
4. Add a CI wrapper `tests/test_agentic_eval.py` that asserts loop mechanics on one scripted scenario (no model) for regression protection.

#### Implements
- [REQ-6] Multi-step eval: measure the agentic capability

### [TASK-3] Working-memory scratchpad fed into replanning

#### Steps
1. In `agent_loop`, accumulate a compact scratchpad of completed steps' `(action, arg, observation)`.
2. Pass the scratchpad into the planner on every replan (and the initial plan when long-term memory exists).
3. Print the live TODO as it runs under `verbose`.

#### Implements
- [REQ-2] Working memory (short-term): the live TODO

### [TASK-4] Long-term project memory (.jcode/memory.md)

#### Steps
1. At the start of `agent_loop`, read `.jcode/memory.md` from `cwd` (graceful no-op if absent) and prepend it to the planner's context.
2. On a notable outcome, append a dated learning line to `.jcode/memory.md` through a `code.write_file` Decision (never silent I/O).

#### Implements
- [REQ-3] Long-term memory: the harness reads/writes its own project memory

### [TASK-5] Context compaction for long loops

#### Steps
1. Before each planner call, bound its input: keep the request + the TODO + the last N observations verbatim and drop/summarize older observations deterministically.

#### Implements
- [REQ-5] Context compaction for long loops

### [TASK-6] Plan mode, /agent-as-default, and whole-run checkpoint

#### Steps
1. Add a dry-run that renders the TODO without executing (`/agent --plan`), naming the gating test for each fix/build phase.
2. In `cli.handle`, route a multi-action plain request to `agent_loop` instead of single-action orchestration.
3. Snapshot the repo (`_snapshot`) before the run and add `/undo` to `_restore` it.

#### Implements
- [REQ-4] Plan mode: show the plan before acting
- [REQ-7] `/agent` as the default NL entry; checkpoint the whole run

### [TASK-7] Requirements-decomposition BUILD flow (the richer jarify-flow)

The spec-driven loop beat the free-form loop 3/3 vs 2/3 on FIX scenarios. Extend its BUILD flow
from single-function to MULTI-requirement: decompose an intent into several checkable requirements,
write a test per requirement, implement against all, verify — where structured decomposition
should pull further ahead of free-form on a 2B.

#### Steps
1. Add `_decompose(intent)` in `harness/spec_loop.py`: one constrained model call that returns a list of `(func_name, behavior)` requirements (parse `name: behavior` lines; keep valid identifiers).
2. Replace the single-function BUILD branch with: stub each `func_name` in `<module>.py`, call the `test_writer` agent per requirement to write `test_<func>.py`, then `fix_loop` the module against all tests, then verify pytest green.
3. Keep the single-function path as the fallback when `_decompose` yields one requirement.

#### Implements
- [REQ-3] Working memory / structured decomposition (requirements as the checkable artifact)

### [TASK-8] Multi-requirement BUILD eval (measure decomposition's advantage)

#### Steps
1. Create `harness/build_eval.py`: >=3 multi-function build intents (e.g. a calculator with add/subtract/multiply), each with a HIDDEN ORACLE test exercising ALL functions (reuse the EXT-008 oracle pattern).
2. Score `spec_driven_loop` (decomposition BUILD flow) vs the free-form `agent_loop` on each; record `suite="build"` to history.
3. CI wrapper test asserting scenarios are well-formed (model-free).

#### Implements
- [REQ-6] Multi-step eval: measure the agentic capability (build variant)

### [TASK-9] Per-function build to close the list-aggregation gap (build eval 5/7 -> 7/7)

DIAGNOSED: the build eval's only failures (listops, minmax) are LIST-AGGREGATION functions
(`largest(xs)`, `maximum(xs)` — max/min/sum over a list passed as one arg). Root cause: the
multi-function build stubs with `*args` so fix_loop routes to the WHOLE-FILE rewriter, which KEEPS
`*args` and implements `max(args)` (wrong for `largest([1,5,2])`). Concrete-signature stubs route
to the single-function BODY-COMPLETER, which implements correctly but can't do multi-function (the
0/3 regression). So neither single regime handles multi-function + correct signatures.

#### Steps
1. In `_decompose_build`, for the multi-requirement case, build EACH function in ISOLATION: a temp module with the CONCRETE stub `def name(params): raise NotImplementedError` + its test, run `fix_loop` (concrete signature -> body-completer implements correctly, including list-aggregation).
2. Extract each implemented function from its isolated build and concatenate them into `solution.py`.
3. Verify the combined suite (all per-function tests) goes green.
4. Eval-gate against `build_eval` (must reach >5/7, no regression) BEFORE commit+push.

#### Implements
- [REQ-6] Multi-step eval: measure the agentic capability (push the build rate past list-aggregation)

### [TASK-10] Hybrid build: *args fallback when a per-function build fails (recover boolchecks -> 7/7)

DIAGNOSED (build eval, 2 runs + dogfool, 3/3 obs): TASK-9's per-function build fixed list-aggregation
SYSTEMATICALLY but CONSISTENTLY fails boolchecks — the body-completer botches `is_odd`'s indentation
in isolation, where the *args whole-file rewriter built it fine. Net +1 (5/7->6/7), a real trade.

#### Steps
1. In `_build_per_function`, after combining `solution.py`, detect any function still a stub (its body raises `NotImplementedError`) — i.e. its per-function build failed.
2. If >=1 function failed, RETRY the whole scenario via the existing `*args` whole-file build path (which builds those functions, e.g. is_odd, correctly) and keep whichever solution.py has more functions implemented / passes more tests.
3. Eval-gate against `build_eval` (target 7/7, NO regression on the list-aggregation cases) BEFORE commit+push.

#### Implements
- [REQ-6] Multi-step eval: measure the agentic capability (close the boolchecks trade)
