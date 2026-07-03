---
id: EXT-036
title: Sentence-to-System — build a complex Python system from a one-sentence spec (Claude-Code-parity)
status: uncovered
priority: high
implementation: []
---

**Owner directive (2026-07-03):** the next major gap for CC-parity is to be *"really really really good at
building complex systems from a sentence."* This spec IDENTIFIES what that means, and drives the
build-discover-record-fill loop toward it. It is the PLANNER layer on top of the existing Foundry EXECUTOR
(EXT-035/EXT-008: build_from_intent → deterministic import wiring → assemble → ship-gate, proven to ~4 modules).

## What "system from a sentence" decomposes into (the capability layers)

A. **Spec expansion** — sentence → implied requirements. B. **Architecture** — requirements → module graph.
C. **Interface design** — module graph → signatures (contract-first). D. **Ordered implementation** — build
leaves-first against fixed interfaces. E. **Per-module test + validate.** F. **Integration** — assemble + run
system-level. G. **Cross-level repair** — a failure routed to the right level (body / interface / architecture).
H. **Scale** — 10+ modules. The EXECUTOR covers D/E/F (to ~4 modules) + per-level G; the PLANNER (A/B/C) and
end-to-end orchestration + H are the new work.

## MEASURED so far (probe `.jaros-data/s2s_planner_probe.py`, 2026-07-03)

**SURPRISE (reshapes the gap):** the small local model (gemma) produces STRUCTURALLY COHERENT plans from a
sentence for simple/medium/complex specs — valid module DAG, per-module signatures, no import cycles,
entrypoint, an acceptance line. The deterministic coherence validator passes all three. So "a 2-3B can't
architect from a sentence" is FALSE at the structural level — that is NOT the gap. The gaps are downstream:

### [REQ-1] Planner: sentence → structured, coherence-validated plan  (PARTIAL — structural planning works)

The model proposes a JSON plan (modules, responsibilities, exports+signatures, imports, entrypoint,
acceptance); a deterministic plane validates coherence (parseable, exports well-formed, imports reference real
modules, DAG acyclic, entrypoint listed). Two-plane: model judges the decomposition, deterministic plane
guarantees structural coherence + repairs/rejects incoherent plans.

#### Acceptance Criteria
- [x] Model emits a parseable JSON plan for a one-sentence spec (probed: simple/medium/complex all parse)
- [x] Deterministic coherence validator (DAG/signatures/imports/entrypoint) — probed, all three pass
- [ ] A plan-repair loop: when the validator finds defects, feed them back for a coherent re-plan (analog of the write-tests repair loop)
- [ ] Measured on a held-out set of sentences; coherence-pass rate reported honestly

### [REQ-2] Executable acceptance — the plan must emit a RUNNABLE system-level oracle, not prose  (GAP)

The probe's acceptance was PROSE ("output containing the min, max, mean") — not deterministically checkable.
For honest end-to-end validation the plan (or a follow-up step) must produce a concrete runnable acceptance
check (a script asserting real behavior on a real input) so the built system is test-gated, not eyeballed.

#### Acceptance Criteria
- [ ] The planner emits (or a deterministic step derives) an executable acceptance test for the system
- [ ] The acceptance test is run against the assembled system; ship only if it passes (Tenet 3: real gate, no prose)

### [REQ-3] Per-module oracle generation — reuse the write-tests capability to gate each module build  (GAP)

`build_from_intent` is oracle-gated (needs a per-module test), but the plan gives only responsibility+signature.
DISCOVERED gap: generate a per-module oracle from responsibility+signature (compose the NEW write-tests
capability, EXT-005 TASK-6/8) so each module builds against a real test, not just free generation.

#### Acceptance Criteria
- [ ] For each planned module, derive a per-module oracle test from its responsibility+signature
- [ ] `build_from_intent` builds each module gated on that oracle; sibling signatures supplied as context

### [REQ-4] End-to-end: plan → ordered build → wire → assemble → acceptance  (GAP — the real test)

Drive the full pipeline: planner → build each module in topological order (deps as context, imports wired
deterministically via EXT-035 resolve_imports) → assemble → run the executable acceptance. This is where
SEMANTIC (not structural) coherence gets tested: do the thin plans yield modules that actually integrate + work?

#### Acceptance Criteria
- [x] End-to-end run on the SIMPLE spec produces a runnable system that passes its acceptance test — **DONE 2026-07-03**
  (`.jaros-data/s2s_build_probe.py`): sentence "CSV column-stats CLI" → gemma plans csv_reader←column_stats←cli →
  builds each module → assembles → runs → prints CORRECT per-column min/max/mean (rc=0, honestly checked). TWO GAPS
  DISCOVERED + FILLED to get here: (i) module generation TRUNCATED at low max_tokens → SyntaxError (raised budget);
  (ii) no per-module SYNTAX gate/repair before assembly → malformed module surfaced as a cryptic system error (added a
  py_compile gate + a bounded syntax-repair loop per module, analog of the write-tests repair). These belong in the
  productionized pipeline.
