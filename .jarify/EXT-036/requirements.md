---
id: EXT-036
title: Sentence-to-System — build a complex Python system from a one-sentence spec (Claude-Code-parity)
status: partial
priority: high
implementation: ["harness/session.py", "harness/cli.py", "harness/project_md.py", "harness/repo_memory.py", "harness/system_builder.py", "harness/task_store.py", "harness/experiment_store.py", "harness/multi_tests.py", "harness/ask_user.py", "harness/system_suite.py", "harness/modification_suite.py", "harness/server_oracle.py", "harness/coherence_suite.py", "harness/episodic_memory.py"]
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
- [x] Deterministic coherence validator (DAG/signatures/imports/entrypoint) — probed, all three pass.
  **FIXED 2026-07-04 (TASK-34):** MEASURED LIVE that the imports check false-positived on STDLIB imports
  (e.g. `sqlite3`) — any module listing a standard-library import was flagged `imports unknown '<name>'`
  and the whole plan rejected, blocking the datastore/DB-backed system class (`notes-sqlite-cli`).
  `validate_plan` now exempts an import from that defect when its top-level name
  (`imp.split(".")[0]`) is in `sys.stdlib_module_names`, while a genuinely-missing LOCAL module
  reference is still flagged exactly as before (value-preserving; proven in
  `tests/test_ext036_system_builder.py`).
- [~] A plan-repair loop: when the validator finds defects, feed them back for a coherent re-plan (analog of the write-tests repair loop) — **PARTIAL, 2026-07-03 (TASK-19)**: MEASURED
  (`.jaros-data/diag_residuals.py`) that 4/5 creation-suite residuals hit the SAME defect — gemma's plan lists
  exactly ONE module but sets `entrypoint` to a DIFFERENT filename it clearly intends as the entrypoint (just
  named its lone module descriptively) — so `validate_plan` correctly rejects it and 0 modules build.
  `harness/system_builder.py::_repair_plan_entrypoint`, called before the `validate_plan` gate, DETERMINISTICALLY
  repairs this specific, unambiguous single-module case (renames the sole module to the entrypoint filename) — a
  deterministic repair, not a model-feedback re-plan call, and only for this one defect shape. A genuinely
  incoherent MULTI-module plan with a mismatched entrypoint is left untouched (ambiguous which module should host
  it) so it still fails coherence exactly as before — no regression, no silent wrong guess. Proven OFFLINE
  (`tests/test_ext036_planrepair.py`, canned llm, no live model). CAVEAT (honest scope): this fills only the ONE
  measured defect shape; a GENERAL re-plan-on-defect loop that feeds arbitrary validator defects back to the model
  for a fresh plan (the broader criterion) remains open.
  **EXTENDED 2026-07-04 (TASK-36):** MEASURED LIVE, 6/6 identical draws — for the notes-sqlite-cli task,
  gemma deterministically draws a 2-module plan (e.g. `cli.py` + `main.py`) where `cli.py` lists an import
  of a LOCAL module (e.g. `database`) never added to the plan's module list, so `validate_plan` correctly
  rejects the whole plan (`imports unknown 'database'`) — 0 modules build. Deterministic, so best-of-k
  cannot help. `harness/system_builder.py::_repair_plan_dangling_imports`, called right after
  `_repair_plan_entrypoint` and before the `validate_plan` gate, scans every module's `imports` and
  ADDITIVELY generates a module entry for any import that is neither a listed local module nor stdlib
  (`sys.stdlib_module_names`, the TASK-34 exemption) — never renaming/removing anything the model
  planned. Proven OFFLINE (`tests/test_ext036_system_builder.py`, canned llm, no live model): the dangling
  import is repaired and the coherence gate passes; a stdlib import is left completely untouched (no
  bogus module); an already-coherent plan is an idempotent no-op; the added module's exports satisfy
  `validate_plan`'s shape checks; malformed/edge-case plan shapes never raise; and an end-to-end
  `build_system` run on the exact measured shape now SHIPS all three modules instead of being rejected.
- [ ] Measured on a held-out set of sentences; coherence-pass rate reported honestly

