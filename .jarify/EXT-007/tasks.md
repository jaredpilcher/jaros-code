# Implementation Tasks — Self-Improvement Backlog (toward Opus-4.8 parity)

## Honest findings (kept truthful — what is / isn't working)

- **2026-06-19: pass rate was FLAT at ~67% all session** (6/9 → 12/18), despite
  rewriter, deterministic inference, syntax guard, feedback, temp escalation,
  telemetry, wiring, and growing evals 9→24. Adding evals/plumbing tightened
  measurement but did NOT improve capability.
- **Diagnosed root cause:** retry budget too small. With `max_iters=2`, round 1 is
  frequently wasted on a format/syntax error (e.g. a markdown fence or dropped
  quote), leaving only one real attempt. Live debug: `count_vowels` FAILED at
  max_iters=2 but PASSED at max_iters=3 (round 1 syntax error → round 2 correct).
- **Fix under test:** raise the runner's default `max_iters` 2→3. MEASURE the next
  full-suite heartbeat; if pass rate does not rise, this hypothesis is wrong — say so
  and try the next lever (real decomposition: a planner/test-reflection agent).
- **2026-06-19 RESULT (honest WIN, measured):** max_iters 2→3 moved the full-suite
  pass rate from **12/18=67% → 20/24=83%** (+16pts, on a HARDER 24-task suite, CI
  40→29pts). The diagnosis was correct: round-1 format/syntax errors needed recovery
  room. This is real capability improvement, not plumbing. Next lever: split broad
  agents into specialists (REQ-6) and crack the remaining frontier fails.


The supervisor advances one task per cycle (frontier-first), appends new tasks as
failures/ideas surface, and keeps the census trending up with quality.

### [TASK-1] Deterministic syntax guard for broken edits

Catch a broken `.py` edit immediately and feed the exact SyntaxError back.

#### Steps
1. Add `py.check` tool (compile-based) in `.jaros-data/tools/py_check_tool.py`.
2. Add `python_syntax_error` + a post-edit guard in `harness/coding_loop.py`.

#### Implements
- [REQ-3] Frontier-driven prioritization (greet_format class of failures)

### [TASK-2] Grow the authored suite to 20+ tasks (tighten the CI)

Add diverse, harder tasks across tiers so the Wilson CI narrows (more accurate).

#### Steps
1. Add 6+ new `evals/coding_tasks/*.json` across tiers 1–3 (strings, dicts, recursion, classes).
2. Confirm the report's CI width shrinks as N grows.

#### Implements
- [REQ-2] Net growth with quality

### [TASK-3] Crack binary_search (loop-boundary reasoning)

#### Steps
1. Add a single-purpose `hint` agent or sharpen the rewriter prompt for boundary bugs.
2. Verify the eval flips binary_search to PASS without regressing others.

#### Implements
- [REQ-3] Frontier-driven prioritization

### [TASK-4] Crack roman_numerals (algorithmic decomposition)

#### Steps
1. Add an example-driven or decomposition strategy for from-scratch algorithm tasks.
2. Verify roman_numerals reaches PASS.

#### Implements
- [REQ-3] Frontier-driven prioritization

### [TASK-5] Wire a HumanEval subset into the continuous runner

Make the external benchmark part of the always-on measurement.

#### Steps
1. Have `run_forever.py` also run a small HumanEval subset when the dataset is present.
2. Record it in the trend labelled `humaneval`.

#### Implements
- [REQ-2] Net growth with quality

### [TASK-6] Router agent: choose editor vs rewriter by file size

A tiny single-purpose router so surgical edits are used on large files.

#### Steps
1. Add `router_agent.py` emitting a choice; wire the loop to honor it.

#### Implements
- [REQ-2] Net growth with quality

### [TASK-8] Wire agents to use tools (and safety-gate generated code)

Agents must use the deterministic tools when they need information, and the
generated code must itself be safe. This is an ongoing, growing responsibility.

#### Steps
1. Safety-gate generated code in code.write_file / code.apply_patch (DONE — EXT-001/REQ-11).
2. Wire py.symbols output into the rewriter's context (DONE).
3. Grow wiring: feed fs.grep/fs.read/fs.find context to agents for multi-file tasks;
   add a navigator agent that emits fs.find/fs.grep to locate code; have agents
   recommend which tool to use next. Add tests for each wiring.

#### Implements
- [REQ-2] Net growth with quality

### [TASK-9] Split into specialized agents + a router (wire everything)

Decompose the broad agents into specialists by language/domain and dispatch to them.

#### Steps
1. Add a `router` agent that classifies a task/target (python / json / yaml / dockerfile
   / markdown / algorithm) and selects the specialist.
2. Add specialist agents: `python_fixer`, `config_editor` (JSON/YAML/INI),
   `dockerfile_editor`, `regex_helper`, etc. — each single-purpose, each tested.
3. Wire the loop to dispatch via the router so each specialist FIRES (no orphans);
   add config/Dockerfile eval tasks so the new specialists are exercised.

#### Implements
- [REQ-6] Specialized agent fleet

### [TASK-7] Per-agent/eval usefulness metric + prune

Measure which agents/tools/evals contribute; remove dead weight (record why).

#### Steps
1. Track agent/tool usage + eval discriminativeness; drop the unhelpful, commit the reason.

#### Implements
- [REQ-2] Net growth with quality
