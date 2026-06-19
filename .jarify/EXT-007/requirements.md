---
id: EXT-007
title: Continuous Harness Self-Improvement (the jarify way)
status: partial
priority: high
implementation:
  - file: harness/eval_runner.py
    ranges:
      - - 1
        - 40
---

This spec governs HOW jaros-code improves itself toward Claude-Code-on-Opus-4.8: the
same jarify way it builds anything — a living backlog of scoped tasks (`tasks.md`),
implemented one at a time, traced to the spec, validated, committed. It encodes the
owner's success criteria: **agents, tools, and evals must keep increasing AND
improving in quality over time** (toward the thousands/tens-of-thousands swarm),
pruning whatever does not help, with the metric trend (pass rate up, Wilson CI down)
as proof.

### [REQ-1] Backlog-driven improvement (jarify loop)

Improvement is driven by `EXT-007/tasks.md`: each supervisor cycle picks the next
pending task, implements it (decompose; never a bigger model), keeps tests green, and
commits. New frontier failures and ideas are appended as new tasks.

#### Acceptance Criteria
- [ ] A living `tasks.md` lists scoped improvement tasks toward parity
- [ ] Each cycle advances exactly one task and updates its status
- [ ] Implementation stays single-purpose and traces to a spec change in the same commit

### [REQ-2] Net growth with quality (and pruning)

Each cycle should grow the system — add a single-purpose agent, a deterministic tool,
or eval tasks — and may prune agents/tools/evals that do not help. The recorded census
(EXT-005 / REQ-9) must trend up over time, with quality (pass rate, CI) also improving.

#### Acceptance Criteria
- [ ] The census trend (agents/tools/evals) is net-increasing over time
- [ ] Unhelpful agents/tools/evals are removed, with the reason recorded in the commit
- [ ] Quality trend (pass rate up, Wilson CI narrowing) accompanies the count growth

### [REQ-3] Frontier-driven prioritization

The next improvement targets the measured frontier — the lowest unmastered tier / the
failing tasks — so effort goes where it moves the metric most.

#### Acceptance Criteria
- [ ] The cycle reads the current frontier tier and failing tasks from the report
- [ ] The chosen task addresses the frontier or tightens measurement (more/harder evals)
- [ ] Progress is visible in the trend after the change lands
