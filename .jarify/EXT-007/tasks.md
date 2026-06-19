# Implementation Tasks — Self-Improvement Backlog (toward Opus-4.8 parity)

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

### [TASK-7] Per-agent/eval usefulness metric + prune

Measure which agents/tools/evals contribute; remove dead weight (record why).

#### Steps
1. Track agent/tool usage + eval discriminativeness; drop the unhelpful, commit the reason.

#### Implements
- [REQ-2] Net growth with quality
