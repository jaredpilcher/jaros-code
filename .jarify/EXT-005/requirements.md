---
id: EXT-005
title: Convergence Evaluation Harness
status: partial
priority: high
implementation:
  - file: harness/eval_runner.py
    ranges:
      - - 1
        - 200
---

This spec serves the central, measurable promise of PRIME-001: the harness must
become so good it overcomes gemma2:2b's limits and reaches Claude-Code-on-Opus-4.8
quality — and we must *prove* convergence, run over run, not assert it. The
evaluation harness is that proof. It is deliberately extensible: the task suite is
expected to grow toward an extensive battery (and, later, to run existing public
benchmarks like SWE-bench / HumanEval).

### [REQ-1] Self-contained coding-task suite

A suite of self-contained coding tasks lives under `evals/coding_tasks/`. Each task
is data: a buggy file, a failing test, an instruction, and a test command, runnable
in an isolated working directory with no external dependencies.

#### Acceptance Criteria
- [ ] Each task declares `{id, instruction, target, files, test_cmd}`
- [ ] Tasks are isolated: setup writes `files` into a fresh temp dir, no shared state
- [ ] The initial suite covers diverse bug classes (arithmetic, comparison, range, format)
- [ ] Adding a task is dropping one JSON file — no code change

### [REQ-2] Scoring runner with pass rate

A runner executes every task through the real `fix_loop` and reports the pass rate
(tasks whose tests pass within the attempt budget) plus per-task attempts.

#### Acceptance Criteria
- [ ] Run each task via `fix_loop` in an isolated temp dir on gemma2:2b
- [ ] Record per-task `{id, solved, attempts}` and an overall `passRate`
- [ ] Print a Claude-Code-like scorecard summary
- [ ] Exit non-zero only on runner error, never merely on unsolved tasks

### [REQ-3] Trend history (convergence signal)

Each run appends a timestamped scorecard to a durable history so the pass-rate trend
over time is the explicit convergence signal toward the bar.

#### Acceptance Criteria
- [ ] Write a full scorecard JSON per run under the artifacts dir
- [ ] Append one summary line per run to a history file (model, passRate, counts, time)
- [ ] The history is machine-readable so trend can be charted/monitored

### [REQ-4] Difficulty tiers and the hardening ratchet

Tasks carry a difficulty `tier`. The runner scores per tier and a ratchet escalates
focus to the next, harder tier once the current tier is mastered — and the suite is
expected to keep adding harder tasks so it never stays easy (PRIME-001: evals must
get harder and harder).

#### Acceptance Criteria
- [ ] Each task declares an integer `tier` (1 = easiest); runner reports per-tier pass rate
- [ ] The runner computes the current "frontier" tier (lowest tier not yet mastered at a threshold)
- [ ] A suite whose every tier is mastered is flagged as "too easy — add harder tasks"
- [ ] Harder authored tiers (multi-edit, edge cases, small algorithms) exist beyond tier 1

### [REQ-5] Real public benchmark integration

Beyond home-grown tasks, the harness runs a real, recognized public benchmark
(HumanEval first) in the same isolated-run, exit-code-honest way, so the bar is
external. The adapter reads the standard benchmark format and runs a subset or all.

#### Acceptance Criteria
- [ ] A loader reads the HumanEval JSONL format (`task_id`, `prompt`, `test`, `entry_point`)
- [ ] Each problem runs in isolation; solved iff the official test passes (exit 0)
- [ ] Results feed the same scorecard/trend, labelled as the external benchmark
- [ ] If the dataset is absent, the runner reports clearly how to obtain it (no silent pass)
