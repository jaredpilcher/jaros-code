---
id: EXT-020
title: Decomposition Probe
status: covered
priority: high
implementation:
  - file: harness/decomp_probe.py
    ranges:
      - - 1
        - 300
---

### [REQ-1] Two-Phase Decompose-then-Implement Flow

The probe must prompt the 2B (temp=0) to write a DETAILED NUMBERED IMPLEMENTATION PLAN
for the target function — concrete internal steps (parse args, iterate, handle edge cases,
return), far more granular than the behavior gherkin — then prompt the 2B (temp=0) to
implement the function FOLLOWING that explicit plan (the plan as scaffolding in the
implement prompt), piped through the proven indentation-repair layer.

#### Acceptance Criteria
- [ ] `_g_plan()` prompts the 2B at temp=0 for a granular numbered implementation plan
- [ ] `_g_code_from_plan()` prompts the 2B at temp=0 to implement following the plan
- [ ] The plan is passed as scaffolding in the implement prompt (not just gherkin alone)
- [ ] Implementation output is piped through the proven indentation-repair layer
- [ ] `_core_decomp_probe()` inner loop is pure (no git I/O), fully testable offline with injectable stubs
- [ ] The monolithic greedy baseline (implement without a plan) is also scored for apples-to-apples comparison

### [REQ-2] Honest Oracle Scoring and Reporting

The probe must score all implementations via the hidden oracle (`_run_nodes` red->green).
The oracle must be invoked ONLY after both the plan and the implementation have been
generated — score-only, never shown to the model during decompose or implement steps.
The probe must load the same hard greedy-fail tasks that EXT-019 probed (from
bigbar_jaros.txt via `_parse_fail_shas`/`_resolve_tasks`), report per-task
(cracked? yes/no) and overall summary comparing decomp vs monolithic greedy,
and state an explicit verdict (HELPS / NO GAIN) answering the key question.

#### Acceptance Criteria
- [ ] Oracle is called after generation only — score-only, never influences plan or implement
- [ ] Task loading uses `_parse_fail_shas` + `_resolve_tasks` (same as EXT-019)
- [ ] Per-task cracked/not-cracked reported with greedy baseline column
- [ ] Overall summary table with Wilson CI
- [ ] Explicit verdict: if decomp > greedy → REASONING bottleneck; if both zero → CODING bottleneck
- [ ] `--tasks N` CLI argument (default 8); progress printed per task