- [ ] Measured on medium→complex; the honest break-point (where end-to-end fails) is the recorded gap
- [ ] Failures diagnosed to a LEVEL (spec/architecture/interface/body/integration) — feeds REQ-5
- [ ] BLOCKER for auto-validating medium/complex: REQ-2 (executable acceptance) — the simple case worked because the
  plan fixed the CLI interface (argv[1]=csv path) so a concrete acceptance could be written; medium/complex need the
  planner to EMIT a runnable acceptance matching the built interface, else validation is manual.

### [REQ-5] Cross-level repair + scale  (FUTURE — discover as we build)

When end-to-end fails, route the failure to the right level (re-plan vs re-interface vs re-implement vs
re-integrate) and repair there. Then push scale (H) past 4 modules. Requirements here will be discovered by
building REQ-1..4 and recording what breaks.

#### Acceptance Criteria
- [ ] (to be discovered) failure-level classifier + level-targeted repair
- [ ] (to be discovered) scale past ~4 modules with sustained end-to-end pass

---

## EXPANDED CAPABILITY SUITE (owner directive 2026-07-03) — "be like Claude Code"

The owner expanded the target: to build complex systems well, jaros-code must also do the surrounding agentic
work Claude Code does. Many gaps — recorded here, filled iteratively (each surfaces naturally as the
sentence-to-system pipeline demands it). Cross-cutting ones (REQ-8..11) may spin out to their own specs.

### [REQ-6] Multi-level test generation — unit / integration / performance  (GAP)

Beyond the unit-test capability (EXT-005 write-tests, mutation-graded): generate INTEGRATION tests (do the
assembled modules work together across boundaries?) and PERFORMANCE tests (does it meet a throughput/latency
bar?). Each honestly graded (integration: real cross-module behavior; performance: measured against a threshold).

#### Acceptance Criteria
- [ ] Integration-test generation for a multi-module system (exercises real cross-module flows, not just one unit)
- [ ] Performance-test generation (measures + asserts a threshold; honest, not a trivially-passing stub)
- [ ] Composed into the sentence-to-system pipeline: a built system gets unit + integration (+ perf where relevant) tests

### [REQ-7] Done-ness validation — is the system complete vs the spec, or not?  (GAP)

A judgment + deterministic evidence that the built system SATISFIES the original sentence (all implied
requirements covered), and an honest "NOT done — here's what's missing" when it doesn't. Builds on the
ship-gate + executable acceptance, but at the SPEC level (did we build what was asked?), not just per-module.

#### Acceptance Criteria
- [ ] Derive the acceptance criteria from the spec (spec-expansion → checklist of implied requirements)
- [ ] Validate each against the built system; report DONE only if all pass, else list the unmet items honestly (Tenet 3)

### [REQ-8] Ask-the-user when needed — clarify ambiguity  (GAP, cross-cutting)

When the spec is ambiguous or under-determined, ASK the user a targeted question rather than guessing (Claude
Code's AskUserQuestion). Requires a judgment (is this genuinely ambiguous?) + an interaction channel.

#### Acceptance Criteria
- [ ] A grounded judgment that detects genuine ambiguity (not asking when a sensible default exists)
- [ ] An interaction channel to surface the question + consume the answer into the plan

### [REQ-9] Web research when needed  (GAP, cross-cutting — OWNER-AUTHORIZED 2026-07-03)

The system may research the web when it needs external knowledge (an API, a format, a library usage). Owner
AUTHORIZED this 2026-07-03 — it supersedes the prior "no harness network" caution (task #32) FOR BUILD-TIME
research. HARD Tenet-3 GUARD: web research must NEVER be used to fetch answers/tests for a held-out eval
(that would corrupt the only honest signal); it is a build-time capability for real user tasks, gated off eval runs.

#### Acceptance Criteria
- [ ] A web-research tool (WebSearch/WebFetch) the system invokes when it judges it needs external knowledge
- [ ] A judgment for WHEN research is needed; results grounded into the build
- [ ] HARD guard: disabled/blocked on held-out eval paths (no leakage, Tenet 3)

### [REQ-10] Repo-context search when needed  (GAP, cross-cutting — tools partly exist)

Search the repo for relevant context (existing helpers, conventions, related code) when building/fixing, and
inject it. Tools EXIST (`/grep`, `/files`, `harness/repo_map.py`); the gap is a judgment for WHEN to search +
wiring the retrieved context into the solve/build loop (contrast the retrieval-negative finding — the lever is
PRECISE API/helper injection, not noisy similar-code; see memory retrieval-fewshot-negative).

#### Acceptance Criteria
- [ ] A judgment that decides when repo context is needed + what to search for
- [ ] Precise retrieved context (signatures/helpers) injected into the build/fix prompt; measured to help, not hurt

### [REQ-11] Skills system — use skills when it judges it needs them  (GAP, cross-cutting — biggest new architecture)

A Claude-Code-style skills system: a library of reusable skills (procedures/capabilities) the system SELECTS
and invokes when it judges a task needs one. Requires: a skill registry, a skill-selection judgment (grounded
for the small model), and skill execution wired into the two-plane architecture.

#### Acceptance Criteria
- [ ] A skill registry (named skills with descriptions/when-to-use)
- [ ] A grounded skill-selection judgment (the small model picks the right skill for a task, or none)
- [ ] Skill execution wired in; measured that skill-use helps on tasks that need it
