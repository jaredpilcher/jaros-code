# Implementation Tasks — EXT-013 Jaros-native behavioral solve + orchestrator

### [TASK-1] Gherkin grain as a Jaros agent

Create the behavior-spec grain as a single-purpose Jaros agent emitting an inert Decision.

#### Steps
1. Add `.jaros-data/agents/gherkin_agent.py` with a `GherkinWriterBoundary.decide(context)` that generates the Given/When/Then spec and returns `create_decision(type="code.write_file", ...)` (no host write).
2. Mirror the `test_writer_agent` Decision pattern (`jaros.core.create_decision`, `source`, `payload={path, content}`).
3. Use the proven EXT-012 gherkin prompt behind the agent boundary.

#### Implements
- [REQ-1] Generation grains are Jaros agents emitting inert Decisions

### [TASK-2] Code grain as a Jaros agent

Create the implementation grain as a Jaros agent emitting a `code.write_file` Decision.

#### Steps
1. Add `.jaros-data/agents/code_agent.py` (or adapt `rewriter_agent`) with `decide(context)` that, given intent + gherkin + feedback, generates the function and returns a `code.write_file` Decision.
2. Pipe the generated code through the parse-gated repair as a Decision/tool (REQ-2), not a direct call.

#### Implements
- [REQ-1] Generation grains are Jaros agents emitting inert Decisions

### [TASK-3] Deterministic ops as Jaros tools through the Runtime

Route every host effect through a validated tool applied by `Runtime.apply`.

#### Steps
1. Use the existing `write_file_tool` for spec/tests/code writes via `code.write_file` Decisions.
2. Run self-tests via a `shell.exec` Decision (existing `shell_exec_tool`) — capture pass/fail + traceback.
3. Expose parse-gated `repair_indentation` as a tool/agent invoked through the Runtime.

#### Implements
- [REQ-2] Deterministic operations are Jaros tools driven through the Runtime

### [TASK-4] Orchestrator judge-agent

The grounded judge that emits the next-action Decision.

#### Steps
1. Add a judge-agent (adapt `orchestrator_agent`) `decide(state)` returning a Decision naming the next action (which proven layer to apply / done), constrained to proven tools.
2. Ground it: mechanical steps deterministic; judgement only at the failure-revision point; bounded budget.

#### Implements
- [REQ-3] The orchestrator is a grounded judge-agent emitting next-action Decisions

### [TASK-5] Runtime-driven solve loop

Drive the end-to-end solve through the Jaros Runtime so it is logged and replayable.

#### Steps
1. Replace the plain-Python loop in `behavioral_solve.py` with a loop of `Runtime.apply(agent.decide(...))` steps (gherkin -> tests -> code -> shell.exec run -> judge -> revise).
2. Confirm a DecisionLog entry per applied Decision and that `jaros replay` reproduces a solve byte-identically.

#### Implements
- [REQ-4] The whole solve is driven through the Jaros Runtime — logged and replayable

### [TASK-6] Eval parity on the held-out 37

Point the eval at the Jaros-native solve and confirm it matches the proven number.

#### Steps
1. Make `commit_replay.attempt_gherkin` (or a new path) invoke the Jaros-native solve.
2. Run the more-itertools held-out 37 and confirm ~6/37 (no regression vs 4/37 baseline), reported with Wilson CI.

#### Implements
- [REQ-5] Preserve the proven held-out number through the migration
