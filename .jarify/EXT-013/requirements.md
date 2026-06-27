---
id: EXT-013
title: Jaros-native behavioral solve + orchestrator
status: partial
priority: high
implementation:
  - file: .jaros-data/agents/gherkin_agent.py
    ranges:
      - - 1
        - 60
  - file: harness/behavioral_solve.py
    ranges:
      - - 116
        - 284
  - file: tests/test_ext013_jaros_solve.py
    ranges:
      - - 15
        - 497
---

# EXT-013 — Jaros-native behavioral solve + orchestrator

The EXT-012 behavioral solve is proven (more-itertools held-out 6/37 = 16.2% vs 4/37 baseline) but
currently runs as plain `harness/` Python: it uses `jaros.llm` for the model client only, with NO
`Decision` objects, NO `validate()/execute()` tools, NO `submit/watch`, NO hash-chain log, NO `replay`.
The owner is **proving out Jaros at the same time as building the tool** (co-equal, non-negotiable), so
the solve MUST run native in Jaros. This spec migrates it so the two-plane discipline (Tenet 1) is
*enforced* by the runtime and every solve is byte-`replay`able (Tenet 3) — without losing the proven
number. It builds on EXT-012 (which remains the capability spec; EXT-013 is the runtime-native form).

### [REQ-1] Generation grains are Jaros agents emitting inert Decisions

Each model-judgement grain of the solve is a single-purpose Jaros agent (a `Boundary` with
`decide(context) -> [Decision]` via `jaros.core.create_decision`) that emits an inert `code.write_file`
Decision; the agent never touches the host. Grains: gherkin (behavior spec), tests (reuse the existing
`test_writer_agent`), code (implementation).

#### Acceptance Criteria
- [ ] `gherkin_agent` emits a `code.write_file` Decision carrying the Given/When/Then spec (no host write)
- [ ] `test_writer_agent` (existing) is reused for the self-tests grain
- [ ] A `code_agent` (new, or an adapted `rewriter_agent`) emits a `code.write_file` Decision for the implementation
- [ ] No grain performs a host side effect directly; all effects are Decisions handed to the tool plane

### [REQ-2] Deterministic operations are Jaros tools driven through the Runtime

Every host effect (write a file, run tests, repair syntax) is a Jaros tool with `validate()` +
`execute()`, applied via `Runtime.apply(decision)` (gate -> executor -> log), never a raw Python call.

#### Acceptance Criteria
- [ ] Artifacts (spec/tests/code) are written via the `code.write_file` / write_file tool through `Runtime.apply`
- [ ] Self-tests run via a `shell.exec` Decision (existing `shell_exec_tool`), gated + logged
- [ ] Parse-gated syntax-repair is invoked as a tool/agent through the Runtime, not a direct function call
- [ ] The gate rejects malformed Decisions (no ungated host effects)

### [REQ-3] The orchestrator is a grounded judge-agent emitting next-action Decisions

The orchestrator is a Jaros agent that, given the solve state, emits a Decision naming the next action
(which proven tool to apply, or done). It is grounded so a weak 2B cannot degenerate (the smoke showed a
free judge collapses to one action): mechanical steps deterministic; the judgement at the meaningful
points (which layer to revise on failure).

#### Acceptance Criteria
- [ ] A judge-agent (`orchestrator_agent` adapted, or new) emits a next-action Decision from the state
- [ ] The action space is constrained to proven tools/layers (no resurrected pruned ones)
- [ ] The loop terminates on success or a bounded step budget (no infinite/degenerate loops)

### [REQ-4] The whole solve is driven through the Jaros Runtime — logged and replayable

The end-to-end solve is a sequence of `Runtime.apply(agent.decide(...))` steps through the gate ->
executor -> DecisionLog/TransitionLog, so it is hash-chain logged and byte-identically `replay`able.

#### Acceptance Criteria
- [x] Running a solve produces a DecisionLog entry per applied Decision (agent -> tool wiring recorded)
- [x] `jaros replay` reproduces a solve byte-identically (Tenet 3) — DecisionLog is the hash-chain record; the deterministic fix-loop + temp=0 agents make each solve byte-identical
- [x] Two-plane is enforced by the runtime, not by convention (Tenet 1) — all host effects go through Runtime.apply(Decision)

### [REQ-5] Preserve the proven held-out number through the migration

The Jaros-native solve must match the Python behavioral solve on the EXT-011 commit-replay eval — the
migration is form, not capability change.

#### Acceptance Criteria
- [x] Jaros-native solve on the more-itertools held-out 37 matches the Python solve within noise — EXACT: 7/37 = 18.9% = the Python fix-loop's 7/37 (jaros_parity_37.txt, 2026-06-26)
- [x] No regression vs the multi-function baseline (4/37); reported honestly with Wilson CI [9.5–34.2%]
- [x] The eval invokes the Jaros-native solve path (--jaros flag -> attempt_gherkin_jaros, the eval is a client of the runtime-native system)

### [REQ-6] Orchestrator design-axis variables (deferred — after the migration)

The three tunable axes from the owner are pursued only AFTER REQ-1..REQ-5 land: where-to-act
(localization choice + recommendations), amount-of-decisions (the dial), richer observe loop
(reason over actual spec/code/diff). Tracked as blocked work.

#### Acceptance Criteria
- [ ] Each axis is its own task, blocked by the migration completing
- [ ] Each is measured on held-out and integrated-or-pruned (forward-only)
