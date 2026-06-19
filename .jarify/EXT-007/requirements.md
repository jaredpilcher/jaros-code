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

### [REQ-5] Continual honesty audit

The system mechanically audits its own honesty every cycle so it cannot lie to itself:
flagging zero-model-call runs, tiny/non-representative suites reported as headlines,
stagnation (flat full-suite pass rate), and orphan inflation. The supervisor must ACT
on flags, never paper over them.

#### Acceptance Criteria
- [ ] Flag CRITICAL when a run solved tasks with `modelCalls.count == 0`
- [ ] Flag MISLEADING when a sub-representative suite (<10 tasks) is reported
- [ ] Flag STAGNATION when the full-suite pass rate is flat across recent runs
- [ ] Surface the flags in the report; the supervisor acts on them each cycle

### [REQ-6] Specialized agent fleet (split + wire everything)

Capability toward Opus-4.8 comes from MANY specialized single-purpose agents, not a
few broad ones. Broad agents are split into specialists by language/domain (e.g.
python-fixer, config/JSON/YAML editor, Dockerfile editor, regex/algorithm helpers,
architecture/spec agents) and every one is wired so it actually fires — chosen by a
router/dispatcher. No broad catch-all agents; no orphans.

#### Acceptance Criteria
- [ ] Identify code/config/domain types and define one specialized agent per type
- [ ] A router/dispatcher selects the right specialist for a task (and it fires)
- [ ] Each specialist is single-purpose with its own tests; broad agents are split or pruned
- [ ] Every added specialist is wired (appears in wiringUsage), never an orphan

### [REQ-4] Wiring telemetry (watch + optimize the agent↔tool wirings)

The system records how often each tool/decision type fires during eval runs, so we
can SEE which agent↔tool wirings are actually used and optimize: wire-in or prune
ones that never fire. Reported alongside the metrics.

#### Acceptance Criteria
- [ ] Each executed decision increments a per-type usage counter
- [ ] The usage snapshot is recorded in the scorecard each run
- [ ] The report shows tool/wiring usage ranked, flagging never-fired tools
- [ ] The counter resets per run so usage reflects the current suite

### [REQ-3] Frontier-driven prioritization

The next improvement targets the measured frontier — the lowest unmastered tier / the
failing tasks — so effort goes where it moves the metric most.

#### Acceptance Criteria
- [ ] The cycle reads the current frontier tier and failing tasks from the report
- [ ] The chosen task addresses the frontier or tightens measurement (more/harder evals)
- [ ] Progress is visible in the trend after the change lands