### [REQ-2] Executable acceptance — the plan must emit a RUNNABLE system-level oracle, not prose  (PARTIAL — robust derivation DONE, TASK-6; false-done in the smoke fallback for stateful CLIs closed, TASK-35)

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
- [x] Close a MEASURED false-done in the smoke fallback for STATEFUL CLIs — **DONE 2026-07-04** (`harness/system_builder.py`
  `SUBPROCESS_CHECKLIST_PROMPT`/`_is_subprocess_check`/`_propose_subprocess_checklist`, TASK-35): the caveat above
  ("the smoke check ... genuinely FAILS on a broken system") is TRUE for import-time errors but was measured
  LIVE to be INCOMPLETE for a CLI whose primary command crashes only when actually invoked — building
  `notes-sqlite-cli` fell through to `_smoke_checklist` (asserts only `import <module>` + `hasattr(module,
  export)`, never calling an exported function or driving the module's `if __name__ == "__main__":` dispatch)
  and reported `done=True` even though a genuinely fresh `python main.py add ...` crashed
  (`sqlite3.OperationalError: no such table: notes` — `add` calls `insert_note()` without ever calling
  `initialize_db()` first). A NEW third derivation tier is now tried between the strict-retry tier and the smoke
  fallback: the model proposes checks that invoke the system's own declared entrypoint as a REAL SUBPROCESS
  (`subprocess.run`/`check_output`/`check_call`/`Popen`, never an in-process `import`), deterministically filtered
  (`_is_subprocess_check` — real executable check AND a genuine `subprocess.*` call in its AST) so it can never
  fabricate a pass; returns `[]` on any model/parse failure and falls through to the SAME smoke fallback as
  before (no regression to any build whose first two tiers already produce a usable checklist, or whose model
  can't produce a subprocess check). Proven OFFLINE (`tests/test_ext036_acceptance.py`, canned llm, no live
  model): the two-sided property — a fixture reproducing the bug CLASS generically (a CLI `add` branch that
  writes to a store without initializing it, not sqlite-specific) now yields `done=False` (closing the
  false-done, with an independent plain-subprocess control confirming the crash is real, not a sandbox
  artifact), while the SAME derivation path yields `done=True` once the CLI is fixed (no new false negative);
  the pre-existing smoke-fallback tests are unchanged (the canned llm's default `"[]"` response to the new tier
  is a no-op continuation to smoke, exactly as before this task).

### [REQ-3] Per-module oracle generation — reuse the write-tests capability to gate each module build  (GAP)

`build_from_intent` is oracle-gated (needs a per-module test), but the plan gives only responsibility+signature.
DISCOVERED gap: generate a per-module oracle from responsibility+signature (compose the NEW write-tests
capability, EXT-005 TASK-6/8) so each module builds against a real test, not just free generation.

#### Acceptance Criteria
- [ ] For each planned module, derive a per-module oracle test from its responsibility+signature
- [ ] `build_from_intent` builds each module gated on that oracle; sibling signatures supplied as context

### [REQ-4] End-to-end: plan → ordered build → wire → assemble → acceptance  (PARTIAL — productionized in build_system, TASK-4; live simple/medium ship; complex fast-fails at plan stage = 7B/reasoning frontier)

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

### [REQ-7] Done-ness validation — is the system complete vs the spec, or not?  (PARTIAL — build_system derives an acceptance checklist + reports DONE/unmet, TASK-4/6; caveat: model writes checks from same spec — independent-oracle rigor remains)

A judgment + deterministic evidence that the built system SATISFIES the original sentence (all implied
requirements covered), and an honest "NOT done — here's what's missing" when it doesn't. Builds on the
ship-gate + executable acceptance, but at the SPEC level (did we build what was asked?), not just per-module.

#### Acceptance Criteria
- [x] Derive the acceptance criteria from the spec (spec-expansion → checklist of implied requirements) — **DONE 2026-07-03**
  (probe: sentence → 4 implied-requirement checks: round-trip, uniqueness, stability, resolution accuracy)
- [x] Validate each against the built system; report DONE only if all pass, else list unmet items — DONE (reports
  "DONE (all pass)" or "NOT DONE — unmet: <list>"). Same Tenet-3 caveat as REQ-2 (model-written checks; add independence).

### [REQ-8] Ask-the-user when needed — clarify ambiguity  (DONE — EXT-036 TASK-12, 2026-07-03)

When the spec is ambiguous or under-determined, ASK the user a targeted question rather than guessing (Claude
Code's AskUserQuestion). Requires a judgment (is this genuinely ambiguous?) + an interaction channel.

#### Acceptance Criteria
- [x] A grounded judgment that detects genuine ambiguity (not asking when a sensible default exists) — **DONE
  2026-07-03** (`harness/ask_user.py::detect_ambiguity(request, llm=None)`): ONE narrow, CONSERVATIVE model
  judgment that emits a single clarifying question ONLY when the request is genuinely ambiguous, else the literal
  token `NONE`. Deterministic parse (`_parse`): defaults to `None` on an empty request, a missing/failing model
  (any exception), degenerate model output (`NONE`/`N/A`/`NA`/`NO`/empty text), or text that isn't shaped like a
  real question (must end in `?` and be long enough) — under-asking is safer than over-asking (Tenet 3: never
  fabricate a question to seem helpful).
- [x] An interaction channel to surface the question + consume the answer into the plan — **DONE 2026-07-03**
  (`harness/cli.py::JcodeCli._maybe_ask` + `handle(line, *, interactive=False)`): in the INTERACTIVE REPL path
  only (`repl()` calls `cli.handle(line, interactive=True)`), before routing a plain request, `detect_ambiguity`
  is checked; if it returns a question, `_maybe_ask` prints it, reads the answer via `input()`, records the Q+A
  as session turns (best-effort), and folds the answer into the request
  (`"{request}\n\nClarification: {answer}"`) that every downstream routing path (structured agent / deterministic
  intent fast-path / orchestrator) then sees. Headless/one-shot callers (`main()`'s argument path) and `handle()`'s
  default (`interactive=False`) skip the check entirely — never blocks waiting on input(). Slash commands never
  reach this check (it only runs on the non-slash branch of `handle()`). Proven OFFLINE
  (`tests/test_ext036_ask.py`, canned llm + monkeypatched `input()`, no live model, no network):
  `detect_ambiguity` returns the canned question for an ambiguous request and `None` for a clear request / on
  model failure / on empty or degenerate output; the interactive path asks, folds the stubbed answer into the
  routed request, and records both turns in the session, and never raises on an interrupted/empty answer; the
  headless path (default and explicit `interactive=False`) never calls `input()` and never augments the request;
  slash-command dispatch (`handle("/help", interactive=True)` and `dispatch("/status")`) never triggers a
  question.

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

### [REQ-13] Full difficulty spectrum — easy / medium / hard / highly-complex creation  (PARTIAL — escalation core DONE + LIVE-WIRED into the CLI, TASK-13/TASK-18)

Sentence→system must span the whole difficulty range, not just easy. SIMPLE/EASY is PROVEN (REQ-4). Push medium →
hard → highly-complex; the honest break-point at each tier is the recorded gap (likely bites at the reasoning-heavy
tiers, the measured small-model frontier — so expect two-plane scaffolding + roster routing to a stronger Jetson-fit
model, e.g. the queued Qwen2.5-Coder-7B, to be the lever for hard/highly-complex).

**MEASURED (2026-07-03, commit c182c33):** on complex builds gemma-4-e2b ships 2/3 (fully-completes 1) while
Qwen2.5-Coder-7B ships 3/3 but never fully-completes and costs ~3x latency — so routing everything to the 7B is
a bad trade; ESCALATE-ONLY-ON-FAILURE (run the default, only pay for the 7B when the default failed to ship) is
the honest lever, and its offline core is now built.

#### Acceptance Criteria
- [x] easy (proven, REQ-4) — [ ] medium — [ ] hard — [ ] highly-complex, each with a held-out sentence set + honest pass rate
- [ ] The break-point tier is documented with the failing LEVEL (spec/arch/interface/body/integration) and the lever tried
- [x] An offline, test-gated ESCALATION core that runs the default model first and only escalates to a measured
  stronger fallback (e.g. Qwen2.5-Coder-7B) when the default fails to ship, never on a shipped result — **DONE
  2026-07-03** (`harness/system_builder.py::build_system_escalating`, TASK-13): wraps `build_system` without
  modifying it; a shipped primary result returns AS-IS (`fallback_llm`/`swap_fn` never invoked — no latency cost
  on the common case); an unshipped primary escalates via an injectable `swap_fn(model_id)` (mirrors
  `harness.collaborative_solve._http_swap`'s convention) to the fallback build, picks the better result by a
  deterministic rule (shipped > done > module count, primary wins ties), and restores the primary model
  afterward in a `finally` block. Never raises: a `swap_fn`/fallback-build failure gracefully returns the
  primary result. Proven OFFLINE (`tests/test_ext036_escalate.py`, canned/fake llms + a stub `swap_fn`
  recording calls, no live model/network/Jetson).
- [x] LIVE CLI wiring -- the offline mechanism above is now genuinely reachable from the product path, not
  just test-gated -- **DONE 2026-07-03** (`harness/cli.py::cmd_buildsystem` + `_buildsystem_escalation_config`,
  TASK-18): `/buildsystem` calls `_buildsystem_escalation_config()` (registry-driven: "configured" =
  `ModelRegistry.lookup_by_class("complex-system-build-specialist")` -- today qwen2.5-coder-7b -- returns a
  MEASURED id AND a model-manager URL is available, default `http://192.168.1.183:8001`, overridable via
  `JCODE_MODEL_MANAGER_URL`); when configured it routes through `build_system_escalating(sentence, subdir,
  primary_llm=self.llm, fallback_llm=self.llm, swap_fn=collaborative_solve._http_swap(manager_url),
  fallback_model_id=..., primary_model_id=registry.default_model())` -- the injected `swap_fn` re-pointing the
  Jetson's SERVED model is what makes the shared `:8000` client's second call actually run the 7B, mirroring
  the TASK-13 measurement runner. This carries the MEASURED 25%->58% (3/12->7/12) hard-tier ship-rate lift
  into the actual product path. Output now reports which model shipped and whether it escalated (e.g.
  "via qwen2.5-coder-7b (escalated)" vs "via gemma-4-e2b"). NO REGRESSION when unconfigured (no registry /
  no specialist / no manager) -- `cmd_buildsystem` falls back to plain `build_system` byte-for-byte as before,
  and no `swap_fn` is ever constructed on that path. Proven OFFLINE (`tests/test_ext036_buildsystem_escalate.py`,
  no live model/network/Jetson): the configured path calls `build_system_escalating` with the right
  primary/fallback llms + model ids + a real swap_fn (and plain `build_system` is never invoked); the
  unconfigured path calls plain `build_system` and never constructs a swap_fn; CLI output reflects
  escalated-vs-not and the shipping model in both branches; an unreachable-manager (raising) `swap_fn` against
  the REAL `build_system_escalating` never crashes `cmd_buildsystem` (relies on that function's own proven
  never-raise guarantee). CAVEAT (honest scope): the medium/hard/highly-complex held-out sweep, and an actual
  LIVE gemma-vs-escalating measurement run against the grown `FIRST_SLICE` suite (REQ-20), remain OPEN
  follow-ups -- this task wires the routing, it does not re-run the live measurement.

### [REQ-14] Modification from a sentence — evolve an existing system  (PARTIAL — regression-gated modify_system DONE, TASK-7; import smoke-gate hardening DONE, TASK-21)

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
- [x] The regression gate must not miss an import-breaking modification just because the surviving model-derived
  checks never happen to exercise the broken module — **DONE 2026-07-03** (TASK-21, MEASURED BUG found by a live
  multi-file-modification probe): a 2-file system (`statlib.py`+`main.py`) modified to "add a max subcommand"
  produced a `main.py` with `from statlib import max` (a name `statlib` never exports) — `main.py` no longer
  imported AT ALL — yet `modify_system` returned `applied=True, regressed=[]`, because both surviving
  `baseline_passing` checks only ever imported `statlib`, never `main` (the one check that did import `main` had
  already failed on the ORIGINAL system and was excluded from `baseline_passing`). FIX: `harness/system_builder.py`
  now runs a DETERMINISTIC, model-independent import smoke-gate (`_importable_modules`, a guarded
  `python -c "import <stem>"` subprocess per module) both BEFORE modification (`baseline_importable`) and AFTER
  assembling the modified modules; any module importable at baseline that is no longer importable
  (`import_regressed`) triggers the SAME revert path as a behavioral regression (module(s) restored to pre-mod
  content, disk + dict, `applied=False`), merged into the reported `regressed`/`note`. Additive to (never
  replacing) the existing model-derived-check gate; a module NOT importable at baseline never counts, so a
  genuinely-broken start system doesn't cause a spurious revert. Proven OFFLINE (`tests/test_ext036_modify.py`):
  the exact reproduction above now reverts `main.py` and reports `applied=False`; a clean 2-file modification that
  keeps every module importable still applies (no false revert); a module broken at baseline that remains broken
  doesn't trigger a revert by itself; the helper never raises on a bad/missing root. Full `tests/` suite stays
  green (1470 passed, 1 skipped).
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

### [REQ-20] Parity instrument: a broad, DIVERSE, held-out suite of sentence→system CREATION classes  (PARTIAL — framework + first slice, EXT-036 TASK-14; sentences made contract-precise, TASK-15; grown to 12 tasks/classes, TASK-17; grown to 20 tasks / 17 classes incl. a highly-complex tier via `HARDER_SLICE` + `ALL_CREATION_TASKS`, TASK-24, 2026-07-04)

To honestly know whether jaros-code is *"really really good at building complex systems from a sentence"* we need a
broad, DIVERSE, HELD-OUT benchmark of CREATION tasks spanning many classes × difficulty tiers — not the three sentences
(jobqueue/kvstore/pipeline) that happened to be probed. Each task is one sentence + an AUTOMATED executable-acceptance
check, never tuned-on (Tenet 3), so the score reflects GENUINE generic capability. This is THE scoreboard for the
sentence→system frontier: ship-rate + done-rate per class × tier, measured gemma-alone vs the escalating system
(REQ-13). Grow the suite relentlessly.

#### Acceptance Criteria
- [ ] A held-out task set covering many CREATION classes (e.g. CLI tool, REST/HTTP service, ETL/data pipeline, job
  queue, state machine, parser/DSL, cache+eviction, scheduler, pub-sub/event system, plugin system, rate-limiter,
  auth/permission, workflow engine, simulation/game-loop) across difficulty tiers (easy 1-module → medium 2-3 → hard
  4-6 interdependent → highly-complex many-module + cross-cutting) — PARTIAL: `FIRST_SLICE` (TASK-14, grown TASK-17)
  now covers 12 tasks / 9 distinct classes (cli-tool [sum/wordcount/temp-converter/max-of-stdin], todo-list,
  kv-store+TTL, priority job-queue, text-transform, calculator, parser (kv-lines-sorted), pub-sub, rate-limiter)
  across easy/medium/hard (4/4/4, TASK-17 doubled the tier counts); **TASK-24 (2026-07-04) adds `HARDER_SLICE`
  (8 more classes: json-config-validator, graph-bfs-shortest-path, bracket-balance, run-length-codec,
  csv-column-aggregator, traffic-light-sequencer, lru-cache [highly-complex], matrix-transpose) + exposes
  `ALL_CREATION_TASKS = FIRST_SLICE + HARDER_SLICE`, growing coverage to 20 tasks / 17 classes and introducing the
  highly-complex tier** — each self-verified via a reference impl through the independent oracle (a no-op scores
  0/8, so no contract is trivially satisfiable, Tenet 3); the remaining broader classes (REST/HTTP service, plugin
  system, auth/permission, workflow engine, simulation/game-loop, and the many-module highly-complex tier) remain
  open growth.
- [x] Each task = one sentence + a deterministic, automated executable-acceptance check (done / not-done), stored so it
  is never leaked into the solving prompt (held-out; Tenet 3) — **DONE 2026-07-03** (`harness/system_suite.py`,
  TASK-14): each `CreationTask`'s `checks` are BLACK-BOX CLI checks (`(argv, stdin, expected_substring)`, run as a
  real subprocess against the build's declared entrypoint) or a `callable(root, plan)->bool`; the oracle is
  INDEPENDENT of the system under test (never the model's own self-derived acceptance checklist from
  `system_builder._derive_acceptance_checklist`) and only `task.sentence` is ever passed to `build_fn` — the checks
  themselves are never part of the solving prompt.
- [x] A runner that reports ship-rate + done-rate per class × tier, for gemma-alone AND the escalating system, honestly
  — **PARTIAL/DONE (mechanism) 2026-07-03** (`harness/system_suite.py::run_creation_suite`, TASK-14): drives any
  `build_fn` matching `build_system`'s signature (so it composes with `build_system` OR
  `build_system_escalating` unmodified) and reports `{results: [...], aggregate: {overall, by_tier}}` with honest
  ship-rate/done-rate/accept-rate; never raises (a per-task build/exec failure records `accepted=False` and the
  suite continues). CAVEAT: this task builds+proves the runner OFFLINE only — an actual LIVE run measuring
  gemma-alone vs. `build_system_escalating` against this suite has not been executed here; that live measurement
  is an explicit follow-up.
- [x] Starts with a first concrete slice (~5–8 classes across tiers) and is designed to grow — **DONE 2026-07-03**
  (`harness/system_suite.py::FIRST_SLICE`, TASK-14; GROWN TASK-17): originally 6 tasks (2 easy / 2 medium / 2 hard)
  across 6 classes, now DOUBLED to 12 tasks (4 easy / 4 medium / 4 hard) across 9 distinct classes, each a
  self-contained sentence + concrete deterministic checks (no wall-clock-dependent checks — e.g. the kv-store's TTL
  expiry uses a `ttl=0` immediate-expiry case, the rate-limiter uses a fixed request count rather than a timed
  window). `CreationTask`/`run_creation_suite` accept an arbitrary `tasks` list, so growing the slice is additive
  (proven twice now: TASK-15's contract-precision fix and TASK-17's +6 classes both left the oracle mechanism
  untouched). Proven OFFLINE (`tests/test_ext036_suite.py`, no live model): aggregation correctness, a passing
  stub → accepted, a broken/missing-entrypoint stub → not accepted without raising, a raising `build_fn` → that
  task recorded not-accepted and the suite continues, the callable-check path, the grown registry's shape (12
  tasks, 4/4/4 tiers, unique names, at least one deterministic check each), and — new in TASK-17 — a coherence
  test running a genuine correct reference implementation of each of the +6 new tasks through the REAL
  `run_creation_suite` oracle, proving each new task's `checks` are actually satisfiable by (and thus genuinely
  determined by) its stated contract, not trivially-always-true or accidentally unsatisfiable.
- [x] The first slice's task SENTENCES are contract-precise, not merely well-shaped (a prerequisite for the ship/
  accept rates above to reflect genuine model capability rather than sentence ambiguity) — **DONE 2026-07-03**
  (`harness/system_suite.py::FIRST_SLICE`, TASK-15). MEASURED: the first LIVE run of the original TASK-14
  sentences scored 0% accept with an INVERTED tier ordering (easy shipped 0/2, medium/hard 0.5) — a HARNESS bug,
  not a gemma ceiling (`.jaros-data/hyp_precise_sentence.py`, `.jaros-data/debug_suite_v2.py`): vague sentences let
  gemma (1) plan an entrypoint filename that wasn't one of its own listed modules, so `validate_plan` correctly
  rejected the plan and 0 modules built, and (2) ship a CLI surface different from what the fixed `checks`
  assumed, so the independent oracle correctly couldn't match it (a false negative, not a real failure). FIX: all
  6 sentences now pin a single entrypoint file named `main.py`, the exact invocation (argv or a precise line-based
  stdin command protocol), the exact stdout format including the trailing newline, and the `if __name__ ==
  "__main__":` requirement; `checks` were re-aligned to each rewritten contract exactly. Honest (Tenet 3): this is
  NOT leakage — the sentence IS the spec the independent, held-out oracle checks against, and the model still has
  to build a genuinely working system that satisfies it, not the checks themselves. Also added a minimal, GENERIC
  (not task-specific) fallback in `_run_single_check`: if the plan-declared entrypoint doesn't resolve, but
  `root/main.py` exists (the convention every sentence now states), the oracle runs that instead — still a real
  file that must actually run successfully, never a fabricated pass. Proven OFFLINE (`tests/test_ext036_suite.py`,
  full `tests/` 1359 green, no live model). CAVEAT: this task fixes the measured harness-precision bug; the actual
  LIVE gemma-alone / escalating-system re-measurement against the fixed suite remains the next follow-up.

