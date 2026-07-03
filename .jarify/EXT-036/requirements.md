---
id: EXT-036
title: Sentence-to-System — build a complex Python system from a one-sentence spec (Claude-Code-parity)
status: partial
priority: high
implementation: ["harness/session.py", "harness/cli.py", "harness/project_md.py"]
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
- [x] The planner emits (or a deterministic step derives) an executable acceptance test for the system — **DONE 2026-07-03**
  (`.jaros-data/s2s_doneness_probe.py`): sentence → a CHECKLIST of executable acceptance checks derived contract-first
  from the SPEC + module API (not the code), each a standalone Python assertion against the built API.
- [x] The acceptance test is run against the assembled system; ship only if it passes — DONE (URL-shortener: 4/4 checks
  pass → DONE). CAVEAT (Tenet 3): the model writes both checks AND code from the same spec, so this validates internal
  consistency + implementation bugs, NOT fully-independent external validation — productionize with independent/mutation rigor.

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
- [x] Derive the acceptance criteria from the spec (spec-expansion → checklist of implied requirements) — **DONE 2026-07-03**
  (probe: sentence → 4 implied-requirement checks: round-trip, uniqueness, stability, resolution accuracy)
- [x] Validate each against the built system; report DONE only if all pass, else list unmet items — DONE (reports
  "DONE (all pass)" or "NOT DONE — unmet: <list>"). Same Tenet-3 caveat as REQ-2 (model-written checks; add independence).

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

### [REQ-12] CLI UX parity with Claude Code  (GAP, owner directive 2026-07-03 — serves Tenet 5)

The jaros-code CLI (`harness/cli.py`, `scripts/jcode.*`) must FEEL like Claude Code: a conversational, interactive
terminal session — the user interacts naturally, asks questions, gives instructions mid-task, and can resume prior
conversations. Today the REPL is command/one-shot oriented. Implementation lives with the CLI (EXT-004). This is
Tenet-5 UX and pairs with REQ-8 (the system asking the USER) — REQ-12 is the reverse+conversational channel.

#### Acceptance Criteria
- [ ] Conversational multi-turn session: freeform natural-language turns (not just slash commands), with context
  carried across turns (the model sees the running conversation, not each request in isolation)
