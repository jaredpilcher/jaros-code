---
id: EXT-015
title: Plan-then-code decomposition (strategy-first generation)
status: covered
priority: high
implementation:
  - file: .jaros-data/agents/plan_agent.py
    ranges:
      - - 21
        - 77
  - file: .jaros-data/tools/strategy_filter_tool.py
    ranges:
      - - 28
        - 167
  - file: harness/behavioral_solve.py
    ranges:
      - - 247
        - 275
  - file: harness/commit_replay.py
    ranges:
      - - 982
        - 1101
  - file: tests/test_plan_then_code.py
    ranges:
      - - 22
        - 622
---

# EXT-015 — Plan-then-code decomposition (strategy-first generation)

Research basis: 'Strategic Decomposition & Filtering for SLMs' — a 1.5B model lifted +30%
relative by FIRST generating a natural-language IMPLEMENTATION STRATEGY (decompose into steps
+ edge cases), THEN a DETERMINISTIC pattern-based FILTER cleaning it (filtering > diversity;
small models can't improve their own scaffold, so the filter MUST be deterministic = two-plane),
THEN coding FROM the filtered plan.

This mechanism is additive and opt-in (`plan=True` / `--plan`); the default behavior of every
existing path is byte-identical.  It is HONEST: no hidden-oracle access; the strategy is
derived from visible commit intent only, same constraint as Gherkin and self-tests.

### [REQ-1] plan_agent Jaros agent

A new single-purpose agent `planner` (`plan_agent.py`) that, given intent + function name +
module context, has the 2B generate a CONCISE numbered implementation strategy (steps + edge
cases), and emits an inert `code.write_file` Decision.  Mirrors `gherkin_agent` exactly in
structure (Tenet 1 / two-plane).

#### Acceptance Criteria
- [ ] `.jaros-data/agents/plan_agent.py` exists with `NAME = "planner"` and `build(llm)`
- [ ] `decide()` returns a list with one `code.write_file` Decision whose `content` is the strategy
- [ ] Respects `plan_path` key in context; defaults to `.jcode/<name>.plan`
- [ ] Strips accidental code fences from the LLM reply
- [ ] Emits an `advance` Decision (fail path) when the LLM returns empty content

### [REQ-2] strategy_filter_tool deterministic execution-plane tool

A new Jaros tool `code.filter_strategy` (`strategy_filter_tool.py`) that is PURE and
DETERMINISTIC (no LLM).  Strips few-shot contamination (lines like 'Example:', fenced code
blocks, copied I/O), strips preamble/boilerplate ('Here is...', etc.), KEEPS concrete
actionable lines (numbered/bulleted imperative steps + edge-case mentions).  Validates that
payload.strategy is a non-empty string.  Graceful no-op: returns original if nothing survives.

#### Acceptance Criteria
- [ ] `StrategyFilterTool` class with `validate(decision)` and `execute(decision)` methods
- [ ] `filter_strategy(text)` is a standalone pure function (no LLM, deterministic)
- [ ] Strips lines starting with 'Example:', `>>>`, and inline `# ` comments
- [ ] Strips fenced code blocks (multi-line ```` ``` ````)
- [ ] Strips boilerplate preamble matching known patterns ('Here is...', etc.)
- [ ] Keeps numbered steps (`1. ...`) and bulleted steps (`- ...`)
- [ ] Keeps lines containing edge-case / algorithmic keywords
- [ ] `validate()` rejects empty/non-str payload.strategy
- [ ] `execute()` returns `{"tool": "code.filter_strategy", "filtered": str}`
- [ ] `filter_strategy` is deterministic (same input → same output always)
- [ ] Graceful no-op: returns original text when all lines are stripped

### [REQ-3] Wire plan_agent + strategy_filter into behavioral_solve_jaros via plan=False param

Add a `plan: bool = False` keyword argument to `behavioral_solve_jaros`.  When `plan=True`,
run `plan_agent` -> `strategy_filter` BEFORE code generation and include the filtered strategy
in the code-writer's intent so it generates FROM the plan.  When `plan=False` (default),
behavior is byte-identical to the pre-EXT-015 path.  Add a `--plan` flag to `commit_replay.py`
(mirrors `--augment`/`--jaros`) that activates `run_gherkin_jaros_plan` (new function scored on
the hidden oracle).

#### Acceptance Criteria
- [ ] `behavioral_solve_jaros` accepts `plan: bool = False` with no default-behavior change
- [ ] When `plan=True`: plan_agent Decision is applied, filtered strategy injected into code intent
- [ ] When `plan=False`: plan_agent is never called; applied_decisions unchanged vs pre-EXT-015
- [ ] `attempt_gherkin_jaros_plan` and `run_gherkin_jaros_plan` functions exist in commit_replay
- [ ] `--plan` flag in commit_replay `__main__` triggers `run_gherkin_jaros_plan`
- [ ] HONEST: no hidden-oracle access at any point; strategy from visible intent only
- [ ] Measurement command: `python -m harness.commit_replay <repo> --gherkin-loop --jaros --plan --n 37`