### [REQ-21] Parity instrument: matching sentence→system MODIFICATION classes (edit an existing complex system)  (PARTIAL — framework + first slice, EXT-036 TASK-16; grown to 10 tasks/harder change classes, TASK-20, 2026-07-03)

The harder, more realistic parity target: modify an EXISTING working complex system from a one-sentence change (most
real dev is editing, not greenfield). For each (or a subset of) the CREATION-suite systems, a matching MODIFICATION
task: start from a built system, apply a one-sentence change, verify via regression-gated automated acceptance (the new
behavior holds AND nothing previously-working regressed). Reuses `modify_system` (REQ-14).

#### Acceptance Criteria
- [ ] A held-out set of MODIFICATION tasks covering many change classes (add a feature, change a behavior, add a
  constraint/validation, add a new backend/adapter, extend an interface, add error handling, add a pipeline stage, swap
  an algorithm, add caching, add a CLI subcommand) across difficulty — PARTIAL: first slice (TASK-16) covered 5 tasks
  (add-a-derived-field, add-a-target-unit, add-a-CLI-subcommand ×2), all simple ADD-a-feature edits. **GROWN 2026-07-03
  (TASK-20)** per PRIME-001's ratchet (an eval suite the harness can ace with a simple append is too easy to stay
  informative): `FIRST_SLICE` now has 10 tasks (3 easy / 4 medium / 3 hard) across 5 harder CHANGE classes not
  covered before — behavior CHANGE (a line-sort CLI: ascending → descending), constraint/validation TIGHTENING (a
  key=value store: reject keys >8 chars), algorithm SWAP (running average → running median), branch/stage ADDITION
  to existing logic (a +/- calculator gains */÷), and a CROSS-CUTTING edit (a multi-command CLI gains an optional
  `--verbose` flag whose default-mode output must stay byte-identical) — plus the original 5 ADD-a-feature tasks.
  The remaining broader change-class list above (new backend/adapter, extend an interface, error handling, pipeline
  stage, caching) remains open growth, mirroring REQ-20's growth path.