- [ ] Mid-task steering: the user can give a new instruction / correction mid-task and the session adapts
- [ ] The system can ASK the user a question and consume the typed answer inline (shares REQ-8's channel)
- [ ] Resume conversations: sessions persist (transcript + state) and can be resumed later (`--resume` / session id)
- [ ] Familiar Claude-Code affordances: streaming output, clear turn markers, `/help` + slash commands still available,
  graceful interrupt — but UX NEVER overrides a higher tenet (Tenet 5 is the lowest-priority tenet)

### [REQ-13] Full difficulty spectrum — easy / medium / hard / highly-complex creation  (GAP, owner 2026-07-03)

Sentence→system must span the whole difficulty range, not just easy. SIMPLE/EASY is PROVEN (REQ-4). Push medium →
hard → highly-complex; the honest break-point at each tier is the recorded gap (likely bites at the reasoning-heavy
tiers, the measured small-model frontier — so expect two-plane scaffolding + roster routing to a stronger Jetson-fit
model, e.g. the queued Qwen2.5-Coder-7B, to be the lever for hard/highly-complex).

#### Acceptance Criteria
- [x] easy (proven, REQ-4) — [ ] medium — [ ] hard — [ ] highly-complex, each with a held-out sentence set + honest pass rate
- [ ] The break-point tier is documented with the failing LEVEL (spec/arch/interface/body/integration) and the lever tried

### [REQ-14] Modification from a sentence — evolve an existing system  (GAP, owner 2026-07-03)

Not just create — MODIFY an existing codebase from a sentence ("add rate-limiting to the shortener", "make the CSV
CLI also output median"). Compose the existing edit capabilities (fix/edit/refactor/multi_file + repo-context REQ-10):
locate the relevant code, plan the change, apply, re-validate (done-ness) that the modification is complete + didn't
break existing behavior (regression-gated).

#### Acceptance Criteria
- [ ] Given an existing system + a modification sentence, locate the change site(s) and apply the change
- [ ] Re-run existing + new acceptance so the modification is validated AND nothing regressed (Tenet 3)
- [ ] Measured across difficulty tiers, like REQ-13

## AGENTIC INFRASTRUCTURE (owner directive 2026-07-03) — the Claude-Code substrate (memory / tasks / experiments / project-file)

Claude Code manages short + long-term memory, condenses context, keeps per-repo memory + a CLAUDE.md sent every
prompt, creates todo tasks + experiments. jaros-code has META-level analogs (this convergence loop uses a task list,
experiments, CLAUDE.md, .claude memory) but must build these INTO the harness for its USERS.

### [REQ-15] Short-term memory management + condensation  (GAP)

The session transcript (REQ-12) is short-term memory; when it grows past the small model's budget, CONDENSE it (an
LLM/deterministic summary of older turns) so context stays within budget without losing the thread — Claude-Code's
compaction. Critical for the small model (tiny context window makes this MORE important than for a big model).

#### Acceptance Criteria
- [ ] Bounded working-context budget; when exceeded, older turns are condensed into a running summary kept in-context
- [ ] Condensation preserves task-relevant facts (measured: a follow-up needing an old fact still resolves post-condense)

### [REQ-16] Long-term + PER-REPO memory  (GAP)

Persistent memory that survives across sessions, SEPARATE per repo the user works on (facts/decisions/preferences for
THIS project). Mirrors the .claude per-project memory model. Small-model-appropriate: recall must be PRECISE (the
retrieval-negative lesson — inject the few relevant facts, not a noisy dump; see memory retrieval-fewshot-negative).

#### Acceptance Criteria
- [ ] A per-repo memory store (keyed by repo path/id) persisted under the repo's jaros state
- [ ] Write (capture a durable fact) + precise recall (surface only the few relevant facts into the prompt)
- [ ] Isolated per repo; measured that recall helps, not hurts (guard against the noisy-context regression)

### [REQ-17] Project-instructions file auto-injected every prompt (JAROS.md ≈ CLAUDE.md)  (GAP)

A per-repo `JAROS.md` (project instructions/conventions) that is loaded and injected into the agent's context on
EVERY user prompt, so the system always honors the project's rules — exactly like CLAUDE.md.

#### Acceptance Criteria
- [x] `JAROS.md` (per repo) is discovered + loaded; its content is injected into the solve/route prompt every turn —
  **DONE 2026-07-03** (`harness/project_md.py::load_project_md`, discovers repo-root `JAROS.md` falling back to
  `.jaros/JAROS.md`; injected via `harness/cli.py::_augment_with_history` as a `PROJECT INSTRUCTIONS:` preamble
  ahead of conversation history on every plain-language + `_nl_fix` turn)
- [x] Bounded (fits the small context); absent file is a graceful no-op — **DONE 2026-07-03** (bounded to
  `MAX_CHARS=2000`; absent/unreadable file returns `""` and leaves the request byte-identical)

### [REQ-18] TODO task creation + management (user-facing)  (GAP)

The system creates + tracks todo tasks for the user's work (decompose a request into tracked steps, mark progress),
like Claude Code's task list — surfaced in the CLI.

#### Acceptance Criteria
- [ ] Create/list/update tasks tied to the session/repo; the model can propose a task breakdown for a request
- [ ] Surfaced in the CLI UX (REQ-12); persisted with the session/repo

### [REQ-19] Experiment creation + management (user-facing)  (GAP)

The system can create + run experiments for the user (hypothesis → run → measure → record), like this convergence
loop does at the meta level — exposed as a first-class user capability.

#### Acceptance Criteria
- [ ] Define an experiment (what to run, how to measure), run it, record the result against the hypothesis
- [ ] Results persisted (per-repo) + surfaced; reusable across sessions
