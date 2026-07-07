# Implementation Tasks

### [TASK-1] plan_agent Jaros agent — strategy-first generation

A new single-purpose agent `planner` (`plan_agent.py`), given intent + function name +
module context, has the 2B generate a concise numbered implementation strategy (steps +
edge cases) and emits an inert `code.write_file` Decision — mirroring `gherkin_agent`'s
structure exactly to preserve the two-plane discipline (Tenet 1).

#### Steps
1. Create `.jaros-data/agents/plan_agent.py` (lines 21-77) with `NAME = "planner"` and a
   `build(llm)` factory, structured the same way as `gherkin_agent`.
2. Implement `decide()` to call the 2B with the intent/function-name/module-context and
   return a list containing one `code.write_file` Decision whose `content` is the generated
   strategy text.
3. Respect a `plan_path` key in the incoming context, defaulting to `.jcode/<name>.plan`
   when absent.
4. Strip accidental code fences from the LLM's reply before emitting the Decision.
5. Emit an `advance` Decision (fail path) instead when the LLM returns empty content, so a
   blank strategy never silently proceeds.

#### Implements
- [REQ-1] plan_agent Jaros agent

### [TASK-2] strategy_filter_tool — deterministic execution-plane filter

A new Jaros tool `code.filter_strategy` is pure and deterministic (no LLM call): it strips
few-shot contamination and boilerplate preamble from a generated strategy while keeping
concrete, actionable numbered/bulleted steps and edge-case mentions, with a graceful no-op
fallback when nothing survives filtering.

#### Steps
1. Implement `StrategyFilterTool` in `.jaros-data/tools/strategy_filter_tool.py` (lines
   28-167) with `validate(decision)` rejecting an empty or non-string `payload.strategy`,
   and `execute(decision)` returning `{"tool": "code.filter_strategy", "filtered": str}`.
2. Implement `filter_strategy(text)` as a standalone pure function: strip lines starting
   with `Example:`, `>>>`, and inline `# ` comments; strip fenced multi-line ``` ``` ```
   code blocks; strip known boilerplate-preamble patterns (e.g. "Here is...").
3. Keep numbered steps (`1. ...`) and bulleted steps (`- ...`), and keep lines containing
   edge-case / algorithmic keywords.
4. Fall back to returning the original text unchanged when every line gets stripped
   (graceful no-op), guaranteeing `filter_strategy` is deterministic — the same input always
   produces the same output.

#### Implements
- [REQ-2] strategy_filter_tool deterministic execution-plane tool

### [TASK-3] Wire plan_agent + strategy_filter into behavioral_solve_jaros via plan=False

A `plan: bool = False` keyword argument is added to `behavioral_solve_jaros`. When
`plan=True`, `plan_agent` then `strategy_filter` run before code generation and the
filtered strategy is injected into the code-writer's intent; when `plan=False` (default),
behavior is byte-identical to the pre-EXT-015 path. A mirrored `--plan` CLI flag activates a
new `run_gherkin_jaros_plan` path scored on the hidden oracle.

#### Steps
1. Add a `plan: bool = False` parameter to `behavioral_solve_jaros` in
   `harness/behavioral_solve.py` (lines 253-281), with no change to the pre-existing
   behavior when the flag is left at its default.
2. When `plan=True`, apply the `plan_agent` Decision (TASK-1), run its output through
   `strategy_filter` (TASK-2), and inject the filtered strategy text into the code-writer's
   intent so generation proceeds from the plan.
3. When `plan=False`, never call `plan_agent`, keeping the applied-decisions sequence
   identical to the pre-EXT-015 path.
4. Add `attempt_gherkin_jaros_plan` and `run_gherkin_jaros_plan` functions in
   `harness/commit_replay.py` (lines 1059-1178, 1541-1543, 1566-1573) and a `--plan` flag in
   `commit_replay`'s `__main__`, mirroring the `--augment`/`--jaros` flag wiring, that
   triggers `run_gherkin_jaros_plan`.
5. Ensure no hidden-oracle access occurs anywhere in the plan path — the strategy is derived
   from the visible commit intent only, matching the Gherkin and self-test honesty
   constraints.

#### Implements
- [REQ-3] Wire plan_agent + strategy_filter into behavioral_solve_jaros via plan=False param