- [x] Each task = an existing working system + one sentence + an automated done-ness check AND a no-regression check
  (Tenet 3, held-out) — **DONE 2026-07-03** (`harness/modification_suite.py`, TASK-16): `ModificationTask.start_system`
  is a small, hand-written, KNOWN-GOOD fixture (never model-built — isolates modification from creation), written onto
  a fresh temp root BEFORE `modify_fn` runs; `new_checks`/`regression_checks` are INDEPENDENT black-box CLI checks
  (`(argv, stdin, expected_substring)`), run against the resulting root by REUSING
  `harness.system_suite._run_single_check` (no duplicated oracle logic). `accepted`/`no_regression` are decided by the
  suite's OWN oracle, never by trusting a `modify_fn`'s self-reported `applied` flag — proven with a dedicated test
  where a stub `modify_fn` dishonestly claims `applied=True` while having broken a regression check, and the suite
  correctly rejects it (`accepted=False`) regardless.
- [x] A runner reports per-class modify-success rate + no-regression rate, gemma-alone vs escalating, honestly —
  **PARTIAL/DONE (mechanism) 2026-07-03** (`harness/modification_suite.py::run_modification_suite`, TASK-16): drives
  any `modify_fn` matching `modify_system`'s positional signature (`modify_fn(modules, mod_sentence, root)`, callers
  bind `llm` via a partial/wrapper — model-agnostic), reports `{results: [...], aggregate: {overall, by_tier}}` with
  honest accept-rate/new-behavior-rate/no-regression-rate/applied-rate; never raises (a per-task modify/exec failure
  records `accepted=False` and the suite continues). CAVEAT: this task builds+proves the runner OFFLINE only — an
  actual LIVE run measuring gemma-alone vs. an escalating modifier against this suite has not been executed here;
  that live measurement is an explicit follow-up. Proven OFFLINE (`tests/test_ext036_modsuite.py`, no live model):
  aggregation correctness, a correct modification → accepted, the critical regression-gate case (new behavior applied
  but a regression check broken) → not accepted even when the modify_fn dishonestly self-reports success, a
  failed-to-apply modify_fn → not accepted without raising, a raising modify_fn → that task recorded not-accepted and
  the suite continues, the first-slice registry's shape, and an internal-coherence sanity check (a straightforward
  correct implementation of each first-slice task's own `mod_sentence` satisfies its own checks — now covering all 10
  tasks including the 5 harder change classes added by TASK-20, plus a dedicated regression-gate test proving the
  honesty gate rejects a dishonestly-self-reported `applied=True` modification on one of the harder tasks too, not
  just the original TASK-16 fixture).

### [REQ-22] Server/HTTP acceptance oracle for REAL web-service builds  (DONE — deterministic oracle module built, EXT-036 TASK-23; wired into build_system, TASK-25, 2026-07-04)

