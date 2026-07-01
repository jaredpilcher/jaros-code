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

### [TASK-7] Orchestrator WHERE-to-act: grounded locate agent + resolver tool

Give the orchestrator the first design-axis variable — decide WHERE to act — as a single-purpose,
grounded Jaros agent, reusing the proven SWE-bench localization primitive. Pure/offline-testable; no
network, no Jetson needed for the unit tests (inject the model via a callable).

#### Steps
1. Add `.jaros-data/agents/locate_agent.py` with a `LocateBoundary.decide(context)` where `context` carries the solve intent + a list of candidate targets `[{file, function, anchor_line}]`. It builds a grounded prompt that NUMBERS the candidates and asks the local 3B for the SINGLE index whose function the intent refers to, then returns an inert `orchestrate.locate` Decision (`create_decision(type="orchestrate.locate", payload={file, function, anchor_line})`) for the chosen candidate. No host effect.
2. Degeneracy-guard: parse the model reply for a single candidate index; if it drifts / abstains / returns out-of-range, fall back deterministically to the candidate whose `anchor_line` best content-matches the intent (never a no-op, never free-text).
3. Add a deterministic resolver: a small function/tool that, given the chosen candidate's file text + `anchor_line`, reuses `harness/swebench_live.py::locate_region` (content-match) to return the concrete `(start, end)` line range — do NOT write a fresh ad-hoc scan.
4. Add `tests/test_ext013_locate.py` (offline, inject a canned model callable): (a) the agent returns an `orchestrate.locate` Decision naming the correct candidate for a synthetic intent+candidate set; (b) the degeneracy-guard falls back to the content-match candidate when the model reply is garbage; (c) the resolver reuses `locate_region` and returns the right `(start,end)`. Run the full suite green.

#### Implements
- [REQ-6] Orchestrator variable — decide WHERE to act (localization)

### [TASK-8] Orchestrator richer-observe: the judge reasons over the actual code

Enrich ``OrchestratorJudgeBoundary`` (the REQ-3 judge) so it observes the ACTUAL current code (and
optionally the gherkin spec), distinguishing a LOGIC bug (-> code) from BROKEN SYNTAX (-> repair) by
SEEING the artifact, not only the failure text.  STRICTLY BACKWARD-COMPATIBLE — zero regression to the
proven solve: the enrichment is OPT-IN; when the richer fields are absent the existing prompt and
behavior are byte-for-byte unchanged.

#### Steps
1. In ``.jaros-data/agents/orchestrator_judge_agent.py::OrchestratorJudgeBoundary.decide``, read
   ``code = str(ctx.get("code", ""))`` (and ``spec = str(ctx.get("spec", ""))``).  When ``code`` is
   non-empty, build the prompt from a RICHER template that includes the current code (truncate to a
   safe budget, e.g. 800 chars) before the "Diagnose the cause" line; when it is empty, use the
   EXISTING ``_PROMPT`` unchanged (backward-compat).
2. Do NOT change the action space, the degeneracy-guard (first recognised token -> default), or the
   deterministic step-budget guard — only the OBSERVATION is richer.  Tag the new code
   ``# #EXT-013-REQ-8`` for traceability (this is a REQ-8 enrichment of the REQ-3 agent).
3. Add offline tests in ``tests/test_ext013_orchestrator_judge.py`` (canned llm; capture the prompt via
   a stub that records the request): (a) with ``ctx["code"]`` the code text appears in the prompt;
   (b) WITHOUT code the prompt equals the existing one (backward-compat); (c) action-selection +
   step-budget behavior is unchanged.  Run the full suite green.

#### Implements
- [REQ-8] Orchestrator variable — richer observe loop
