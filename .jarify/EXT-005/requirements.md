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
become so good it overcomes Gemma 4 2B (`e2b`)'s limits and reaches Claude-Code-on-Opus-4.8
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
- [ ] Run each task via `fix_loop` in an isolated temp dir on Gemma 4 2B (`e2b`)
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

### [REQ-6] Operator metrics report (better and more accurate over time)

A report summarizes how convergence is going with metrics that both *improve* (pass
rate, per-tier, frontier) and become *more accurate* over time: the pass rate
carries a Wilson 95% confidence interval that tightens as the suite grows, and a
coverage section (task count, tiers, real-benchmark inclusion) shows measurement
breadth increasing. A short headline is pushable to the owner's phone.

#### Acceptance Criteria
- [ ] Compute the pass rate with a Wilson 95% interval whose width shrinks as N grows
- [ ] Report per-tier pass rates, the frontier tier, and the recent trend from history
- [ ] Report coverage (number of tasks, tiers, whether real benchmarks are included)
- [ ] Render a markdown report and a <200-char headline suitable for a push notification

### [REQ-8] Scheduled phone reports with quiet hours

The supervisor pushes a phone report on a fixed cadence (default every 30 min) but
NEVER during quiet hours (default 02:00–08:00 local). The gating is deterministic and
testable; the last-push time is persisted so cadence holds across cycles.

#### Acceptance Criteria
- [ ] `in_quiet_hours` is true for 02:00–07:59 local and false otherwise
- [ ] `should_push` returns false during quiet hours regardless of elapsed time
- [ ] Outside quiet hours, `should_push` is true only when >= interval since last push
- [ ] The last-push timestamp is persisted and re-read across supervisor cycles

### [REQ-9] Growth census (agents, tools, evals increasing)

The report counts the system's agents, tools, eval tasks, and specs, and shows their
growth over time — because success is visible only as these COUNTS increasing (toward
the thousands/tens-of-thousands swarm goal) alongside improving quality.

#### Acceptance Criteria
- [ ] Count single-purpose agents, deterministic tools, eval tasks, and EXT specs
- [ ] Persist the census each run so the growth trend is recorded
- [ ] The report shows current counts, their change vs the first recorded run, and the goal
- [ ] The headline includes the counts so increasing agents/tools/evals is visible at a glance

### [REQ-7] Continuous always-on operation

The harness runs continuously (forever), perpetually exercising itself over the suite
and emitting fresh metrics + a heartbeat each cycle, fault-isolated so no single
cycle stops it. It is safe to leave running unattended (local model + temp-dir tests
only). Improvements committed between cycles are picked up automatically.

#### Acceptance Criteria
- [ ] A runner loops forever: eval → report → heartbeat → short pause → repeat
- [ ] Any cycle error is logged and the loop continues (never crashes the process)
- [ ] A machine-readable heartbeat (cycle, timestamp, passRate, CI) is written each cycle
- [ ] Uses only local inference + temp-dir tests (no network, no host mutation outside artifacts)

### [REQ-10] Generative convergence metric (self vs. hidden oracle)

Repair pass-rate alone does not prove we can build from intent. The harness also tracks
the EXT-008 from-intent metric: per task, `self_pass` (own tests) and `oracle_pass`
(held-out oracle), aggregated into a generative pass-rate trend alongside the repair
trend. The un-gameable headline is the **intent-fidelity** rate (oracle pass), and the
**self-yes/oracle-no** rate is surfaced as the "misread intent" gap to drive down.

#### Acceptance Criteria
- [ ] Run the `evals/intent_tasks/` suite through `build_from_intent` and record per task
      `{id, self_pass, oracle_pass}`
- [ ] Report a generative pass-rate (oracle) trend distinct from the repair pass-rate
- [ ] Surface the self-yes/oracle-no ("misread intent") rate as its own tracked number
- [ ] The oracle is never written into a build dir or shown to any agent (honesty)

### [REQ-11] Supervisor convergence loop: wiring health & correction

The supervisor runs the standing MEASURE→DIAGNOSE→DISCOVER→PLACE→WIRE→RE-MEASURE→PRUNE
loop (PRIME-001 design). The harness must give it the signals to do so honestly: which
agent→tool wirings actually fire (no orphans), which agents/tools/evals are unused
(prune candidates), and whether any change was net-negative (revert signal).

#### Acceptance Criteria
- [ ] Report wiring usage: every agent→tool edge exercised in a run, with fire counts
- [ ] Flag orphans: agents that never emit a used Decision and tools never invoked
- [ ] The honesty audit flags STAGNATION (flat trend), MISLEADING (tiny N), and UNUSED
      (orphans) so the supervisor knows where to correct
- [ ] Census + trend are persisted so net-negative changes are detectable and reversible
- [ ] Track ORCHESTRATION/WIRING QUALITY as a trended success axis (not just counts):
      `leverage` = solved tasks per agent (rises when wiring improves at flat agent count),
      distinct wired edges fired, and decisions composed per solved task — persisted to
      history and shown in the report with deltas vs the first recorded run

### [REQ-5] Real public benchmark integration

Beyond home-grown tasks, the harness runs a real, recognized public benchmark
(HumanEval first) in the same isolated-run, exit-code-honest way, so the bar is
external. The adapter reads the standard benchmark format and runs a subset or all.

#### Acceptance Criteria
- [ ] A loader reads the HumanEval JSONL format (`task_id`, `prompt`, `test`, `entry_point`)
- [ ] Each problem runs in isolation; solved iff the official test passes (exit 0)
- [ ] Results feed the same scorecard/trend, labelled as the external benchmark
- [ ] If the dataset is absent, the runner reports clearly how to obtain it (no silent pass)