**Owner directive (2026-07-03):** the crown-jewel lever for building REAL framework systems is that the product
must actually VERIFY a web service, not hollow-pass it. MEASURED (verify-don't-assume): `harness/system_builder.py`
`build_system`'s acceptance checklist derives checks and runs each via `_run_check`, which executes `python
<entry>.py` and inspects STDOUT. A FastAPI/Flask service has no stdout — it blocks serving HTTP — so every
model-proposed check for it gets FILTERED OUT by the executable-check gate and the build silently falls back to
`_smoke_checklist` (`import main; assert hasattr(main, "app")`), which passes the instant the module IMPORTS,
WITHOUT EVER STARTING THE SERVER OR HITTING A SINGLE ENDPOINT. A gemma-built FastAPI service (correct code,
genuinely serves HTTP) was measured to get `done=True` "all acceptance checks pass" with zero endpoints exercised
— a Tenet-3 hollow pass on exactly the class of system this product most needs to nail.

#### Acceptance Criteria
- [x] `harness/server_oracle.py::detect_web_service(modules)` — best-effort, never-raise scan of module SOURCES
  ({filename: code}) that returns `{"kind": "asgi"|"wsgi", "entry": <module stem>, "app": <attr name>}` for the
  first module where a FastAPI/Starlette (ASGI) or Flask (WSGI) app object assignment + matching import are both
  found, else `None` — DONE, TASK-23
- [x] `harness/server_oracle.py::serve_and_check(root, service, http_checks, *, startup_timeout, request_timeout)`
  — actually STARTS the detected app (uvicorn for ASGI, the Flask CLI for WSGI) on a FREE ephemeral localhost
  port, POLLS the port until it binds (bounded by `startup_timeout`, returns honestly if the server dies first),
  then runs each `http_check` (`method`, `path`, optional `status`/`json_contains`/`body_contains`) as a REAL HTTP
  request via urllib and grades it — DONE, TASK-23
- [x] Every launched server process (and descendants) is torn down in a `finally` block, no orphaned
  uvicorn/flask process, on both the pass path and every failure path — mirrors
  `.jaros-data/tools/shell_exec_tool.py::_kill_tree` (Windows: `taskkill /F /T /PID`; POSIX: signal the process
  group) — DONE, proven with real fastapi + flask + uvicorn fixtures (`tests/test_ext036_server_oracle.py`, no
  network beyond 127.0.0.1)
- [x] Honest negative proof: a check demanding a WRONG expected value genuinely FAILS (proves the oracle really
  inspects the response, not a trivial pass); a broken app (import-time crash) fails within `startup_timeout`
  WITHOUT HANGING and leaves no orphan — DONE, proven OFFLINE
- [x] Wired into `harness/system_builder.py::build_system` so a real system build with a detected web service is
  actually HTTP-verified end-to-end instead of silently falling back to the import-only smoke checklist —
  **DONE 2026-07-04** (`harness/system_builder.py::build_system`, TASK-25): immediately after ASSEMBLE,
  `detect_web_service(built)` is called; when it finds a service, the model proposes HTTP endpoint checks from
  the SPEC (`_derive_http_checklist`, deterministically filtered by `_is_http_check` to well-formed dicts that
  assert at least one of `status`/`json_contains`/`body_contains` — mirroring `_is_executable_check`'s
  parse-and-assert gate), and `done` is now GATED on a real `serve_and_check` pass — the stdout-based
  checklist / import-only `_smoke_checklist` is NEVER reached for a detected web service, closing the hollow-pass
  gap. HONESTY (Tenet 3): if no valid `http_checks` can be derived, `done=False` with an explicit "not
  HTTP-verified" note/unmet entry (`shipped` may still be True — the code assembled + imports fine, but `done`
  never lies). Non-web-service builds are byte-for-byte unaffected — `detect_web_service` finds nothing in a
  plain CLI system, so the pre-existing stdout/smoke acceptance path is reached exactly as before (proven: the
  full creation-suite/system_builder test path stays green at the same behavior). Proven OFFLINE
  (`tests/test_ext036_system_builder.py`, canned llm + a real FastAPI/uvicorn fixture, no live model, no network
  beyond 127.0.0.1): a correct single-module FastAPI service with a derivable `/health` check → `shipped=True,
  done=True`, HTTP-verified; the SAME flow with a BROKEN app (wrong JSON body) → `done=False` (a genuine control,
  not a coincidental pass); a service with no derivable `http_checks` → `done=False` with the honest
  "not HTTP-verified" note (never a hollow `done=True`); a normal non-web CLI build (the pre-existing canned-llm
  fixture) is unchanged (`done=True` via the stdout/smoke path, the new HTTP-checklist prompt is never even
  issued). Full `tests/` suite stays green (1507 passed, 1 skipped, up from 1503/1).

### [REQ-23] Long-horizon build coherence instrument  (PARTIAL — minimal first version DONE, EXT-036 TASK-26; GOVERNED build path (the LIFT mechanism) DONE, EXT-036 TASK-27; LIVE-CAUGHT defects fixed, EXT-036 TASK-28; NO-REGRESS FLOOR hardened end to end, EXT-036 TASK-29; task slice HARDENED with a HARD_SLICE, EXT-036 TASK-30; median-of-k STABILITY option added, EXT-036 TASK-31, 2026-07-04)

**Owner directive (2026-07-04):** PRIME-001 intent capability (g), the LONG-HORIZON BUILD COHERENCE instrument, is
the north-star measurement. The creation suite (REQ-20) and modification suite (REQ-21) each measure ONE
single-behavior prompt end to end (shipped/done/accepted y-or-n) — neither measures whether a build STAYS ALIGNED
across a LARGE, MULTI-REQUIREMENT ask without drift. Before building the full jarify-native
decompose->task->alignment-gate loop that would LIFT this number, the harness needs the INSTRUMENT that measures
coherence honestly: given a prompt stating N distinct requirements, how many does the built system actually
satisfy (each independently, black-box verified), and by how much did it drift? That number ranks which planes
matter for the follow-on capstone build.

#### Acceptance Criteria
- [x] A `CoherenceTask` dataclass (`name`, `tier`, `prompt` — one contract-precise sentence/paragraph describing a
  system with N distinct requirements, `requirements` — a list of independent `(req_id, argv, stdin,
  expected_substring)` black-box CLI checks, one per requirement) — **DONE 2026-07-04**
  (`harness/coherence_suite.py::CoherenceTask`). REUSES `harness.system_suite._run_cli`/`_resolve_entry` (the
  SAME proven oracle primitives REQ-20/21 already built and proved) rather than duplicating subprocess-execution
  or entrypoint-resolution logic; `harness/system_suite.py` itself is untouched.
- [x] `run_coherence_suite(build_fn, tasks=None, python_exe=None) -> dict`: builds each task via
  `build_fn(prompt, root)` (same positional shape as `build_system`), independently checks EVERY requirement
  against the built entrypoint, and records per task `requirements_total`, `requirements_satisfied`, `coherence =
  satisfied/total` (the drift/partial signal — NOT all-or-nothing), `all_satisfied`, and `wall_seconds` (the
  build's measured duration, reported only — never a correctness dependency) — **DONE 2026-07-04**
  (`harness/coherence_suite.py::run_coherence_suite`). Aggregates mean coherence + fully-coherent rate, overall
  and per tier. NEVER raises: a build/exec failure records that task's honest `requirements_satisfied=0` and the
  suite continues — proven OFFLINE (a raising `build_fn` never aborts the suite; a non-dict/`None` build result
  is handled without raising).
- [x] A FIRST_SLICE of contract-precise, internally-coherent minute-scale tasks (Tenet 3: a correct reference
  implementation satisfies ALL its requirements) — **DONE 2026-07-04**: 3 tasks (`stats-cli` easy/4 reqs,
  `text-tools-cli` medium/5 reqs, `ledger-cli` hard/5 reqs) across tiers, each a single-file `main.py` CLI
  contract following the same convention `harness.system_suite.FIRST_SLICE` proved (exact argv/stdin invocation,
  exact stdout format, `if __name__ == "__main__":` required). Proven OFFLINE
  (`tests/test_ext036_coherence.py`, no live model): a known-correct reference implementation of each task scores
  `all_satisfied=True`/`coherence=1.0`; a deliberately PARTIAL implementation (satisfying only k of N
  requirements per task, with the unmet requirements genuinely wrong, not just mis-worded) scores `coherence =
  k/N` EXACTLY, proving the instrument measures per-requirement coverage (the drift signal), not an
  all-or-nothing pass; a no-op `build_fn` (writes nothing) scores `coherence=0.0` for every task (no trivial
  pass); aggregate shape (`overall`/`by_tier`, mean coherence, fully-coherent rate) is well-formed, including on
  an empty task list and on a mixed fully-coherent/zero-coherent pair. Full `tests/` suite stays green.
- [x] WIRING the governed decompose->build->independently-verify->re-ground-repair loop that LIFTS the
  coherence number — **DONE 2026-07-04** (`harness/system_builder.py::build_system_governed`, EXT-036
  TASK-27): a NEW function (`build_system`'s existing behavior/signature untouched) that (1) DECOMPOSES the
  prompt's distinct requirements via ONE independent model call — `[{req_id, description, check}]`, each
  `check` an executable acceptance for that ONE requirement, deterministically filtered
  (`_is_executable_check`) + de-duped — the SPEC OF RECORD, kept separate from whatever `build_system`'s own
  self-derived checklist later contains; (2) BUILDS via the existing, unmodified `build_system` pipeline; (3)
  VERIFIES EVERY enumerated requirement independently against the assembled system (reusing `_run_check`),
  never trusting `build_system`'s own `done` verdict; (4) RE-GROUNDS + REPAIRS each unmet requirement with a
  call that feeds the model the FULL requirement list (not just the failing one) plus the current module
  sources, then RE-VERIFIES ALL requirements — a repair that silently re-drops a different, previously-met
  requirement is CAUGHT and the round REVERTED (mirrors TASK-5's `_repair_system` non-degrading guard;
  best-seen `(built, unmet)` tracked), bounded to `max_repair` rounds (default 3); (5) `done` is judged ONLY
  against the independently-decomposed list, never the model's own self-checklist. Returns `{modules, shipped,
  done, requirements_total, requirements_met, unmet: [...], note, rounds}`. NEVER raises. Proven OFFLINE
  (`tests/test_ext036_system_builder.py`, a fake llm mirroring the `_CannedLlm` pattern, no live model): a
  CORE LIFT TEST where the underlying build genuinely drops one of three independently-decomposed requirements
  (mirroring the measured `incr`-dropping defect at small scale) while `build_system`'s own narrow checklist is
  fooled into `done=True` — `build_system_governed` LIFTS `requirements_met` from 2/3 to 3/3 via one re-ground
  repair round, proving the mechanism's whole point; an ANTI-REGRESSION test where a repair round fixes the
  unmet requirement but silently breaks a different, previously-met one is REJECTED (reverted, met-count never
  decreases); an HONESTY test where the repair never actually fixes the requirement stays `done=False` with the
  unmet requirement honestly listed (never a false `done=True`); and a confirmation that `build_system`'s
  existing tests are byte-identical (additive-only). Full `tests/` suite stays green (1533 passed, 1 skipped).
  CAVEAT (honest scope, explicit follow-ups): wiring `build_system_governed` into the `/buildsystem` CLI
  command, and a LIVE gemma-vs-escalating measurement run of `build_system` vs `build_system_governed` against
  a grown, harder `FIRST_SLICE` (e.g. the 11-requirement kvdb-cli that originally measured the 10/11 drop),
  remain open — this task builds + proves the governed mechanism, it does not yet re-run that live measurement.
- [x] FIX the LIVE-CAUGHT regression a first live run of `build_system_governed` measured — **DONE 2026-07-04**
  (`harness/system_builder.py`, EXT-036 TASK-28). MEASURED (a live diagnostic against real gemma,
  `.jaros-data/diag_decompose.py`, verified before fixing): the TASK-27 mechanism 0/11-ed on the 11-requirement
  kvdb-cli — WORSE than plain `build_system`'s own 10/11 — from THREE defects in the raw model output. (A)
  **PARSE BUG:** live gemma emits the decompose list as ONE JSON ARRAY PER LINE
  (`[{"req_id":"R1",...}]` then `[{"req_id":"R2",...}]` on separate lines), which the old single-outermost-bracket
  extractor's greedy match spans across every line at once — not valid JSON — silently parsing to ZERO
  requirements. FIXED: `_extract_requirements_json` tries the single COMBINED array/object case first
  (back-compat), then falls back to a line-by-line scan collecting every parseable JSON array or bare object,
  handling one-array-per-line/multiple-arrays/bare-JSONL alike. (B) **CHECK-INTERFACE MISMATCH (the actual LIFT
  blocker):** gemma's per-requirement `check` assumed an imagined import-and-assert-class API
  (`import main; main.KeyValueStore().set(...)`) that never matches the ACTUAL built system (a stdin-driven CLI,
  `python main.py`), so even a parsed check errored against the real interface and every requirement was falsely
  "unmet." FIXED: requirements are now decomposed AND verified as BLACK-BOX CLI checks
  (`{"argv": [...], "stdin": "...", "expect": "<substring>"}`, in the system's own `python main.py`-reads-stdin
  terms) via `_verify_requirement`, reusing `harness.system_suite._run_cli`/`_resolve_entry` — the SAME proven
  black-box oracle REQ-20/21 already built — never an imagined class API; `_is_blackbox_requirement_check` +
  `_dedup_requirements` deterministically filter/de-dup on this shape, replacing the old
  import-and-assert-class `_is_executable_check` gate for this decomposed list (build_system's OWN self-derived
  checklist, used elsewhere, is untouched). (C) **NO-REGRESS FLOOR:** `build_system_governed` now ALWAYS runs the
  underlying `build_system` pipeline — even when decompose yields zero requirements — so a decompose failure
  degrades to `build_system`'s own shipped/done/modules result rather than a hollow 0-requirement/0-module
  regression; a defensive final check also ensures the returned module set is never smaller than
  `build_system`'s own. Proven OFFLINE (`tests/test_ext036_system_builder.py`, a fake llm mirroring the
  `_CannedLlm` pattern, no live model): the CORE LIFT/anti-regression/honesty tests were adapted to a real
  stdin-driven CLI fixture with black-box (argv/stdin/expect) checks verified via `_verify_requirement` against
  an ACTUAL built `main.py` (proving the verification matches the CLI's real interface); new tests prove
  `_decompose_requirements` parses the ONE-ARRAY-PER-LINE format into ALL N requirements (not 0/1), a single
  combined array still works (back-compat), an old imagined-class `check` shape is correctly dropped by the
  black-box filter (never silently misinterpreted), and an empty/garbage decompose falls back to
  `build_system`'s own shipped=True/done=True result (never a degenerate 0-module regression) when
  `build_system` itself ships. Full `tests/` suite stays green (1537 passed, 1 skipped, up from 1533/1). CAVEAT
  (honest scope): a fresh LIVE gemma re-measurement of `build_system_governed` against the 11-requirement
  kvdb-cli after this fix (the explicit next step to confirm the LIFT actually reaches >= single-pass live), and
  wiring `build_system_governed` into the `/buildsystem` CLI command, remain open follow-ups.
- [x] Make the NO-REGRESS FLOOR actually HOLD end to end (not just on the empty-decompose fallback) —
  **DONE 2026-07-04** (`harness/system_builder.py::build_system_governed`, EXT-036 TASK-29). A LIVE measurement
  (an 11-requirement kvdb-cli) caught a safety-critical gap TASK-28's defect-(C) floor did not close: plain
  `build_system` (single-pass) satisfied 10/11 behavioral requirements, but `build_system_governed`'s re-ground
  REPAIR LOOP — chasing its own unmet requirements (incr/keys) — DAMAGED previously-working behavior (clear/
  usage broke), ending at 8/11 on an independent behavioral check: a genuine regression BELOW single-pass. The
  prior floor only fell back to `build_system` when decompose yielded ZERO requirements; it never compared the
  repair loop's FINAL verified quality against `build_system`'s own initial output, so a repaired-but-worse
  system could ship (and, if a repair round aborted mid-way — e.g. an exception after some of its writes
  already landed on disk, before that round's own end-of-round regression check ran — the loop's in-memory
  bookkeeping could go stale, reporting the pre-round unmet set unchanged while the genuinely-worse system
  shipped on disk). FIXED: `build_system_governed` now captures `build_system`'s own INITIAL output as an
  explicit BASELINE right after assembly (its modules + their verified count against the SAME
  independently-decomposed requirement checks, `_verify_requirement`, computed BEFORE any governed repair
  runs), then — after the repair loop finishes, however it ended — independently RE-VERIFIES the actual
  CURRENT on-disk state FRESH (never trusting the loop's own in-memory bookkeeping). If that final verified
  count is worse than the baseline's, or the final state fails to re-verify at all, it REVERTS: re-assembles
  the baseline's modules back onto `root` (undoing whatever the repair loop left on disk) and returns the
  baseline's own modules/shipped/done/`requirements_met`, with an honest note that governed repair did not
  improve on `build_system` so the single-pass result was kept. This GUARANTEES `build_system_governed` is
  always `max(baseline, governed)` on the independently-decomposed requirement set — never worse than a plain
  `build_system` call. Additive: the existing TASK-28 empty-decompose fallback and the round-level
  non-degrading guard are untouched (defense-in-depth, not replaced). Proven OFFLINE
  (`tests/test_ext036_system_builder.py`, a fake llm, no live model): a dedicated FLOOR test where the initial
  build satisfies only 1 of 3 independently-decomposed requirements and the repair round genuinely regresses to
  0 (one fix silently breaks the previously-working requirement, the other fix is syntactically invalid and its
  repair-retry call RAISES — simulating a live model/network failure — aborting the round mid-way before its
  own end-of-round check runs) — `build_system_governed` returns the BASELINE (`requirements_met=1`, the
  honest baseline unmet set), never the regressed 0-met result, and the actual `main.py` on disk (re-verified
  by running it for real) is the baseline's, not the regressed one. The existing lift test, the round-level
  anti-regression test, the honesty test, the empty-decompose fallback test, the never-raises test, and the
  `build_system`-unchanged confirmation all stay green (unchanged behavior on those paths). Full `tests/` suite
  stays green. HONEST SCOPE (no fabricated lift, Tenet 3): this floor does NOT fix decompose-completeness blind
  spots — a requirement the decompose call never enumerates at all remains invisible to this check set — it
  only guarantees governed never regresses BELOW build_system on the requirements it does check; a live gemma
  re-measurement against the kvdb-cli confirming the floor holds live (`requirements_met >= 10/11`) remains the
  explicit next follow-up.
- [x] Harden the instrument's own TASK SLICE so it stays DISCRIMINATING (never floor/ceiling-ing out) —
  **DONE 2026-07-04** (`harness/coherence_suite.py::HARD_SLICE`, EXT-036 TASK-30). MEASURED: `FIRST_SLICE`
  (stats-cli 4 reqs, text-tools-cli 5, ledger-cli 5) scored `build_system` at coherence=1.00 (saturated); a
  separately-probed 11-requirement interdependent kvdb-cli broke it (single-pass 10/11), showing FIRST_SLICE
  alone had stopped being informative. FIX: `HARD_SLICE` adds 2 "highly-complex"-tier, 11-requirement,
  INTERDEPENDENT tasks — `kvdb-cli` (the proven-discriminating one: set/get/get-missing/delete/exists-yes/
  exists-no/count/keys/incr/clear/usage against an in-memory stdin-driven key-value store) and `taskmgr-cli`
  (a different domain, also interdependent: add/add-increments-id/done/done-missing/list-shows-status/
  list-empty/remove/remove-missing/count-after-remove/pending-count/usage against an in-memory stdin-driven
  task list, where later commands' checks depend on state built up by earlier ones in the same stdin stream).
  `ALL_COHERENCE_TASKS = FIRST_SLICE + HARD_SLICE` is exposed for callers that want the grown set;
  `run_coherence_suite`'s own default stays `FIRST_SLICE` (backward compatible, no behavior change for existing
  callers). Proven OFFLINE (`tests/test_ext036_coherence.py`, no live model): a correct reference
  implementation of EACH `HARD_SLICE` task scores `all_satisfied=True`/`coherence=1.0` (every requirement is
  genuinely satisfiable by a correct program, Tenet 3); a deliberately partial kvdb-cli implementation (8 of 11
  requirements genuinely correct, keys/incr/clear genuinely wrong) scores `coherence=8/11` exactly; a no-op
  `build_fn` scores `coherence=0.0` for every `HARD_SLICE` task; `ALL_COHERENCE_TASKS == FIRST_SLICE +
  HARD_SLICE`; each `HARD_SLICE` task has >=8 requirements; the bare default call still returns
  `len(FIRST_SLICE)` results. Full `tests/` suite stays green (1571 passed, 1 skipped). CAVEAT (honest scope):
  growing `HARD_SLICE` beyond 2 tasks, and a live gemma-vs-escalating measurement run of `build_system`/
  `build_system_governed` against the grown suite, remain open follow-ups.
- [x] STABILIZE the number against single-pass variance with an n>1 (median-of-k) option — **DONE 2026-07-04**
  (`harness/coherence_suite.py::run_coherence_suite`, EXT-036 TASK-31). MEASURED: a live run of the hardened
  `HARD_SLICE` showed single-pass (`repeats=1`) `build_system` is HIGH-VARIANCE on the hard, 11-requirement
  tasks — `kvdb-cli` scored 0/11 on one draw (a fast BROKEN build, ~49s) but 10/11 on another (~158s);
  `taskmgr-cli` hit 11/11 — so a single run is not a stable coherence number. FIX: `run_coherence_suite` gained
  a `repeats: int = 1` parameter; at `repeats<=1` the ORIGINAL single-pass code path runs byte-identically
  (record/aggregate shape unchanged, back-compat guaranteed by literally keeping that code path untouched and
  branching around it, not by refactoring it). At `repeats>1`, each task is built + independently verified
  `repeats` times and the per-task record gains `coherence_median`/`coherence_mean`/`coherence_min`/
  `coherence_max`/`runs` (the per-run `requirements_satisfied` list); the top-level `coherence`/
  `requirements_satisfied`/`all_satisfied` stay the MEDIAN run's own actual values (`statistics.median_low`
  over the per-run satisfied counts, a stable reproducible pick) so existing consumers of those keys get a
  stable central number instead of one noisy draw. BUILD-FAILURE is distinguished from DROPPED-REQUIREMENT via
  a deterministic `build_ok` per run (the resolved entrypoint genuinely exists on disk AND — when the task has
  requirements — at least one was satisfied, i.e. the build produced something runnable at all): a run failing
  that is `build_failed_count`, a run passing it but not satisfying every requirement is
  `dropped_requirements_count` — two different measured failure modes reported separately. The suite-level
  aggregate additionally reports the mean of each task's `coherence_median` (the stable central number) and a
  `build_failure_rate` across all individual runs. NEVER raises: a failed run counts as coherence 0.0 for that
  run, never aborting the suite. Proven OFFLINE (`tests/test_ext036_coherence.py`, no live model, a
  deterministic call-COUNTER stub — never randomness — varying its build across calls): `repeats=1`
  (omitted or explicit) preserves the EXACT pre-TASK-31 record/aggregate shape (asserted via `set(rec.keys())`
  and a full omitted-vs-explicit equality check); an alternating good/build-failed stub under `repeats=4`
  yields `runs == [4, 0, 4, 0]`, `coherence_min/max/mean == 0.0/1.0/0.5`, `build_failed_count == 2`,
  `dropped_requirements_count == 0`; a separate stub whose "bad" draw runs fine but drops exactly one
  requirement yields `build_failed_count == 0`/`dropped_requirements_count == 2` (proving the two failure
  modes are genuinely distinguished, not conflated); a stub that ALWAYS fails (or always raises) scores
  `build_failed_count` equal to `repeats` for every run and `coherence` 0.0 throughout without raising; the
  aggregate's `build_failure_rate`/mean-of-`coherence_median` are checked on a mixed always-good/always-broken
  two-task suite; and both `HARD_SLICE` tasks' reference implementations stay `all_satisfied=True` with 0
  build-failed/dropped runs under `repeats=3`. Full `tests/` suite stays green (1580 passed, 1 skipped, up
  from 1571/1). CAVEAT (honest scope): a fresh LIVE gemma re-measurement of `build_system`/
  `build_system_governed` against `HARD_SLICE` with `repeats>1` (the actual stabilized number this task was
  motivated by) remains an open follow-up — this task builds + proves the instrument's stability mechanism,
  it does not itself re-run that live measurement.

### [REQ-24] Episodic (action+rationale) memory — groundwork + experience-recall for planning  (PARTIAL — store + deterministic recall DONE, EXT-036 TASK-32, 2026-07-04; wiring the planner is an open follow-up)

**Owner directive (2026-07-04):** PRIME-001 intent capability (f) — the system must remember what it did
and WHY, keeping a durable, referenceable record of its actions and the rationale behind them (an
episodic/provenance memory), so that when the user says "do that again" or refers to something done
earlier, it can recall the exact prior work; and while forming a new plan it first retrieves any similar
past work and reconciles the new plan against it — past experience is part of the upcoming plan's
context, not forgotten each run. This is DISTINCT from the existing memory subsystems: REQ-15 condenses
the CURRENT session's own transcript (short-term, in-session); REQ-16 stores durable per-repo FACTS (user
preferences/decisions) selectively recalled by a memory-agent. REQ-24 is a new axis — a chronological log
of DISCRETE ACTIONS the system took (what + why), queryable by similarity, so a planner can retrieve and
reconcile against relevant PRIOR WORK regardless of which session produced it.

**GUARD (Tenet 3, from a measured negative — see memory `jaros-code-retrieval-fewshot-negative`):** this is
PLAN + PROVENANCE recall, NOT behavior-keyed few-shot CODE examples — that mechanism measured NEGATIVE for
solving quality on the 2B (probed behavior-keyed RAG few-shot lowered the pass rate). Recall here informs
the PLAN's context (what was done before and why, so a repeat/similar request can be recognized and
reconciled) — it must NEVER paste stale code into a solving prompt as an example to imitate.

**v1 is DETERMINISTIC (no model call, no embeddings):** lexical/tag-based retrieval only. Embeddings-based
semantic recall is an explicit, separate, later follow-up — this requirement's job is the durable store +
a genuinely-ranked deterministic recall mechanism, proven offline.

#### Acceptance Criteria
- [x] A durable, append-only store of past actions: `record_action(action, rationale, *, tags=None,
  outcome=None, meta=None)` persists `{action, rationale, tags, outcome, meta, seq/ts}` to a JSONL store
  under the data dir; never raises on any input (garbage/None/non-string arguments degrade gracefully,
  never crash the caller) — **DONE 2026-07-04** (`harness/episodic_memory.py::record_action`, TASK-32)
- [x] Deterministic similarity recall: `recall_similar(query, *, k=5, tags=None)` returns up to `k` past
  actions ranked by DETERMINISTIC lexical/tag overlap (e.g. token-set Jaccard over action+rationale text,
  with a bonus for shared tags) — NOT a model call, NOT embeddings (that is an explicit later follow-up);
  ties broken stably (e.g. recency/insertion order) so results are reproducible; empty store / no match /
  bad input returns `[]`, never raises — **DONE 2026-07-04** (`harness/episodic_memory.py::recall_similar`,
  TASK-32: token-set Jaccard over `action + rationale` text plus a fixed per-shared-tag bonus, ties broken
  by descending `seq` i.e. most-recent-wins)
- [x] A scoped/reset store option so callers and tests can isolate state (no cross-test/cross-repo bleed) —
  DONE (`reset(store)` plus every function accepting a `store=` keyword defaulting to `DEFAULT_STORE`)
- [x] Read-back: `load_actions()` parses the JSONL, skipping malformed lines, never raising — DONE
- [x] Proven offline (deterministic unit tests): recall ranks a crafted set of distinct actions in the
  correct, exact order; a tag filter narrows results; `k` bounds the count; an empty store and a
  non-matching query both return `[]` without raising; a malformed JSONL line is skipped, not fatal —
  DONE (`tests/test_episodic_memory.py`, 10 tests, no model/network; full `tests/` suite stays green:
  1590 passed, 1 skipped, up from 1580/1)
- [ ] EXPLICIT FOLLOW-UP (not required by this requirement): wiring `record_action`/`recall_similar` into
  `build_system`/`build_system_governed`/the CLI orchestrator so every real build records its action+
  rationale and every new plan retrieves+reconciles against similar past work before planning — this
  requirement builds and proves the mechanism only; wiring is an open follow-up (out of TASK-32's scope)

### [REQ-25] Best-of-k build reliability — mask occasional total build failure  (PARTIAL — offline mechanism DONE, EXT-036 TASK-33, 2026-07-04)

**Owner directive (2026-07-04), MEASURED, verify-don't-assume:** a median-of-3 coherence measurement on
`HARD_SLICE` (the 11-req interdependent CLIs, REQ-23) found single-pass `build_system` scores median
coherence 1.0 when it succeeds — it NAILS all 11 requirements, ZERO dropped requirements — but suffers an
occasional TOTAL BUILD FAILURE (~17% measured: 1/6 builds produced nothing runnable, scoring 0). So the
failure mode this class of build actually has is BUILD RELIABILITY (occasional total failure), NOT dropped
requirements — the governed decompose→repair capstone (REQ-23) was the WRONG lever for THIS failure mode
(no requirements are being dropped to repair) and was correctly banked as net-negative for it. The RIGHT
lever for a total-failure-rate class is BEST-OF-K: build the same spec up to `k` times and keep the best
attempt by an INDEPENDENT acceptance measure — this masks the ~17% total-failure rate deterministically
(selection is test-gated/deterministic; only generation is model-driven), without any model-drift risk.

#### Acceptance Criteria
- [x] `build_system_best_of_k(spec, root, *, llm=None, k=3)` in `harness/system_builder.py` (NEW function;
  `build_system`'s own behavior/signature untouched) builds up to `k` attempts, each into its OWN fresh
  temp subdirectory so attempts never contaminate each other — **DONE 2026-07-04**
  (`harness/system_builder.py::build_system_best_of_k`, TASK-33)
- [x] Each attempt is scored by an INDEPENDENT acceptance measure (a freshly-derived acceptance checklist —
  `_derive_acceptance_checklist` — run for real via `_run_check` against that attempt's own assembled
  modules, never trusting the attempt's self-reported `done` alone) — count of actually-passing checks is
  the score — **DONE 2026-07-04**
- [x] SELECTS the best attempt (most passing acceptance checks; ties → the first/fastest evaluated).
  EARLY-EXIT: an attempt that passes ALL of its acceptance checks stops the loop immediately (doesn't waste
  the remaining `k`) — **DONE 2026-07-04**
- [x] ASSEMBLES the winning attempt's modules onto the caller's `root` (never the temp attempt dirs), and
  returns `{modules, shipped, done, attempts_run, best_score, note}` — `done` reflects the WINNER's real,
  independently-verified acceptance, never a fabricated pass. NEVER raises: a failing attempt scores 0 and
  is skipped over; if every attempt fails, the LEAST-BAD attempt is returned with `done=False` and an
  honest note (never a manufactured pass) — **DONE 2026-07-04**
- [x] Selection is fully DETERMINISTIC and test-gated (only generation is model-driven) — proven OFFLINE
  with a fake/canned llm (`tests/test_ext036_system_builder.py`): a case where attempt 1 is broken/empty (0
  checks pass) and attempt 2 is fully correct proves best-of-k MASKS the failure (returns the correct
  system); a first-attempt-passes-everything case proves the early-exit (`attempts_run == 1`); an
  all-attempts-fail case proves the honest least-bad return (`done=False`, no fabricated pass);
  `build_system` itself is confirmed byte-identical/unaffected — **DONE 2026-07-04**
- [ ] FOLLOW-UP (explicit, out of this task's scope): wiring `build_system_best_of_k` into the `/buildsystem`
  CLI command (today only reachable via direct harness import/tests) and a LIVE gemma re-measurement of the
  masked failure rate against `HARD_SLICE`/`coherence_suite.run_coherence_suite` — open

### [REQ-26] Acceptance-completeness / done-honesty — a deterministic minimum acceptance floor  (DONE — offline mechanism, EXT-036 TASK-37, 2026-07-05)

**MEASURED PROBLEM (2026-07-05), task #118:** `build_system`'s `_derive_acceptance_checklist(spec,
mods, llm)` (REQ-2) proposes acceptance checks via the MODEL, so the checklist VARIES in
completeness for the IDENTICAL sentence — a single datastore build derived 3 checks, another draw
of the SAME sentence derived only 1. `build_system_best_of_k` (REQ-25) then EARLY-EXITS on
whichever draw derived the fewest/easiest self-checks and reports `done=True` on a sparse 1-check
bar — not real correctness. The model was also independently found to systematically MISS a
'usage'/CLI-help check. So `done` was not comparable across builds/draws and could be hollow — a
Tenet-3 gap sitting directly beneath REQ-25's best-of-k selection mechanism.

**THE FIX — a DETERMINISTIC MINIMUM checklist the model can only ADD TO:** derived from the SPEC
sentence + the built module API alone (NO model call, so it is IDENTICAL for the same input every
time, closing the cross-draw inconsistency), composed via UNION with the model's own proposals so
the bar for a given sentence can never be SPARSER than the minimum.

#### Acceptance Criteria
- [x] `harness/system_builder.py::_minimum_acceptance(spec, mods, plan)` — a DETERMINISTIC
  minimum checklist: the existing `_smoke_checklist` (import + `hasattr`) as the floor, a
  USAGE/HELP check (running the entrypoint with no args AND with `--help`, asserting neither
  crashes with an unhandled Python exception — the systematically-MISSED check), and one
  subprocess check per conservatively-extracted command token the spec names
  (`_extract_command_tokens` — quoted tokens like `'add'`/`'list'` plus a small fixed allow-list
  of imperative verbs; under-extracts rather than hallucinates a command the sentence doesn't
  name). Entry filename resolved by `_minimum_entry_filename` (plan's declared `entrypoint`, else
  a module literally named `main.py`, else the last planned module — mirrors
  `harness.system_suite._resolve_entry`'s convention). — **DONE 2026-07-05**
- [x] NO ORACLE LEAK (Tenet 3): every minimum check asserts ONLY that the command doesn't
  genuinely crash (`'Traceback (most recent call last)' not in result.stderr`) — never a specific
  stdout VALUE, which would require knowing the answer up front. Empty stdin (`input=""`) is fed
  so a stdin-driven CLI (REQ-23's convention) sees an immediate EOF rather than hanging. — **DONE
  2026-07-05**
- [x] `harness/system_builder.py::_compose_acceptance_checklist(spec, mods, llm, plan)` — the
  FINAL checklist = the deterministic minimum UNIONED with `_derive_acceptance_checklist`'s own
  model-derived proposals (REQ-2 is untouched — still a pure model-tier derivation on its own);
  de-duplicated by `(name, code)` so an identical proposal is never double-counted. The model's
  checks AUGMENT, never REPLACE, the minimum. Guarded: a model/derive failure or exception still
  leaves the deterministic minimum in place. — **DONE 2026-07-05**
- [x] `build_system`'s own ACCEPTANCE step now calls `_compose_acceptance_checklist` (replacing
  the direct `_derive_acceptance_checklist` call) — `done=True` iff EVERY check in the composed,
  minimum-inclusive checklist passes from a CLEAN state (the pre-existing from-clean-state /
  REQ-5 repair-loop honesty rules are untouched); an empty checklist still never counts as done
  (existing rule, now only reachable in the degenerate case where the minimum itself yields
  nothing, e.g. no modules at all). — **DONE 2026-07-05**
- [x] `build_system_best_of_k`'s `_score_build_attempt` (REQ-25) now scores every attempt against
  the SAME composed, minimum-inclusive checklist instead of a purely model-derived one — a draw
  that self-derives fewer model checks is still measured against the full deterministic floor, so
  best-of-k selects/early-exits only when a draw genuinely passes the FULL bar, never a sparse
  self-accepted one. `build_system`'s and `build_system_best_of_k`'s own signatures/other
  behavior are otherwise byte-identical. — **DONE 2026-07-05**
- [x] HONEST regression proven, not hidden: a fixture with a single trivial self-derived model
  check (an `import` that never exercises the broken command) that previously would have looked
  like a pass now correctly fails via the deterministic minimum's own command check — `done`
  flips to the HONEST `False`. A matching control proves no NEW false negative (the same composed
  bar reports `done=True` once the CLI is genuinely fixed). This is the intended, HONEST outcome
  (a stricter, trustworthy bar can only lower a hollow accept-rate, never raise a real one) — not
  a regression. — **DONE 2026-07-05**
- [x] Proven OFFLINE (`tests/test_ext036_acceptance_completeness.py`, 16 tests, canned/fake `llm`,
  no live model): `_extract_command_tokens`/`_minimum_entry_filename`/`_minimum_acceptance` unit
  behavior (including never-raises on bad input); the minimum is deterministic/stable across
  repeated calls on the same sentence; the composed checklist is never sparser than the minimum
  and the model's proposals genuinely augment it; an identical model proposal dedupes against a
  minimum check; the composed checklist survives a raising `llm`; an end-to-end build whose model
  self-derives only ONE trivial (always-passing) check still gets `done=False` on a genuinely
  broken CLI (caught by the minimum's own command check) and `done=True` once fixed (no new false
  negative); `build_system_best_of_k` no longer early-exits on a sparse first-attempt pass and
  lands the genuinely-fixed second attempt. `tests/test_ext036_acceptance.py` extended (1 updated
  + 1 new test for the empty-checklist invariant under the new composition — an empty checklist
  is now only reachable by monkeypatching BOTH the minimum and the model-derivation to `[]`, since
  a real (non-monkeypatched) minimum is never empty for a non-empty module set). One pre-existing
  REQ-23 governed-build fixture (`MAIN_MISSING_MUL` in `tests/test_ext036_system_builder.py`) was
  updated to still DEFINE the `mul` function (satisfying the new stricter existence-based smoke
  floor) while leaving it unwired from the CLI dispatch — preserving that file's "build_system's
  own checklist is fooled by a dropped BEHAVIOR, not a dropped SYMBOL" premise under the new
  deterministic floor, HONESTLY updated per the stricter (correct) bar rather than weakened. Full
  `tests/` suite stays green: 2275 passed, 2 skipped (up from 2258/2). — **DONE 2026-07-05**
- [ ] FOLLOW-UP (explicit, out of this task's scope, pre-existing per REQ-25): a LIVE gemma
  re-measurement of accept-rates before/after this fix (the honest expectation is a LOWER
  measured accept-rate, not a regression), and wiring `build_system_best_of_k` into the
  `/buildsystem` CLI command — open
