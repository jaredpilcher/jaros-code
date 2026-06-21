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
- [ ] All cascade attempts use the `body` mode (body-completer — outputs only the function
      body, spliced after the given signature+docstring), diversified by temperature/few-shot.
      The model wastes most tokens regenerating the docstring; body-only avoids that, so it is
      faster AND much more accurate on the first try. CONFIRMED apples-to-apples (same
      HumanEval[::4], 41 problems, gemma-4-e2b): whole-file cascade pass@1 37% / within 59% →
      body cascade pass@1 66% / within 76% (largest external-bar gain to date). The whole-file
      mode was later DROPPED: it truncates before its closing sentinel on long problems
      (wasting the attempt) and ran ~2x slower; all-body matches the mix exactly (31/41) at
      ~39s vs ~78s per problem. `editor`/rewriter retained for the repair regime.
- [ ] DEFINITIVE full-suite number (all 164 HumanEval problems, gemma-4-e2b, all-body cascade,
      2026-06-21): **pass@1 = 95/164 = 57.9%** (attempt 1, no test visibility — externally
      comparable) and **within-budget = 124/164 = 75.6%** (attempts 2-6 leak the failing test,
      so NOT comparable to published pass@1). Attempt distribution: {1:95, 2:5, 3:13, 4:4, 5:1,
      6:6}. This is the honest headline (the 41-problem slices read 66%/76% — the full hard set
      pulls pass@1 down to ~58%, within-budget holds ~76%). The run also validated the
      shell.exec process-tree kill: it completed all 164 cleanly past HumanEval_115, which
      previously hung the eval via an orphaned infinite-loop pytest.
- [ ] BREADTH — multi-file fix (`harness/multi_file.py`, wired as CLI `/fixrepo`): the
      single-file `fix_loop` cannot fix a fault that lives in a different file than the one
      under test (the Claude-Code-class case). `multi_file_fix` LOCATES candidate files
      deterministically (traceback files + import graph reachable from the failing test —
      a tool, not a model call), then tries `fix_loop` on each candidate on a clean snapshot,
      reverting a non-helping attempt before the next, until the test passes. Verified end-to-
      end: a bug in `mathutils.scale` (called via `main.apply`, tested in `test_app.py`) is
      located and fixed though the failure surfaces in a different file. Locating-the-file is
      the deterministic plane; only the fix is model work. Now exercised by a tracked eval
      (`harness/multifile_eval.py`, 9 scenarios: import-graph, 3-level deep chain, exception/
      traceback, cross-file operator bug, off-by-one range, boundary comparison, distractor
      modules, subpackage, and a MULTI-FAULT two-file case) — **9/9 = 100%** on gemma-4-e2b.
- [ ] MULTI-FAULT cross-file repair: a fault spanning 2+ files is now fixed CUMULATIVELY.
      `fix_loop` gained an opt-in `keep_partial` flag (default off → single-file behavior is
      byte-identical) that, on overall failure, leaves the attempt with the FEWEST test
      failures. `multi_file_fix` keeps a candidate's partial edit only if it strictly reduces
      the failing-test count, then fixes the next file on top. Verified end-to-end: two
      independent bugs in two files both located + fixed; 8/8 single-file unchanged; suite 118.
