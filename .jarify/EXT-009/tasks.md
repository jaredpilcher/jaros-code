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
