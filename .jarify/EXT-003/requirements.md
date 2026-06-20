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

### [REQ-5] Strategy-diverse cascade for the implement regime

Single prompt/sampling tweaks (best-of-N temperature diversity, few-shot) each move a 2B
only marginally on cold synthesis AND each trades tasks (regressions), because each one
*replaces* the baseline. The leverage is that the strategies are **complementary**: each
solves problems the others miss. So for the implement regime (filling a stub:
HumanEval/MBPP/from-intent), every attempt uses a *different* strategy generated from the
CLEAN stub — plain greedy, plain warm, few-shot, few-shot warm, high-temp ×2 — and the
deterministic test selects the first that passes. Because acceptance is test-gated, the
result is the **union** of what the strategies solve and is **strictly non-regressing**
versus any single strategy. Repair tasks keep feedback-iteration unchanged.

#### Acceptance Criteria
- [ ] `fix_loop` detects the implement regime (a `NotImplementedError`/`pass` stub) and
      drives the strategy cascade from the clean stub each attempt
- [ ] The attempt budget widens to cover the full strategy set when implementing
- [ ] Proven on an EXTERNAL benchmark out-of-sample (HumanEval[40:60]: 13/20 → 17/20,
      +4, zero regressions) — not on tasks tuned against
- [ ] Repair tasks (existing buggy code) are unaffected: feedback-iteration retained
- [ ] Cascade attempts mix two generation MODES: `whole` (whole-file rewriter) and `body`
      (body-completer — outputs only the function body, spliced after the given
      signature+docstring). Body-only is ~2x faster and solves different problems, widening
      the union (HumanEval spread: 59%→79% within-budget, ~104s→~49s per problem)
