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
