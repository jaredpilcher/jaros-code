---
id: EXT-036
title: Sentence-to-System — build a complex Python system from a one-sentence spec (Claude-Code-parity)
status: partial
priority: high
implementation: ["harness/session.py", "harness/cli.py", "harness/project_md.py", "harness/repo_memory.py", "harness/system_builder.py", "harness/task_store.py", "harness/experiment_store.py", "harness/multi_tests.py"]
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

### [REQ-2] Executable acceptance — the plan must emit a RUNNABLE system-level oracle, not prose  (PARTIAL — robust derivation DONE, TASK-6)

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
- [x] Robust derivation, unblocking done-ness on a WORKING system — **DONE 2026-07-03** (`harness/system_builder.py`
  `_derive_acceptance_checklist`/`_is_executable_check`/`_smoke_checklist`, TASK-6): MEASURED (docs/GAP-MAP.md) that
  systems SHIP but report `done=False` because the model's proposed checks are vague/"conceptual" prose (no real
  assertion) or the checklist doesn't parse at all. Proposed checks are now DETERMINISTICALLY FILTERED — a check
  survives only if its `code` parses (`ast.parse`) AND contains a real `assert`; an unparseable/all-filtered first
  attempt gets exactly ONE stricter retry (demanding only runnable Python, no prose); if still nothing survives, a
  deterministic SMOKE checklist (every module imports without error and each exported name is actually present)
  is synthesized instead. HONEST (Tenet 3): filtering + the smoke fallback never manufacture a pass — the smoke
  check is itself a real import+assert that genuinely FAILS on a broken system (proven: an import-time exception
  is honestly reported unmet, not swallowed); an empty checklist (only possible with zero modules, which
  `validate_plan` already forbids) still never counts as done. Proven OFFLINE (`tests/test_ext036_acceptance.py`,
  canned llm, no live model — filtering, the bounded retry, and the smoke fallback's honest pass/fail).

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

### [REQ-5] Cross-level repair + scale  (PARTIAL — module-body-level repair DONE, TASK-5)

When end-to-end fails, route the failure to the right level (re-plan vs re-interface vs re-implement vs
re-integrate) and repair there. Then push scale (H) past 4 modules. Requirements here will be discovered by
building REQ-1..4 and recording what breaks.

#### Acceptance Criteria
- [x] MODULE-BODY-level repair driven by acceptance-check feedback — **DONE 2026-07-03, CORRECTED
  2026-07-03** (`harness/system_builder.py::build_system`'s bounded system-level repair loop, TASK-5):
  when the derived acceptance checklist has unmet checks, each failing check's code + run error + the
  CURRENT module sources are fed to the model for a TARGETED fix (which module + its corrected complete
  content); the fix is syntax-gated (reusing `syntax_ok`/the syntax-repair prompt), applied, and the
  FULL checklist re-run, bounded to `max_repair=2` rounds. Honest (Tenet 3): `done` still requires the
  full checklist to pass; an already-done build skips repair (0 rounds). CORRECTION (architect review
  caught a Tenet-3 defect, not committed): "non-degrading" was documented but NOT enforced — the guard
  compared unmet COUNT only, so a targeted fix for one check could silently SWAP in a regression on a
  different, previously-passing check (same count, different set) and that regression would ship
  unrolled-back. FIXED: each round now snapshots pre-round module sources + the unmet SET; if any
  check that passed before the round now fails (a set-based regression), the round's module write(s)
  are REVERTED to their pre-round content and the loop stops, rejecting that round — best-seen
  `(built, unmet)` is tracked and returned, so repair now REALLY only improves or leaves `unmet`
  unchanged, never regresses a previously-passing check. Proven OFFLINE
  (`tests/test_ext036_system_repair.py`, canned llm incl. a dedicated swap-regression case, no live
  model). CAVEAT: this always targets a module BODY — it is not yet a general failure-LEVEL classifier
  that can instead route a failure to re-plan / re-interface / re-integrate; that broader classifier
  remains open (below).
- [ ] A failure-LEVEL classifier that routes a failure to re-plan vs re-interface vs re-implement vs
  re-integrate (not just always module-body repair) — open
- [ ] (to be discovered) scale past ~4 modules with sustained end-to-end pass — open

---

## EXPANDED CAPABILITY SUITE (owner directive 2026-07-03) — "be like Claude Code"

The owner expanded the target: to build complex systems well, jaros-code must also do the surrounding agentic
work Claude Code does. Many gaps — recorded here, filled iteratively (each surfaces naturally as the
sentence-to-system pipeline demands it). Cross-cutting ones (REQ-8..11) may spin out to their own specs.

### [REQ-6] Multi-level test generation — unit / integration / performance  (PARTIAL — integration_check/perf_check DONE, TASK-10)

Beyond the unit-test capability (EXT-005 write-tests, mutation-graded): generate INTEGRATION tests (do the
assembled modules work together across boundaries?) and PERFORMANCE tests (does it meet a throughput/latency
bar?). Each honestly graded (integration: real cross-module behavior; performance: measured against a threshold).

#### Acceptance Criteria
- [x] Integration-test generation for a multi-module system (exercises real cross-module flows, not just one unit)
  — **DONE 2026-07-03** (`harness/multi_tests.py::integration_check(modules, root, flow_code=None, llm=None)`):
  assembles the `{name: code}` modules onto `root` and RUNS a standalone cross-module scenario (a script
  importing >=2 modules and asserting a real interaction between them, reusing the same guarded
  `harness.multi_file._run` runner the acceptance checklist uses). When `flow_code` is omitted a narrow model
  call (`_derive_flow_code`) proposes one best-effort; the RUN itself is always deterministic. Honest (Tenet 3):
  a broken cross-module interaction genuinely fails, surfacing the real run output — never coerced to a pass.
- [x] Performance-test generation (measures + asserts a threshold; honest, not a trivially-passing stub) —
  **DONE 2026-07-03** (`harness/multi_tests.py::perf_check(modules, root, entry_cmd, threshold_s)`): runs
  `entry_cmd` in `root` and MEASURES real wall-clock elapsed time (`time.perf_counter`); `passed` requires
  both a real successful exit AND `elapsed <= threshold_s` — a genuinely slow (or failing) run genuinely fails,
  never estimated or coerced to green. Proven OFFLINE with a real fast (`python -c "pass"`) vs. a real
  deliberately slow (`sleep(2)` against a 0.5s threshold) subprocess run.
- [ ] Composed into the sentence-to-system pipeline: a built system gets unit + integration (+ perf where
  relevant) tests — open. `build_system` was intentionally left UNMODIFIED for this task (TASK-10's scope) to
  keep the TASK-4/5/6 acceptance/repair-gate tests byte-identical; wiring `integration_check`/`perf_check` into
  `build_system` as opt-in advisory fields is a follow-up, not yet done. Proven OFFLINE
  (`tests/test_ext036_multitests.py`, no live model needed for the core; the flow-derivation path is exercised
  with a canned stub `llm`): a cooperating 2-module integration flow passes and genuinely fails when a module is
  broken, `perf_check` passes a fast entry and genuinely fails a deliberately slow one (real measured time), and
  both functions never raise on bad/missing input (None modules, missing flow/entry, an unusable root).

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

### [REQ-12] CLI UX parity with Claude Code  (PARTIAL — conversational session + resume backbone DONE, TASK-1; mid-task steering / inline ask / streaming remain)

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

### [REQ-14] Modification from a sentence — evolve an existing system  (PARTIAL — regression-gated modify_system DONE, TASK-7)

Not just create — MODIFY an existing codebase from a sentence ("add rate-limiting to the shortener", "make the CSV
CLI also output median"). Compose the existing edit capabilities (fix/edit/refactor/multi_file + repo-context REQ-10):
locate the relevant code, plan the change, apply, re-validate (done-ness) that the modification is complete + didn't
break existing behavior (regression-gated).

#### Acceptance Criteria
- [x] Given an existing system + a modification sentence, locate the change site(s) and apply the change — **DONE
  2026-07-03** (`harness/system_builder.py::modify_system(modules, mod_sentence, root, *, llm=None)`, TASK-7):
  composes the CREATE pipeline's PROVEN pieces (`syntax_ok`, `_derive_acceptance_checklist`, `_run_check`) — the
  model (`_identify_targets`) judges which existing module(s) the sentence targets, then regenerates each one WITH
  the change given its current source (`_regenerate_module`), syntax-gated + bounded-repaired (reusing
  `REPAIR_PROMPT`, TASK-4's per-module gate).
- [x] Re-run existing + new acceptance so the modification is validated AND nothing regressed (Tenet 3) — **DONE
  2026-07-03**: a BASELINE acceptance checklist is derived + run on the CURRENT system BEFORE any change, recording
  the set of checks that currently PASS; after the regenerated module(s) are assembled, those baseline-passing
  checks are RE-RUN — mirroring TASK-5's `_repair_system` revert pattern — and ANY regression REVERTS the modified
  module(s) to their pre-modification content (disk + the returned dict), reporting `applied=False` +
  `regressed: [names]`. `applied=True` only when nothing that used to work broke. A best-effort NEW-behavior
  checklist, derived from the mod sentence itself, is also run (`new_behavior_ok`) but is advisory — REQ-14 only
  REQUIRES existing behavior preserved, since the model-authored new-behavior check could itself be wrong. Proven
  OFFLINE (`tests/test_ext036_modify.py`, canned llm, no live model): a clean modification applies, a
  regression-causing modification is reverted (asserted byte-identical to the pre-mod source, both in the returned
  dict and on disk), and unparseable model output at every stage never raises. Wired as `/modifysystem [<dir> ::]
  <sentence>` in `harness/cli.py` (operates on the last `/buildsystem` output by default, or an explicit dir).
- [ ] Measured across difficulty tiers, like REQ-13 — open (this task proves the mechanism on a small canned/live
  case; a held-out difficulty-tier sweep, like REQ-13's, has not been run)

## AGENTIC INFRASTRUCTURE (owner directive 2026-07-03) — the Claude-Code substrate (memory / tasks / experiments / project-file)

Claude Code manages short + long-term memory, condenses context, keeps per-repo memory + a CLAUDE.md sent every
prompt, creates todo tasks + experiments. jaros-code has META-level analogs (this convergence loop uses a task list,
experiments, CLAUDE.md, .claude memory) but must build these INTO the harness for its USERS.

### [REQ-15] Short-term memory management + condensation  (DONE — EXT-036 TASK-11, 2026-07-03)

The session transcript (REQ-12) is short-term memory; when it grows past the small model's budget, CONDENSE it (an
LLM/deterministic summary of older turns) so context stays within budget without losing the thread — Claude-Code's
compaction. Critical for the small model (tiny context window makes this MORE important than for a big model).

#### Acceptance Criteria
- [x] Bounded working-context budget; when exceeded, older turns are condensed into a running summary kept in-context —
  DONE (`harness/session.py::condense(session, llm=None, keep=CONDENSE_KEEP, max_chars=300)`): deterministic budget
  check (`MAX_TURNS=40` on the full transcript); under budget it is BYTE-IDENTICAL to `session.recent()` (no behavior
  change for short sessions); over budget the oldest turns (everything before the most-recent `CONDENSE_KEEP=6`) are
  folded via ONE narrow model call (`_summarize_turns`) into a single `{"role": "summary", "text": ...}` entry, and
  the returned slice is `[summary] + recent turns` — bounded regardless of transcript size. Guarded: any model
  failure (unreachable/empty output) falls back to a deterministic truncation (`_fallback_truncate`), never raises.
  Wired into `harness/cli.py::handle()`'s history-injection path (replacing the raw `session.recent()` call) so the
  router always receives the condensed view once over budget, the raw recent turns otherwise.
- [x] Condensation preserves task-relevant facts (measured: a follow-up needing an old fact still resolves post-condense)
  — DONE, proven OFFLINE (`tests/test_ext036_condense.py`, canned llm summary, no live model): a fact stated in an
  old (now-summarized) turn is present in the canned summary text so it's still injected into the routed request;
  under-budget sessions return raw turns unchanged (and never call the model); over-budget sessions replace the
  oldest turns with a single honestly-labeled `summary` entry while keeping the most-recent turns verbatim, staying
  within a fixed-size bound regardless of transcript size; a model failure (raises, or returns empty text) falls back
  to truncation without raising. Existing `test_ext036_cli_session.py` (TASK-1)/`test_ext036_project_md.py`
  (TASK-2)/`test_ext036_repo_memory.py` (TASK-3) all stay green — condensation is additive and only engages once the
  transcript exceeds `MAX_TURNS`, well beyond those tests' short sessions.

### [REQ-16] Long-term + PER-REPO memory  (DONE — EXT-036 TASK-3, 2026-07-03)

Persistent memory that survives across sessions, SEPARATE per repo the user works on (facts/decisions/preferences for
THIS project). Mirrors the .claude per-project memory model. Small-model-appropriate: recall must be PRECISE (the
retrieval-negative lesson — inject the few relevant facts, not a noisy dump; see memory retrieval-fewshot-negative).

#### Acceptance Criteria
- [x] A per-repo memory store (keyed by repo path/id) persisted under the repo's jaros state — DONE
  (`harness/repo_memory.py::add_fact`/`load_facts`, `<root>/.jaros/memory.jsonl`; bounded read, guarded — never raises)
- [x] Write (capture a durable fact) + precise recall (surface only the few relevant facts into the prompt) — DONE
  (`/remember` persists a fact; `select_relevant` is a NARROW memory-agent judgment mirroring the validated
  `.jaros-data/mem_experiment2.py` selection prompt, wired into `harness/cli.py`'s plain-language routing as a
  `RELEVANT MEMORY:` block, after `PROJECT INSTRUCTIONS:` and before conversation history)
- [x] Isolated per repo; measured that recall helps, not hurts (guard against the noisy-context regression) — DONE
  (store keyed by repo root; ANY failure — no facts, unreachable model, unparseable/out-of-range output — returns
  `[]`, never a bulk dump). Honest caveat: the "recall helps" measurement is the existing live-model probe
  (`.jaros-data/mem_experiment2.py`, MEM-AGENT selective beat RAW-LONG dump on the long-context task this design is
  built from); this task's own tests are OFFLINE (stubbed selection, no live model) per its testing constraint, so a
  fresh live-model re-measurement of this exact wiring has not been re-run here.

### [REQ-17] Project-instructions file auto-injected every prompt (JAROS.md ≈ CLAUDE.md)  (DONE — EXT-036 TASK-2, 2026-07-03)

A per-repo `JAROS.md` (project instructions/conventions) that is loaded and injected into the agent's context on
EVERY user prompt, so the system always honors the project's rules — exactly like CLAUDE.md.

#### Acceptance Criteria
- [x] `JAROS.md` (per repo) is discovered + loaded; its content is injected into the solve/route prompt every turn —
  **DONE 2026-07-03** (`harness/project_md.py::load_project_md`, discovers repo-root `JAROS.md` falling back to
  `.jaros/JAROS.md`; injected via `harness/cli.py::_augment_with_history` as a `PROJECT INSTRUCTIONS:` preamble
  ahead of conversation history on every plain-language + `_nl_fix` turn)
- [x] Bounded (fits the small context); absent file is a graceful no-op — **DONE 2026-07-03** (bounded to
  `MAX_CHARS=2000`; absent/unreadable file returns `""` and leaves the request byte-identical)

### [REQ-18] TODO task creation + management (user-facing)  (DONE — EXT-036 TASK-8, 2026-07-03)

The system creates + tracks todo tasks for the user's work (decompose a request into tracked steps, mark progress),
like Claude Code's task list — surfaced in the CLI.

#### Acceptance Criteria
- [x] Create/list/update tasks tied to the session/repo; the model can propose a task breakdown for a request —
  DONE (`harness/task_store.py::add_task`/`list_tasks`/`update_task`, a per-repo store at
  `<root>/.jaros/tasks.jsonl`, deterministic + guarded, never raises; statuses pending/in_progress/done.
  `propose_tasks(request, llm=None)` is the ONE narrow model call that decomposes a request into 2-6 concrete
  task strings — a JSON-list parse, `[]` on any model failure or unparseable output, never fabricates a
  breakdown)
- [x] Surfaced in the CLI UX (REQ-12); persisted with the session/repo — DONE: `/task <text>` adds a task,
  `/tasks` lists them (id + status), `/task done <id>` / `/task doing <id>` update status
  (`harness/cli.py::cmd_task`/`cmd_tasks`). Proven OFFLINE (`tests/test_ext036_tasks.py`, canned llm, no live
  model): add/list/update round-trip + per-repo isolation + status transitions, `propose_tasks` returns the
  stubbed breakdown and `[]` on unparseable output, the CLI commands work end-to-end, and slash-command
  dispatch/output is unaffected by stored tasks.

### [REQ-19] Experiment creation + management (user-facing)  (DONE — EXT-036 TASK-9, 2026-07-03)

The system can create + run experiments for the user (hypothesis → run → measure → record), like this convergence
loop does at the meta level — exposed as a first-class user capability.

#### Acceptance Criteria
- [x] Define an experiment (what to run, how to measure), run it, record the result against the hypothesis —
  DONE (`harness/experiment_store.py::define_experiment`/`run_experiment`, a per-repo store at
  `<root>/.jaros/experiments.jsonl`, deterministic + guarded, never raises. `run_experiment` executes the
  experiment's `run_cmd` via a REAL guarded subprocess (Popen + tree-kill on timeout, mirrors
  `harness/multi_file.py::_run`) in `root` — never fabricated; a failing/hanging command records the real
  non-zero exit code + a bounded output tail, honestly, never silently upgraded to a pass)
- [x] Results persisted (per-repo) + surfaced; reusable across sessions — DONE: `/experiment <hypothesis> ::
  <run_cmd>` defines an experiment, `/experiments` lists them (id + status + last exit code), `/experiment run
  <id>` actually runs it and reports the real exit code/output (`harness/cli.py::cmd_experiment`/`cmd_experiments`).
  Proven OFFLINE (`tests/test_ext036_experiments.py`, no model needed — trivial real `python -c
  "...sys.exit(N)"` run_cmds): define/list/run round-trip + per-repo isolation, a passing run_cmd records
  exit_code 0 and a failing one records the real non-zero exit code, a hanging command is guarded by a short
  timeout without raising, the CLI commands work end-to-end, and slash-command dispatch/output is unaffected.
