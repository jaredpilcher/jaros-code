---
id: EXT-003
title: Bounded Coding Loop Orchestration
status: partial
priority: high
implementation:
  - file: harness/coding_loop.py
    ranges:
      - - 1
        - 394
---

This spec serves **Tenets 1, 3 & 5** of PRIME-001. Single-purpose agents (EXT-002)
and deterministic tools (EXT-001) are individually incomplete; this orchestration
composes them into a bounded edit→test→judge loop, routing every step through the
real Jaros gate + executor so each Decision is validated, executed, and recorded in
the decision log (replay-faithful). The transcript gives a Claude-Code-like feel.

### [REQ-1] Faithful Jaros runtime wrapper

A `Runtime` registers the EXT-001 tools and the built-in `advance` handler, then
applies a Decision through the real `validate_decision` gate and `executor.apply`,
recording each accepted Decision to a durable decision log.

#### Acceptance Criteria
- [ ] Register custom tools from `.jaros-data/tools` and the `advance` handler
- [ ] Validate every Decision at the gate before execution; reject reports a reason
- [ ] Apply accepted Decisions via `executor.apply` and return the tool output
- [ ] Record each accepted Decision to a `DecisionLog` under the data dir's `state/`

### [REQ-2] Bounded edit→test→judge loop

A `fix_loop` composes editor → code.apply_patch → (run tests) → test-reader over a
target file and a test command, iterating up to a bounded number of attempts and
stopping as soon as the test-reader judges PASS.

#### Acceptance Criteria
- [ ] Read the target file and pass bounded content to the `editor` agent each round
- [ ] Apply the editor's edit through the Runtime (deterministic tool)
- [ ] Run the test command via `shell.exec` through the Runtime and capture output
- [ ] Feed output to `test-reader`; stop on PASS or after `max_iters`; report the outcome

### [REQ-3] Claude-Code-like transcript

The loop prints a transparent, streaming transcript: each agent's decision and each
tool's real result, so the operator sees exactly what the harness is doing.

#### Acceptance Criteria
- [ ] Print a per-round header and the model/provider in use
- [ ] Show each agent's emitted Decision type and the tool result summary
- [ ] Show the final PASS/FAIL outcome and the number of attempts used

### [REQ-4] Deterministic boundary-mutation repair fallback

Some bugs turn on a single operator a 2B model cannot reason about (`<` vs `<=`).
Empirically, every *model-side* decomposition of such a fix (locate the line, fix the
line, quote the snippet) bottoms out on that same judgement gemma2:2b cannot make. So
for the boundary/off-by-one bug class the fix moves into the **deterministic plane**:
when the whole-file rewrite (REQ-2) fails on an existing `.py` bug, try each
single-operator mutation (`<`↔`<=`, `>`↔`>=`, `±1`) via the `code.write_file` tool, run
the suite via `shell.exec`, and keep the first candidate that passes. No reasoning call
is involved, so the repair is byte-identically reproducible (Tenet 3). This honours the
decomposition mandate honestly: the ant-sized grain is a mechanical edit + test, not a
judgement the model is incapable of.

#### Acceptance Criteria
- [ ] `boundary_repair_candidates` is pure and deterministic: one single-operator edit
      per candidate, de-duplicated and stably ordered
- [ ] `mutation_repair_loop` applies each candidate via the Runtime and runs the suite,
      returning success on the first candidate that makes the tests pass
- [ ] On total failure it restores the original file (never leaves a worse file)
- [ ] Wired as the `fix_loop` fallback for `.py` bug-fixes the rewriter cannot crack
