---
id: EXT-036
title: Sentence-to-System — build a complex Python system from a one-sentence spec (Claude-Code-parity)
status: partial
priority: high
implementation: ["harness/session.py", "harness/cli.py", "harness/project_md.py", "harness/repo_memory.py", "harness/system_builder.py", "harness/task_store.py", "harness/experiment_store.py", "harness/multi_tests.py", "harness/ask_user.py", "harness/system_suite.py", "harness/modification_suite.py", "harness/server_oracle.py", "harness/coherence_suite.py", "harness/episodic_memory.py", "harness/acceptance_review.py", "harness/filename_contract.py", "harness/http_service_scaffold.py", "harness/agent_scaffold.py", "harness/port_coercion.py", "harness/endpoint_shape.py"]
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

### [REQ-20] Parity instrument: a broad, DIVERSE, held-out suite of sentence→system CREATION classes  (PARTIAL — framework + first slice, EXT-036 TASK-14; sentences made contract-precise, TASK-15; grown to 12 tasks/classes, TASK-17; grown to 20 tasks / 17 classes incl. a highly-complex tier via `HARDER_SLICE` + `ALL_CREATION_TASKS`, TASK-24, 2026-07-04; grown to 24 tasks / 21 classes with 4 more real-system highly-complex classes, TASK-50, 2026-07-08)

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
  0/8, so no contract is trivially satisfiable, Tenet 3). **TASK-50 (2026-07-08, MEASURED: the toy-CLI tier is
  ~92% mastered — no longer discriminates) adds 4 MORE `HARDER_SLICE` classes, all `"highly-complex"`, drawn from
  the real-systems frontier (real persistence/parsing/state, not just harder toy logic): `sqlite-persistent-kv-cli`
  (genuine cross-process SQLite persistence — a `set` in one process must be `get`-able in a completely separate
  later process), `sql-mini-query-cli` (an in-memory `CREATE TABLE`/`INSERT INTO`/`SELECT ... WHERE` engine),
  `infix-expr-eval-cli` (an INFIX expression evaluator with real operator precedence + parentheses, harder than
  the suite's existing RPN calculator), and `json-path-query-cli` (a dotted/indexed JSON-path resolver) — growing
  coverage to 24 tasks / 21 classes; each self-verified via its own reference impl through the independent oracle
  (a no-op scores 0 on all four, Tenet 3, `tests/test_ext036_harder_creation_classes.py`)**; the remaining broader
  classes (REST/HTTP service, plugin system, auth/permission, workflow engine, simulation/game-loop, and the
  many-module highly-complex tier) remain open growth.
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

### [REQ-21] Parity instrument: matching sentence→system MODIFICATION classes (edit an existing complex system)  (PARTIAL — framework + first slice, EXT-036 TASK-16; grown to 10 tasks/harder change classes, TASK-20, 2026-07-03; multi-file tier added, TASK-22, 2026-07-03; ratcheted with a genuinely-hard `HARDER_SLICE`, TASK-51, 2026-07-08)

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
- [x] The difficulty frontier must be RATCHETED once the existing tiers saturate, not left to go stale (PRIME-001's
  difficulty ratchet, mirroring REQ-20's TASK-24/TASK-50 growth) — **DONE 2026-07-08** (`harness/modification_suite.py`
  `HARDER_SLICE`, TASK-51): MEASURED (docs/GAP-MAP.md) that `FIRST_SLICE` + `MULTIFILE_SLICE` together are ~35/36
  SATURATED — gemma aces nearly every task including the multi-file tier, so the suite no longer discriminates.
  `HARDER_SLICE` adds 4 genuinely-hard, all-`"highly-complex"`-tier tasks, each starting from a COMPLEX,
  already-non-trivial `start_system` (not a toy CLI) that the model must comprehend and precisely EXTEND: an infix
  arithmetic expression evaluator (real operator precedence + parentheses) gains a modulo operator at the same
  precedence as `*`/`/`; an in-memory SQL-like engine (`CREATE TABLE`/`INSERT INTO`/`SELECT * FROM ... WHERE`) gains
  single-column projection (`SELECT <col> FROM ... WHERE`); a dotted-path JSON resolver gains Python-style negative
  array indices; a two-file stats CLI (`statlib.py` mean/median + `main.py` dispatch) gains a `mode` subcommand
  (smallest value wins ties) requiring a coordinated edit across both files. `HARDER_SLICE` is exposed standalone
  (NOT folded into `ALL_TASKS`, which stays byte-identical to `FIRST_SLICE + MULTIFILE_SLICE` for backward
  compatibility with existing callers/tests — callers that want the hardest tier pass `tasks=HARDER_SLICE`
  explicitly); `run_modification_suite`'s default `tasks=FIRST_SLICE` is unchanged. HONEST (Tenet 3, no leak): each
  `start_system` is proven to already pass its own `regression_checks` UNMODIFIED (known-good precondition); a
  hand-written, genuinely-correct REFERENCE MODIFICATION for every task is driven through the REAL
  `run_modification_suite` oracle and satisfies BOTH `new_checks` AND `regression_checks` (`accepted=True`); and a
  NO-OP `modify_fn` (start_system left completely unchanged) FAILS every task's `new_checks` — proving the checks
  genuinely test the requested change and are not trivially/accidentally satisfiable by the pre-modification system.
  Proven OFFLINE (`tests/test_ext036_harder_modification_classes.py`, no live model, no network): all four
  properties above, plus the registry's structural shape. CAVEAT (honest scope): a live gemma-vs-escalating
  measurement against `HARDER_SLICE` has not been run here — that remains an explicit follow-up, mirroring REQ-20's
  same open caveat for its own `HARDER_SLICE`.

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

### [REQ-27] Behavioral acceptance honesty — error-in-output detection + add/list round-trip  (DONE — EXT-036 TASK-38, 2026-07-05)

**MEASURED PROBLEM (2026-07-05), behavioral verification of a `done=True` build:** REQ-26's
deterministic minimum per-command checks (`_no_crash_subprocess_check`) assert ONLY
`'Traceback (most recent call last)' not in result.stderr` — a NO-CRASH bar, not a
BEHAVIORAL one. A built datastore CLI that gracefully CATCHES its own exception and PRINTS
it (e.g. `"An error occurred while listing notes: DatabaseManager.__init__() missing 1
required positional argument: 'db_path'"`) at exit-code 0 PASSES the no-crash check while
being genuinely broken — LIVE-measured: `done=True` was reported, yet running the built CLI
by hand, `list` printed that error and `add` never actually persisted (a note added then
listed did NOT appear). `done=True` was HOLLOW — a NEW false-done class sitting directly
beneath REQ-26's own floor: "runs without crashing" is not the same claim as "works".

#### Acceptance Criteria
- [x] `harness/system_builder.py::_has_error_marker(text)` (+ its generated-code mirror
  `_ERROR_MARKER_HELPER_SRC`, single source of truth via the same compiled regex pattern
  strings) — a check now FAILS if a command's combined stdout+stderr contains a standalone
  error marker EVEN AT `rc=0`: a line starting with `Traceback`/`Exception`/`Error`, or a
  substring match for `an error occurred` / `missing ... required ... argument` / `not
  found` (case-insensitive). Conservatively ANCHORED (line-start for the class-name forms,
  specific fixed phrases for the substring forms) so a legitimate usage/help message (e.g.
  argparse's own `"prog: error: the following arguments are required: ..."`, which is
  prefixed by the program name, never bare at line-start) and normal output that merely
  contains the word "error" as DATA (e.g. `"Server error rate: 0.02"`) are never
  false-flagged. `_no_crash_subprocess_check` (REQ-26) now asserts BOTH the pre-existing
  no-traceback rule AND this marker check for every minimum invocation, including the
  usage/--help check (which is unaffected in practice by the anchoring above). — **DONE
  2026-07-05**
- [x] `harness/system_builder.py::_derive_roundtrip_pair(spec)` + `_roundtrip_acceptance_check(entry,
  add_cmd, list_cmd)`, composed into `_minimum_acceptance`: when the SPEC sentence clearly
  names (as a whole word, quoted or bare) BOTH an ADD-like command (`add`/`create`/`save`/
  `insert`/`new`) AND a LIST-like command (`list`/`show`/`print`/`get`/`all`), a
  DETERMINISTIC behavioral round-trip check is added — from a clean invocation, run
  `<entry> <add-cmd> <sentinel...>` then `<entry> <list-cmd>`, and assert a fixed literal
  sentinel token APPEARS in the list output (real persistence, not just no-crash). Tries the
  add command with 1 then 2 positional sentinel args (covers both `add <text>` and `add
  <title> <content>` conventions) — the round-trip PASSES if ANY arg-count both adds without
  an error marker AND the sentinel shows up in the subsequent list output. Conservative:
  emitted ONLY when the sentence names a clear add+list pair (skipped otherwise, e.g. a
  plain "add(a, b)" calculator sentence with no list-like word derives nothing new). — **DONE
  2026-07-05**
- [x] NO ORACLE LEAK (Tenet 3): the round-trip asserts only that a user-supplied SENTINEL
  literal (never derived from or leaked into the solving prompt) added via the system's own
  ADD command appears via its own LIST command — the system's own stated contract, never a
  hidden expected value. — **DONE 2026-07-05**
- [x] Composed into `_minimum_acceptance`/`_compose_acceptance_checklist` (REQ-26) exactly
  like every other minimum check — UNIONED with the model's own proposals, never
  replacing them; `done=True` iff every composed check (now including the strengthened
  error-marker + round-trip checks) passes from a clean state. Honest Tenet-3 consequence:
  MORE builds correctly become `done=False` under this stricter floor — a trustworthy
  `done` on fewer builds is the intended outcome, not a regression. A REAL working
  add+list system still gets `done=True` (no new false negative). — **DONE 2026-07-05**
- [x] Proven OFFLINE (`tests/test_ext036_acceptance_completeness.py`, extended, no live
  model): `_has_error_marker` unit behavior (catches the measured graceful-error phrasing
  and a bare `Error:`-prefixed line; does NOT flag an argparse-style `"prog: error: ..."`
  usage line or a legitimate `"...error rate..."` data line); `_derive_roundtrip_pair` unit
  behavior (finds an add+list pair, is conservative/returns `None` on a sentence naming
  only one side or neither, never raises on bad input); an end-to-end `build_system` run
  against a fake CLI that gracefully prints `"Error: ..."` at `rc=0` on its primary command
  now reports `done=False` (caught by the strengthened minimum, not just a trivial
  self-derived check); an end-to-end run against a fake CLI whose add+list genuinely
  round-trips (writes then reads back a real file/store) reports `done=True`; full
  `tests/` suite stays green. — **DONE 2026-07-05**

### [REQ-28] Per-command minimum-acceptance probes must not mis-grade usage/argument-validation as a runtime defect  (DONE — EXT-036 TASK-39, 2026-07-05)

**MEASURED FALSE-NEGATIVE (2026-07-05), physical verification of a genuinely-working best-of-k
build:** REQ-26's per-command minimum check (`_minimum_acceptance`'s loop over
`_extract_command_tokens(spec)`, each probed via `_no_crash_subprocess_check(..., [[cmd,
"x"]])`) feeds exactly ONE guessed positional arg per command — it has no way to know a
command's real arity. A best-of-k (k=5) attempt built a GENUINELY WORKING SQLite notes CLI
(physically verified: `add "T" "BODY"` persists, `list` shows it, all requirements met,
`n_unmet=0`), but its `add` command takes TWO positional args (title + content); probed with
only one (`add x`), it correctly prints its OWN usage/argument-validation message (e.g.
`"Error: 'add' command requires a title and content."`) at `rc=0` — the CORRECT behavior for
a mis-arity call. REQ-27's `_has_error_marker` correctly flags the bare `Error:`-prefixed line
as an error marker (that check's own job, and it must keep doing so for a GENUINE runtime
error), so the per-command `add` check FAILS, and `build_system`'s overall acceptance reports
`done=false` ("best attempt passes 4/5 acceptance checks") even though the app is genuinely
working. This is a FALSE-NEGATIVE — the bar under-claims a working app — which is exactly as
dishonest a Tenet-3 defect as a false-done: `_minimum_acceptance`'s own GUESSED-ARITY probing
strategy, not the built app, is the source of the mis-grade.

#### Acceptance Criteria
- [x] `harness/system_builder.py::_is_usage_validation_message(text)` (+ a generated-code
  mirror, `_USAGE_VALIDATION_HELPER_SRC`, built from the SAME pattern strings — single
  source of truth, no drift) — a conservative, DETERMINISTIC classifier for output that is
  clearly a USAGE/ARGUMENT-VALIDATION message rather than a genuine runtime defect: an
  argparse-style `usage:` line, `"the following arguments are required"`, `"too few/many
  arguments"`, `"expected ... argument(s)"`, a `"requires a/an/<N>"` phrasing (the measured
  `"'add' command requires a title and content"` shape), `"provide a/an/the"`, a
  `"required argument"` phrase (NOT the Python-runtime `"required positional argument"`
  shape — deliberately NOT matched, see the negative test below), and `"missing
  argument/option/parameter"` immediately adjacent (NOT the Python-runtime `"missing N
  required positional argument"` TypeError shape, which has `"N required positional"`
  between the two words and so does not match). Conservative by construction: every pattern
  is chosen so it matches the vocabulary of a program's OWN CLI-arity-validation message
  while provably NOT matching REQ-27's motivating genuine-defect text (the graceful
  `"An error occurred while listing notes: ... missing 1 required positional argument:
  'db_path'"` TypeError string) or any other REQ-27 true-positive fixture. — **DONE
  2026-07-05**
- [x] `_no_crash_subprocess_check(name, entry, invocations, *, allow_usage_validation=False)`
  gains the new keyword-only parameter (default `False`, so every EXISTING call site — the
  usage/`--help` check, the smoke floor — is byte-identical in behavior). When
  `allow_usage_validation=True`, the generated check's error-marker assertion becomes: fail
  only if `_has_error_marker(combined)` is True AND `_is_usage_validation_message(combined)`
  is False — i.e. a genuine error marker is excused ONLY when it is ALSO classified as a
  usage/argument-validation message; a genuine runtime error (no usage vocabulary present)
  still fails exactly as before. The PRE-EXISTING no-traceback assertion (`'Traceback (most
  recent call last)' not in result.stderr`) is COMPLETELY UNCHANGED and unconditional — an
  actual unhandled crash always still fails regardless of this parameter. — **DONE
  2026-07-05**
- [x] `_minimum_acceptance`'s per-command loop (the `[[cmd, "x"]]` GUESSED-ARITY probes)
  now passes `allow_usage_validation=True` — this is the ONLY call site changed. The
  usage/`--help` check (`[[], ["--help"]]`) and `_roundtrip_acceptance_check` (REQ-27's
  arity-AWARE round-trip, which already tries both 1 and 2 positional args and so never
  needs to excuse a usage-validation message) are explicitly left STRICT/unchanged, per
  scope. — **DONE 2026-07-05**
- [x] NO ORACLE LEAK (Tenet 3): the classifier is a closed-form deterministic vocabulary
  match derived from the interface/spec-level convention of CLI usage messages in general —
  never derived from or tuned to any specific built app's hidden expected output. — **DONE
  2026-07-05**
- [x] HARD DUAL TEST proving BOTH directions at once, run through the ACTUAL
  `_minimum_acceptance` + `_run_check`/`_run_check_verbose` machinery against two synthetic
  on-disk CLIs (`tests/test_ext036_usage_validation_floor.py`):
  1. TRUE-POSITIVE PRESERVED — a CLI whose `list` command (invoked correctly) prints
     `"Error: no such table: notes"` at `rc=0` still FAILS its per-command check (and the
     full minimum-acceptance checklist is NOT all-pass) — REQ-27's genuine-defect catch is
     untouched by this relaxation.
  2. FALSE-NEGATIVE FIXED — a CLI whose `add` command, when probed with only one guessed
     arg, prints its own `"... requires a title and content."` usage message at `rc=0`, but
     whose real two-arg `add <title> <content>` genuinely persists to disk and is visible
     via `list` — the per-command `add` check now PASSES, and (composed with a genuinely
     passing round-trip check) the full minimum-acceptance checklist is all-pass.
  Full `tests/` suite re-run via `python -m harness.run_with_heartbeat -- python -m pytest
  tests/ -q`, confirmed green with no regression. — **DONE 2026-07-05**

### [REQ-30] Optional 7B-review of model-proposed acceptance checks (DONE — offline mechanism, EXT-036 TASK-40, 2026-07-05)

**MEASURED PROBLEM (2026-07-05), memory [[jaros-code-build-acceptance-honesty]]:**
REQ-26's composed acceptance checklist (deterministic minimum UNION model-proposed
checks) is honest about the FLOOR, but the model-PROPOSED portion (the SAME small
model that built the system also writes checks for its own build) is a MIXED bag:
some HALLUCINATE (an invented API `from main import encode`, an invented value
`assert convert(300,'K','C')==27.78` when 300K=26.85), FALSE-NEGATIVING 8/20
genuinely-correct systems on the 20-task suite; others correctly CATCH real
breakage (rpn-calc, kv-store-ttl). Blanket-TRUSTING the model-proposed checks
false-negatives correct builds; blanket-DEMOTING them (a reverted attempt, parked
in `git stash@{0}`) introduced 2 FALSE-DONES.

**VALIDATED FIX (owner's idea, PRE-REGISTERED KILL CRITERION probed 2026-07-05,
`.jaros-data/sevenb_review_probe.py`, task #122):** a STRONGER model
(qwen2.5-coder-7b) REVIEWS+CORRECTS each model-proposed check from the VISIBLE
SPEC + CODE ONLY — never any hidden/expected output (NO ORACLE LEAK). Probe
result: the 7B fixed 3/4 hallucinated checks (turned a currently-failing bogus
check into a passing-or-dropped one) AND preserved 1/1 real-bug check (left it
genuinely failing) — passing the pre-registered bar. This requirement builds the
production-grade, injectable mechanism the probe validated; the live gemma<->7B
Jetson swap orchestration + the 20-task false-done gate that flips this on by
default are explicit follow-ups, out of scope here.

#### Acceptance Criteria
- [x] `harness/acceptance_review.py::review_checks(spec, modules, proposed_checks,
  reviewer_llm) -> list[dict]` — a pure, injectable function reusing the EXACT
  `REVIEW_PROMPT` wording and fence-stripping/DROP-parse logic validated by the probe.
  For each proposed check, calls `reviewer_llm.complete(LlmRequest(prompt=...,
  params={"temperature": 0.0, "max_tokens": 1024})).text`; corrects a hallucinated
  API/import to the real one, recomputes an asserted VALUE from the spec's stated
  rules (or drops the assertion if the spec doesn't determine it), or DROPS the
  whole check (omitted from the returned list) when it can't be verified from
  spec+code alone. — **DONE 2026-07-05**
- [x] NO ORACLE LEAK (Tenet 3): the reviewer sees ONLY `spec` + the built `modules`
  source + the ONE proposed check — never any hidden/expected output. — **DONE
  2026-07-05**
- [x] NEVER raises: a `reviewer_llm.complete` exception (unreachable model,
  malformed response, anything) leaves that ONE check UNCHANGED (conservative —
  keep the model's original proposal rather than silently losing/mangling it),
  never crashes the caller and never treats a reviewer outage as a drop. — **DONE
  2026-07-05**
- [x] Wired into `harness/system_builder.py::build_system` (and
  `_score_build_attempt`/`build_system_best_of_k`, REQ-25) as an OPTIONAL
  keyword-only refinement `check_reviewer=None`. Default `None` leaves
  `build_system`'s behavior BYTE-IDENTICAL to before this task (proven by a
  dedicated regression test). When a `check_reviewer` IS supplied, ONLY the
  MODEL-PROPOSED portion of the composed checklist (REQ-26) — never the
  deterministic minimum, which always gates as-is and is never sent to the
  reviewer — is replaced by `review_checks`'s corrected/dropped output BEFORE the
  checklist gates `done`. `build_system` performs NO model-swap orchestration
  itself: `check_reviewer` is just an injected llm; which model actually serves
  as the reviewer (e.g. a live Jetson gemma<->7B swap) is a CALLER concern, kept
  out of scope so `build_system` stays fast, gemma-default, and offline-testable.
  — **DONE 2026-07-05**
- [x] Proven OFFLINE (`tests/test_ext036_acceptance_review.py`, fake/canned
  `llm`/`reviewer_llm` stubs, no live model, no network): `review_checks` unit
  behavior — corrects a hallucinated check to the real API, drops an
  unverifiable check, keeps a real-bug check UNCHANGED when the reviewer is
  "told to keep it" (proving review never launders a genuine defect-catch into a
  pass), keeps the original check unchanged when the reviewer raises, strips
  markdown fences the same way the validated probe does, never raises on
  empty/bad input, and the reviewer prompt carries only spec+code+the one check
  (no oracle leak). End-to-end: a hallucinated model-proposed check on a
  genuinely-working synthetic CLI flips `done` False->True once reviewed
  (dropped); a real-bug model-proposed check stays failing (`done=False`,
  0-false-done preserved) even when the reviewer is told to keep it; a
  fixed-build regression test proves `check_reviewer=None` (both the implicit
  default and an explicit `None`) is byte-identical on `shipped`/`done`/`unmet`/
  `note`/`modules`; a reviewer that raises on every call never crashes
  `build_system` (degrades to the unreviewed composed checklist). — **DONE
  2026-07-05**
- [ ] FOLLOW-UP (explicit, out of this task's scope): the live gemma<->7B
  Jetson-swap orchestration that actually serves `check_reviewer` with the
  stronger model in production, and a LIVE 20-task false-done-gate measurement
  before flipping `check_reviewer` on by default in `/buildsystem` — open

### [REQ-31] 7B-GENERATE acceptance checks — the stronger model writes checks from scratch, unshackled from Gemma's proposals (DONE — offline mechanism, EXT-036 TASK-41, 2026-07-06)

**Owner's extension of REQ-30 (task #122b, 2026-07-06):** REQ-30's `review_checks` is
BOUNDED by Gemma's own proposed checks — the 7B can only correct/patch what Gemma wrote,
never invent a better check Gemma never thought to propose. This requirement builds the
GENERATE variant: the stronger model writes acceptance checks FROM SCRATCH from ONLY the
visible spec + built module sources (NO ORACLE LEAK, same honesty framing as REQ-30's
`REVIEW_PROMPT`) — unshackled from Gemma's hallucinated proposals entirely. It is standalone
and injectable, for an A/B live-gate measurement against `review_checks` and the unassisted
baseline; it is NOT wired into `build_system` in this task (that wiring + the live measurement
are the caller's/parent's next step, mirroring how REQ-30's offline mechanism preceded its own
follow-up).

#### Acceptance Criteria
- [x] `harness/acceptance_review.py::generate_checks(spec, modules, generator_llm,
  max_checks=4) -> list[dict]` — a pure, injectable function that prompts `generator_llm`
  (a `.complete(LlmRequest(prompt=..., params={"temperature": 0.0, "max_tokens":
  1024})).text`-style object) to WRITE runnable acceptance checks proving the spec is
  satisfied, using ONLY `spec` + the built `modules` source. Returns a list of
  `{"name": str, "code": str}` dicts (the same shape `_compose_acceptance_checklist`
  entries / `_run_check_verbose` consume), bounded to `max_checks`. — **DONE 2026-07-06**
- [x] NO ORACLE LEAK (Tenet 3): the prompt sent to `generator_llm` contains ONLY `spec` +
  the built `modules` source — NEVER any hidden/expected output or oracle of any kind.
  — **DONE 2026-07-06**
- [x] Parses the generator's raw response conservatively: strips markdown fences (reusing
  `review_checks`'s `_clean_reviewed_code`), splits multiple fenced Python blocks into
  separate checks, honors a whole-response `DROP`, and OMITS any block that doesn't parse
  as valid Python with a real `assert` (a check the model can't write is dropped, never
  fabricated). — **DONE 2026-07-06**
- [x] NEVER raises: a `generator_llm.complete` exception, or any unparseable/garbage
  response, returns `[]` (conservative — no generated checks rather than a crash or a
  fabricated one). — **DONE 2026-07-06**
- [x] `review_checks` (REQ-30) is UNCHANGED by this task — `generate_checks` is new,
  additive code alongside it. — **DONE 2026-07-06**
- [x] Proven OFFLINE (`tests/test_ext036_generate_checks.py`, fake `generator_llm` stubs, no
  live model, no network): a well-formed multi-check response parses into the right number
  of runnable checks; the no-oracle-leak prompt shape; fenced-code stripping and
  multi-block splitting; a raising/garbage/DROP generator each yields `[]` without
  crashing. Full `tests/` suite re-run via `python -m harness.run_with_heartbeat --
  python -m pytest tests/ -q`, confirmed green with no regression. — **DONE 2026-07-06**
- [ ] FOLLOW-UP (explicit, out of this task's scope): wiring `generate_checks` into
  `build_system`/`build_system_best_of_k` (mirroring REQ-30's `check_reviewer` kwarg
  pattern), and a LIVE A/B gate measurement (7B-generate vs 7B-review vs baseline) on the
  20-task false-done suite before either mechanism is flipped on by default — open

### [REQ-32] Deterministic plan-repair for MULTI-module "entrypoint not a listed module" (DONE — EXT-036 TASK-42, 2026-07-06)

**MEASURED (hard-tier capability diagnostic, `.jaros-data/hardtier_failure_diag.json`,
2026-07-06):** the `graph-bfs-shortest-path-cli` CREATION task fails at the PLAN stage —
`build_system`'s `note` = `"plan failed coherence validation: entrypoint not a listed
module"` — a pure deterministic plan-coherence rejection, never reaching the reasoning
stage. LIVE-CONFIRMED (3/3 identical draws against the served gemma-4-e2b): the model
plans exactly 2 logic modules (`graph_builder.py`, `bfs_solver.py`), BOTH with `imports:
[]` (no module imports any sibling — a fully disconnected pair), and sets `entrypoint:
"main.py"`, a filename it never adds as a module — `validate_plan` correctly rejects
the whole plan and 0 modules build. `_repair_plan_entrypoint` (TASK-19, REQ-1) already
fixes the analogous SINGLE-module case (rename) but deliberately leaves EVERY
multi-module case untouched ("ambiguous which module should host the entrypoint") — this
requirement fills that gap for the one unambiguous multi-module shape.

#### Acceptance Criteria
- [x] `harness/system_builder.py::_repair_plan_entrypoint_multi(plan) -> (plan, note)` —
  when the plan lists 2+ modules, `entrypoint` is a well-formed `<identifier>.py`
  filename not among the listed module names, and NO listed module imports another
  listed module (a fully disconnected set — no existing candidate to guess between),
  ADD a new module named `entrypoint` whose `imports` list every currently-listed
  module (mirrors `_repair_plan_dangling_imports`'s additive-only convention — never
  renames or removes anything the model planned). — **DONE 2026-07-06**
- [x] SAFE / conservative: when ANY listed module already imports another (an existing
  wiring relationship exists, so it is genuinely ambiguous which module — if any —
  should host the entrypoint), or the entrypoint name/module shapes are malformed, the
  function makes NO repair and the plan is left to fail `validate_plan` exactly as
  before (no wrong guess). — **DONE 2026-07-06**
- [x] Wired into `build_system`'s plan-repair sequence, running after
  `_repair_plan_entrypoint` (TASK-19) and before `_repair_plan_dangling_imports`
  (TASK-36), so a plan tripping multiple defects gets all of them repaired in one pass;
  its note is folded into the existing `plan_repair` field. — **DONE 2026-07-06**
- [x] No regression to the pre-existing conservatism: the ALREADY-PINNED
  `test_ext036_planrepair.py` multi-module case (`cli.py` importing `calculator.py`,
  a genuine existing-wiring shape) still fails coherence validation exactly as before
  this task (that plan has an inter-module import, so this new function correctly
  declines to touch it). The existing single-module repair (TASK-19) is unchanged. —
  **DONE 2026-07-06**
- [x] `graph-bfs-shortest-path-cli` now PASSES plan validation after the repair (the
  deterministic rejection is unblocked; the build proceeds past the plan stage) —
  CONFIRMED LIVE against the served gemma-4-e2b. — **DONE 2026-07-06**
- [x] Proven OFFLINE (`tests/test_ext036_planrepair_multi.py`, no live model): the
  measured graph-bfs shape (fully disconnected 2-module plan) is repaired and becomes
  coherent; the pre-existing single-module repair test stays green; a genuinely
  ambiguous multi-module plan (an inter-module import already exists) is left rejected;
  a malformed-entrypoint variant is left rejected; the function never raises on
  malformed/edge-case plan input. Full `tests/` suite re-run via
  `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirmed green
  with no regression. — **DONE 2026-07-06**

**GENERALIZATION (EXT-036 TASK-47, MEASURED 2026-07-07 on `todo-list-cli`):** the TASK-42
repair only fired for a FULLY DISCONNECTED module set, so it left the common WIRED-DAG shape
rejected. Per-class creation-scoreboard run (2026-07-07) measured `todo-list-cli` failing
with 0 files: gemma plans `data_manager.py` + `cli_handler.py` (where `cli_handler` imports
`data_manager`) and sets `entrypoint: "main.py"` — a perfectly coherent dependency DAG with
a pinned entrypoint it never listed. The old "any sibling import → decline" guard tripped and
the whole plan was rejected. Because the repair ADDS a brand-new entrypoint module (it never
renames/chooses an existing one), the "which module hosts the entrypoint" ambiguity never
applies; the only open question is what the new entrypoint imports, and the DAG-correct
answer is the ROOT modules (in-degree 0 within the listed set — the top of the graph, from
which every module is transitively reachable). This SUPERSEDES the earlier "wired ⇒ decline"
conservatism (2nd and 4th criteria above) for any ACYCLIC plan.

#### Acceptance Criteria
- [x] `_repair_plan_entrypoint_multi` fires for ANY acyclic 2+-module plan with a well-formed
  unlisted `<identifier>.py` entrypoint: it computes the ROOT modules (those no listed module
  imports) and adds the entrypoint module importing exactly those roots. A fully disconnected
  set has every module as a root, so `roots == names` and this reduces EXACTLY to the TASK-42
  behavior (strict superset — no regression). — **DONE 2026-07-07**
- [x] A genuinely CYCLIC plan (no in-degree-0 module → empty roots) is still declined and
  left to `validate_plan`'s cycle check; malformed/edge-case shapes still decline as before. — **DONE 2026-07-07**
- [x] Proven OFFLINE (`tests/test_ext036_planrepair_multi.py` + `tests/test_ext036_planrepair.py`):
  the wired `cli.py`→`calculator.py`+`main.py` shape and a 3-module chain are now repaired
  (main.py imports the single root) and become coherent; the disconnected graph-bfs shape
  still repairs (note now reads "importing roots [...]"); the build ships end-to-end. — **DONE 2026-07-07**
- [x] Re-measured on the live Jetson: `todo-list-cli` builds a `main.py` and passes its
  independent oracle checks (creation scoreboard: todo-list 0%→pass). — **PENDING live re-measure this session**

### [REQ-33] Robust `_extract_json`: balanced-bracket extraction + bounded repair for malformed model JSON (DONE — EXT-036 TASK-43, 2026-07-06)

**MEASURED (plan-coherence gap-hunt, 2026-07-06):** across 40 CREATION-suite builds
(20 tasks x2 draws) the ONLY not-shipped failures were `todo-list-cli` on BOTH draws,
note = "planner produced no parseable JSON plan". Repro: `todo-list-cli`'s plan is a
large JSON object whose `"acceptance"` field is a long prose string that, on some gemma
draws, carries an UNESCAPED literal control character (a raw newline) inside the JSON
string value — `json.loads` raises and `harness/system_builder.py::_extract_json`
(lines 290-300) returns `None` with no repair attempt, so no plan is produced and the
build never ships. `_extract_json` is shared by the PLAN step AND every
acceptance-checks/fix-extraction call site (`~735/800/1269/1393/1862`), so a fix here
is a generic robustness lift, not a plan-only patch. Root cause: `_extract_json` does one
greedy `opener.*closer` regex (spanning to the LAST closer, which can over-span into
trailing prose) then a single `json.loads`, with zero repair on failure.

#### Acceptance Criteria
- [x] `_extract_json` gains a bounded REPAIR fallback used ONLY when its ORIGINAL
  greedy-match-then-`json.loads` fails (missing match, or `json.loads` raises) — the
  original code path is preserved UNCHANGED and tried FIRST, so any input the OLD
  code already parsed returns the IDENTICAL parsed object, byte-for-byte
  (★ non-negotiable — proven by regression test, not just asserted). — **DONE
  2026-07-06**
- [x] On failure, a BALANCED-bracket/brace extraction (depth-counted, string-literal
  aware so quote/escape state — including a malformed literal control char inside a
  string — never perturbs the depth count) is tried, preferred over a second blind
  greedy-to-last-closer attempt, because it does not over-span into trailing prose
  containing a stray closer. — **DONE 2026-07-06**
- [x] If still unparseable, a MINIMAL, string-aware repair is applied to each
  candidate span: literal control characters (`\n`/`\r`/`\t`/other bytes < 0x20)
  found INSIDE a JSON string literal are escaped to their proper JSON form, and a
  trailing comma immediately before a closing `}`/`]` (outside any string) is
  dropped; the repaired text is retried through `json.loads`. — **DONE 2026-07-06**
- [x] Markdown code-fence lines (```` ``` ````/```` ```json ````) are stripped before
  the balanced/repair attempts (normalization only; the preserved original-path
  regex already tolerated fences and is untouched). — **DONE 2026-07-06**
- [x] NEVER raises: an unparseable/garbage input still returns `None` after every
  extraction/repair attempt is exhausted. — **DONE 2026-07-06**
- [x] Drop-in replacement: identical signature (`_extract_json(raw, opener, closer)`),
  no caller changes required; both `("{","}")` (plan/fix objects) and `("[","]")`
  (acceptance-checks arrays) modes are exercised. — **DONE 2026-07-06**
- [x] Proven OFFLINE (`tests/test_ext036_extract_json_repair.py`, no live model): (a)
  the MEASURED todo-list shape (a plan-shaped JSON object with an unescaped literal
  newline inside the `acceptance` string) now returns the correct dict, was `None`
  before; (b) a valid JSON object followed by trailing prose containing a stray `}`
  returns the correct object (greedy-to-last-closer would have over-spanned or failed
  to parse); (c) several ALREADY-VALID JSON payloads (escaped `\n`, nested objects,
  arrays, the `[`,`]` acceptance-checks array mode) parse to the IDENTICAL object as
  the pre-change code — an explicit regression guard; (d) genuinely non-JSON garbage
  input still returns `None`, never raises; (e) a trailing-comma-only defect is
  repaired. Full `tests/` suite re-run via `python -m harness.run_with_heartbeat --
  python -m pytest tests/ -q`, confirmed green with no regression. — **DONE
  2026-07-06**
- [x] A FINAL, string-literal-aware STRUCTURAL-BRACKET recovery stage handles a defect
  class TASK-43's control-char/trailing-comma repair cannot: a DROPPED structural
  closer (`}`/`]`) inside a nested container — **DONE 2026-07-08** (`harness/system_builder.py`
  `_recover_missing_braces`, TASK-48). MEASURED (`.jaros-data/artifacts/todo_rawplan.log`):
  gemma's `todo-list-cli` plan embeds a multi-line Python class body as an export
  "signature" string and drops the `}` closing the export object before the `]` ending
  `exports`; `json.loads` fails ("Expecting ',' delimiter") and 0 modules build (class
  scores 0/3). `_recover_missing_braces` walks the text keeping a joint `{`/`[` stack
  (string-literal + backslash-escape aware, so brackets embedded in a string value never
  perturb depth); when a closer's matching opener is deeper in the stack than the
  innermost entry, it inserts the missing closers for the unclosed inner containers before
  emitting the real closer — inserting ONLY structural closers, never fabricating
  keys/values/commas. Wired into `_extract_json` as the LAST resort, tried only after the
  existing greedy/`_balanced_span`/`_repair_json_candidate` paths have all failed, so every
  previously-parseable plan is byte-identical (unaffected). Whatever it recovers still
  flows through the unchanged `validate_plan` gate — a bad recovery becomes a rejected
  plan, never a silent false build. Does NOT recover end-of-input truncation (a stack
  still open at end-of-string is left unchanged, a different defect class). Proven
  OFFLINE (`tests/test_ext036_plan_brace_recovery.py`): the exact captured `todo_rawplan.log`
  bytes now parse into a plan dict with the signature string intact (was `None` under the
  pre-recovery logic); 6 already-valid samples (incl. nested arrays-of-objects and strings
  literally containing `{ } [ ] ,`) pass through byte-identical and `_extract_json` returns
  the same result as before; an end-of-input-truncated payload is left unchanged, not
  fabricated.

### [REQ-34] Iterative REPLAN-AS-MODIFICATION build recovery (DONE — offline mechanism, EXT-036 TASK-44, 2026-07-06)

**Owner idea (roadmap 57e8341):** today's `_repair_system` (REQ-5) only ever attempts a
per-module, per-check PATCH when a build fails acceptance — feed the failing check's
error + the current module sources back to the model for a targeted corrected module.
The owner's richer idea: when that still isn't enough, step BACK and REPLAN — assess
where the project actually landed vs the spec's target, produce a MODIFICATION plan to
bridge the gap, apply it via the existing MODIFICATION plane (`modify_system`, REQ-14),
re-check, and ITERATE (2nd/3rd/4th round). This can fix things a local per-check patch
cannot (add a missing module, restructure), and reuses proven machinery rather than
inventing a new apply mechanism.

#### Acceptance Criteria
- [x] `build_system` gains an OPT-IN, keyword-only `replan_on_failure: bool = False`
  parameter; the default leaves `build_system` BYTE-IDENTICAL to before this
  requirement for every existing caller/test (proven by a dedicated regression test,
  not just asserted). — **DONE 2026-07-06**
- [x] When `True` AND the build is still NOT DONE after normal acceptance +
  `_repair_system`'s targeted patch, an iterative recovery loop
  (`_replan_as_modification`) runs, bounded to `MAX_REPLAN_ROUNDS = 3`: (1) build a
  MODIFICATION request from the SPEC + the CURRENT built module sources + the FAILING
  acceptance checks' NAMES and their REAL run errors (obtained by actually running each
  check, the same feedback convention `_repair_module_for_check` already uses) — NEVER
  a check's own assertion CODE (which can embed a hidden expected value) and never any
  other oracle-only sentinel; (2) apply via `modify_system(current_modules, mod_request,
  root, llm=llm)` (REUSES the existing MODIFICATION plane, REQ-14, rather than inventing
  a new apply mechanism); (3) re-run the FULL acceptance checklist on the new modules. —
  **DONE 2026-07-06**
- [x] CONVERGENCE GATE mirroring `_repair_system`'s non-degrading floor, made STRICTER: a
  round is kept ONLY when it STRICTLY REDUCES the unmet-check COUNT AND regresses no
  check that was passing before the round (a SET comparison, so a swap-in regression on
  a different check can never slip through as a same-count coincidence); otherwise the
  round is REJECTED — every module touched that round is reverted to its pre-round
  content (disk + the returned dict) and the loop STOPS (bounded, no infinite loop,
  never worse than best-seen). — **DONE 2026-07-06**
- [x] 0-FALSE-DONE preserved (Tenet 3): `done` is always the REAL acceptance checklist
  passing after this recovery returns — the recovery can only ever produce a genuinely
  fresh passing state, never fabricate one. — **DONE 2026-07-06**
- [x] Proven OFFLINE (`tests/test_ext036_replan.py`, canned/stubbed `llm`/`modify_system`,
  no live model): (a) FIXES — a synthetic build failing 2 acceptance checks, with a
  canned `modify_system` fix, reaches `done=True`/`unmet=[]` after 1 replan round through
  the full `build_system(..., replan_on_failure=True)` pipeline; (b) NO-REGRESSION /
  NO-INFINITE-LOOP — a canned `modify_system` that makes no improvement stops after
  round 1 (never loops needlessly), and one that fixes one check while regressing a
  different, previously-passing check is REJECTED and reverted (disk + dict), the
  original still-failing check remaining the reported unmet, the previously-passing one
  never regressing; (c) BOUNDED — a canned `modify_system` that fixes exactly one more
  check per round across 4 starting-unmet checks is capped at exactly
  `MAX_REPLAN_ROUNDS = 3` accepted rounds, one check remaining unmet, proving the bound
  is real (the loop stops because of the cap, not because it ran out of progress to
  make); (d) BYTE-IDENTICAL WHEN OFF — `replan_on_failure=False` (the default, both
  implicit and explicit) never invokes `modify_system` at all and produces a result
  dict identical to before this requirement, on a fixed synthetic failing build; (e) NO
  ORACLE LEAK — the modification request built for the model contains the spec, the
  current module source, and the failing check's NAME, but never a hidden
  expected-output sentinel embedded only in the check's own assertion code (a check
  whose CODE carries a distinct sentinel that its REAL run error never surfaces is used
  to prove the exclusion directly); (f) never raises when `modify_system` itself raises,
  or when a build is already done (the recovery is a complete no-op). Full `tests/`
  suite re-run via `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`;
  no regression vs the pre-change baseline (2356 passed / 2 skipped). — **DONE
  2026-07-06**
- [ ] LIVE measurement: does replan-as-modification lift any of the currently
  repair-failing hard-tier CREATION-suite tasks (e.g. `kv-store-ttl`,
  `priority-jobqueue`)? — open, owned by the parent (this task builds and offline-proves
  the mechanism only; it does not run a live gemma measurement).

### [REQ-35] `modify_system` can ADD a new module, not just regenerate existing ones (DONE — EXT-036 TASK-45, 2026-07-06)

**Owner steer (roadmap 45508cf, task #128):** `modify_system` (REQ-14) composes
`_identify_targets`, which only ever names EXISTING modules, so a modification that
genuinely needs a brand-new module (e.g. "add rate-limiting" to a system with no
rate-limiter module yet) could never be satisfied — the modification plane could
regenerate but never GROW the system.

#### Acceptance Criteria
- [x] A deterministic-shaped, AMBIGUITY-GUARDED model judgment
  (`_identify_new_modules(modules, mod_sentence, llm)`) asks whether the modification
  requires an entirely NEW module that does not already exist; any vague/empty/
  unparseable answer (including the literal `NONE`) yields `[]` — no new module is
  added — **DONE 2026-07-06**. Names are filtered to plausible bare `*.py` filenames not
  already an existing module, de-duplicated, and BOUNDED to at most 3 new modules per
  modification (`MAX_NEW_MODULES = 3`).
- [x] Each genuinely-named new module is built via the SAME bounded syntax-gate/repair
  loop `_regenerate_module`/`_build_module` already use (`syntax_ok`/`REPAIR_PROMPT`,
  reused verbatim — no module-building logic duplicated), given the existing modules'
  sources for import context (`_build_new_module`) — **DONE 2026-07-06**. Assembled
  additively onto `root` via `_jailed_write` (Tenet 1), with `runtime` threaded through
  exactly like every other write `modify_system` performs.
- [x] The REGRESSION GATE is extended: on ANY regression (a previously-passing
  behavioral check now failing, OR the deterministic import smoke-gate's
  baseline-importable-now-broken signal, TASK-21), the modified/regenerated module(s)
  are reverted to their pre-modification content AS BEFORE, AND any newly-ADDED
  module(s) are REMOVED entirely — deleted on disk and dropped from the returned
  `modules` dict — so a rejected modification never leaves an orphaned new-module file
  or a half-wired system — **DONE 2026-07-06**.
- [x] BYTE-IDENTICAL when no new module is genuinely identified: the add-path is an
  injectable no-op — every new loop over `new_module_names`/`added_names` is simply a
  0-iteration pass, so the pre-existing regenerate-only pipeline (assembly, the
  regression gate, the best-effort new-behavior check, the returned note) is completely
  unaffected, and every pre-existing `tests/test_ext036_modify.py`/
  `tests/test_ext037_buildsystem_jaros_write.py`/`tests/test_ext037_root_enforcement.py`
  test passes unmodified — **DONE 2026-07-06**.
- [x] NEVER raises (Tenet 3): an unreachable/misbehaving model at either the
  identification or the build step degrades gracefully (no new modules identified /
  that one module's build is skipped), matching `modify_system`'s existing
  never-raise contract; `applied=False` + a diagnostic `note` on any failure. NO ORACLE
  LEAK: the identify/build prompts see only the existing module sources + the
  modification sentence, never a hidden/expected output — **DONE 2026-07-06**.
- [x] Proven OFFLINE (`tests/test_ext036_modify_add.py`, canned llm, no live model): a
  purely-additive modification (no existing target) adds a new module and keeps it when
  nothing regresses, with the write genuinely landing on disk; the regenerate-only path
  is BYTE-IDENTICAL when the model names no new module; a regression (from a changed
  existing module) reverts the regenerated module(s) AND removes the added module (file
  gone + dropped from the dict); the new-module count is bounded to at most 3 even when
  the model names 5; a vague/empty/`NONE` answer (and malformed/duplicate/existing
  names) adds nothing; a raising model at either the identify or the build step never
  crashes `modify_system`; and `runtime` is genuinely threaded to the added module's
  write (a fake recording runtime proves the write goes through a `code.write_file`
  Decision, never a raw `Path.write_text` alongside it). Full `tests/` suite re-run via
  `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`; no regression
  vs. the pre-change baseline. — **DONE 2026-07-06**

### [REQ-37] A spec-DERIVED behavioral PROPERTY check for build_system acceptance (PGS-style, arXiv 2506.18315) (DONE — offline mechanism, EXT-036 TASK-46, 2026-07-06)

**Owner directive (task #130):** the crash-based REQ-26 minimum acceptance floor (+REQ-27's
error-marker/round-trip strengthening) catches a system that *crashes* or gracefully prints
its own error, but nothing in the composed checklist catches a system that never crashes yet
behaves *semantically wrong* — e.g. a priority queue that dequeues in the wrong order, or a
codec whose `decode(encode(x)) != x`. A PGS-style (Property-Generated-and-Scored, arXiv
2506.18315) spec-derived behavioral PROPERTY check closes that class.

**SACRED-SAFE BY CONSTRUCTION:** this requirement only ever ADDS a check to the composed
acceptance checklist (REQ-26/`_compose_acceptance_checklist`) — it can flip a build's `done`
from `True` to `False` (catching a genuine semantic/ordering bug the existing checks missed)
but can **never** flip `False` to `True`, so it structurally cannot manufacture a false-done.
The only risk is an over-strict FALSE-NEGATIVE, which the tri-state grading rule below is
specifically designed to avoid.

#### Acceptance Criteria
- [x] `_derive_spec_properties(spec, llm)`: given the SPEC STRING ONLY (never the built code —
  no leak, no self-deception cycle), the model proposes 0-2 ABSTRACT behavioral properties the
  system must satisfy (e.g. "an item added with higher priority is dequeued before a
  lower-priority item"; "the reported count increases by exactly 1 after each add"; "decoding
  the encoding of X returns X"). If none is clearly derivable, `[]` — no property is invented,
  and that task keeps today's behavior exactly. Bounded to `MAX_SPEC_PROPERTIES = 2`; guarded
  (any model/parse failure yields `[]`); never raises — **DONE 2026-07-06**.
- [x] `_build_property_check(prop, mods, llm, *, plan=None)`: converts one abstract property
  into a runnable acceptance check that exercises the BUILT CLI through a REAL subprocess
  invocation (mirrors `_roundtrip_acceptance_check`/`_propose_subprocess_checklist`'s
  subprocess-only, never-`import` convention) — reusing the SAME `_is_subprocess_check` filter
  and `_minimum_entry_filename` entrypoint-resolution already proven elsewhere in this module.
  Any unusable property, no resolvable entrypoint, a model/parse failure, or code that doesn't
  survive the subprocess-check filter returns `None` — no check is added (fewer checks, never a
  fabricated one) — **DONE 2026-07-06**.
- [x] TRI-STATE GRADING RULE, encoded EXPLICITLY and enforced DETERMINISTICALLY (not left to the
  model's own code structure) via `_wrap_property_check`, which wraps the model-authored check
  body in a harness-controlled `try`/`except`:
    - **VIOLATED** — the property test RAN and its assertion DEFINITIVELY failed (a genuine
      `AssertionError`) → the check FAILS (`done` can flip to `False`, catching the bug).
    - **INCONCLUSIVE** — the CLI couldn't be invoked as the check assumed, or ANY other
      exception was raised → treated as a PASS (never manufacture a false-negative from a
      broken/mismatched test).
    - **SATISFIED** — the property test ran to completion with no exception → PASS.
  — **DONE 2026-07-06**.
- [x] Wired into `build_system` as an OPTIONAL, injectable, default-OFF keyword parameter
  (`spec_properties: bool = False`) — a complete no-op when omitted/`False`, so every existing
  caller/test is BYTE-IDENTICAL to before this task. When `True`, the derived property checks
  are UNIONED (purely additively) into the composed acceptance checklist right after the
  optional `check_reviewer` step, so `done` requires them too — never removing or weakening any
  existing check — **DONE 2026-07-06**.
- [x] NO ORACLE LEAK: `_derive_spec_properties`'s prompt is formatted from the SPEC STRING
  alone — never the built module sources, the acceptance checklist, or any expected output —
  **DONE 2026-07-06**.
- [x] Proven OFFLINE (`tests/test_ext036_property_check.py`, canned llm, no live model, no
  Jetson): (a) a wrong-ordering priority-queue build → the property is VIOLATED → the check
  FAILS → `build_system(..., spec_properties=True)` reports `done=False` (the SAME wrong build
  reports `done=True` with the flag off, proving the property check is what catches it); (b) a
  correct priority-queue build → SATISFIED → `done=True` (no new false-negative); (c) an
  inconclusive/broken property test (a `subprocess.check_call` against a nonexistent script,
  raising `CalledProcessError` — not `AssertionError` — before its own `assert` is ever reached)
  is treated as a PASS, and a mirror-image control (a genuine `AssertionError` with no exotic
  exception involved) still FAILS, proving the tri-state wrapper doesn't launder every failure
  into a pass; (d) a task with no derivable property (`"[]"`) adds no check, behavior unchanged
  (including bounding to `MAX_SPEC_PROPERTIES` when the model over-proposes, and `None` returns
  from `_build_property_check` on an unusable property/no entrypoint/malformed output/an
  in-process-only check that fails the subprocess filter); (e) never raises when the model
  raises at either the derivation or the build-check step, at both the helper-function level and
  through the full `build_system` call; (f) no-oracle-leak — the derivation prompt is asserted
  BYTE-EQUAL to `PROPERTY_DERIVATION_PROMPT.format(spec=spec)`, and none of the built module's
  source/plan JSON/expected-output text ever appears in it; (g) the flag off (by omission, and
  explicitly `False`) never calls `_derive_spec_properties` at all (monkeypatched to raise if
  called) and matches the explicit-`False` result exactly. Full `tests/` suite re-run via
  `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`; no regression vs. the
  pre-change baseline — **DONE 2026-07-06**.
- [ ] A 20-task trustbar measurement (WIN = `false_done` drops without the overall `done`-rate
  cratering) gates whether this mechanism is promoted from opt-in to default-on — open, owner
  reserved this measurement before the architect commits (task #130's own scope is the offline
  mechanism only).

### [REQ-38] Hard-tier escalation for the FIX/EDIT path (gemma → qwen-7b on repair failure)

The hard-tier escalation (REQ-13, `build_system_escalating`: gemma-4-e2b primary → qwen2.5-coder-7b
fallback on ship-failure, swap via the `:8001` model-manager) currently applies ONLY to the CREATION
path (`/buildsystem`). The FIX/EDIT path (`fix_loop`) is gemma-only with in-gemma repair retries — so a
hard bug-fix gemma can't crack never gets the stronger model. Owner directive (2026-07-07): the fix/edit
path should ALSO escalate to the 7B on repair failure, mirroring REQ-13's escalate-ONLY-on-failure
discipline (never pay for the 7B unless gemma's repair loop actually failed; keep gemma-only behavior
byte-identical when escalation is unconfigured; ALWAYS restore gemma serving afterward).

#### Acceptance Criteria
- [ ] Add an escalate-on-failure wrapper around the fix/repair loop (analogous to
      `build_system_escalating`): run gemma's repair loop first; only if it fails to produce a passing
      fix AND escalation is configured, swap to qwen-7b (via the same `_http_swap(manager_url)` seam) and
      retry the fix, returning whichever result passes.
- [ ] Gemma-only behavior is BYTE-IDENTICAL when escalation is unconfigured (no manager/registry
      coverage) — a pure no-op wrapper, never a regression (mirror REQ-13's `escalated=False` path).
- [ ] The served model is ALWAYS restored to gemma-4-e2b after an escalated fix (safety).
- [ ] Test-gated with a stubbed primary-fails/fallback-succeeds fixture proving the escalation fires
      only on failure and never leaves the caller worse off than gemma-only.

### [REQ-39] Deterministic module-body repair: length-guard / constant-index contradiction (DONE — EXT-036 TASK-49, 2026-07-08)

**MEASURED BUG (repro `.jaros-data/artifacts/kv_diag.log`, `cli.py` section):** the
`kv-store-ttl` `set` handler gemma writes is `if command == "set": if len(parts) == 3: key =
parts[1]; value = parts[2]; ttl = int(parts[3]); ...` — but `set <key> <value> <ttl>` splits
into 4 tokens, so `len(parts) == 3` is always False and every `set` SILENTLY NO-OPS (0/3 Get/
Delete behavioral checks fail). The guard is internally self-contradictory with its own body:
it requires `len(parts) == 3` yet indexes `parts[3]`, which needs `len(parts) >= 4`.
`build_system`'s bounded acceptance-driven repair loop (REQ-5) already fed this failure back
for 2 rounds live and gemma could not fix it — a deterministic tool is the lever (mirrors
`harness/import_wiring.py::resolve_imports`, EXT-035 REQ-3 — a pure, AST-only, never-raising,
purely-additive/corrective repair over generated module code, run right alongside it in
`build_system`'s assemble path).

#### Acceptance Criteria
- [x] `harness/system_builder.py::repair_guard_index_mismatch(code: str) -> str` — a PURE,
  stdlib-`ast`-only, never-raising function: finds an `If` whose test is a simple length
  comparison `len(<Name>) OP <int constant>` (either operand order, `OP` in `{==, !=, <, <=,
  >, >=}`) whose gated (true-branch) body contains a constant-index subscript `<Name>[M]` on
  the SAME name, and — ONLY when the guard's constant provably, guard-WIDE contradicts that
  index (every length value admitted by the guard makes `M` unreachable) — repairs the
  guard's own numeric constant to the MINIMAL value consistent with the body's own worst-case
  index `M` (e.g. `== M+1`). Changes ONLY that one constant (a targeted text-level splice at
  the literal's own AST span); the rest of `code` is returned byte-for-byte intact. Returns
  the input BYTE-IDENTICAL when no provable contradiction is found or on any parse failure —
  **DONE 2026-07-08**.
- [x] HONESTY (Tenet 3, conservatism over coverage — a false repair is a real regression):
  fires ONLY on a PROVABLE, guard-WIDE contradiction. A closed/bounded-above guard (`==`,
  `<`, `<=`) can be provably wrong for EVERY admitted length; an open-ended guard (`!=`, `>`,
  `>=`) never can (some admitted length always leaves the index reachable), so those ops are
  NEVER repaired. NEVER touches: an already-consistent guard; a guard on a DIFFERENT name
  than the one indexed; a variable/negative/slice index; an index confined to an `else`/
  sibling branch; a compound/chained boolean guard; or any other ambiguous shape. Never
  touches any acceptance oracle / `validate_plan` — **DONE 2026-07-08**.
- [x] Wired into `harness/system_builder.py::build_system`'s BUILD→ASSEMBLE path: applied to
  every generated module in `built`, in the same spot/pattern as the existing deterministic
  import-resolver wiring (`#EXT-035-REQ-3`) — purely additive, a no-op for code without this
  exact defect shape, and does not touch `build_system_escalating`/`build_system_governed`/
  `build_system_best_of_k`/`modify_system` or any oracle/gate logic — **DONE 2026-07-08**.
- [x] Proven OFFLINE (`tests/test_ext036_guard_index_repair.py`, no model/network): (a) the
  EXACT captured buggy `set` handler is repaired to a consistent `len(parts) == 4` guard, the
  repaired module still compiles, and a real subprocess run of the repaired module (fed a
  `set`/`get` sequence on stdin) proves `set` NO LONGER no-ops (the ORIGINAL buggy module is
  independently confirmed, via the same real run, to genuinely no-op first — a regression
  oracle, not a coincidental pass); (b) 8+ valid/ambiguous fixtures are returned
  BYTE-IDENTICAL (a correct `len(parts)==4` guard over `parts[3]`, a guard on a different name
  than the one indexed, `x[-1]`, `x[i]`, `x[1:3]`, no length guard at all, an index confined
  to an `else` branch, a compound boolean guard, and an open-ended `>`/`>=` guard); (c) `<`/
  `<=`/`!=` guards and their REVERSED operand forms (`N OP len(seq)`) are handled correctly —
  genuine `<`/`<=` contradictions are repaired to their own minimal consistent constant,
  reversed forms are correctly normalized, and `!=` (open-ended) is never touched even when
  reversed; (d) `repair_guard_index_mismatch` never raises on `None`/empty/syntactically
  malformed input — **DONE 2026-07-08**.

### [REQ-40] KEY-VALUE-aware persistence round-trip — fixes a false-negative on set/get datastores (DONE — EXT-036 TASK-52, 2026-07-08)

**MEASURED + CONFIRMED OFFLINE (2026-07-08):** the VERIFIED-CORRECT SQLite-kv leaf
(`graph_dsl.SQLITE_KV_LEAF` — passes all 5 of `sqlite-persistent-kv-cli`'s independent oracle
checks, including genuine cross-process persistence) FAILED `_minimum_acceptance` (REQ-26/27)
on exactly one check: `minimum: 'create'+'get' round-trip persists`. Two root causes in the
existing add/list round-trip derivation: (1) `_ADD_LIKE_WORDS` has no `set`/`put`/`store`, so
the spec's real write verb (`set`) was never matched and the prose word "create" (from
"create the database file") was mis-picked as the add command instead; (2)
`_roundtrip_acceptance_check` is ADD/LIST-shaped — it runs `<entry> <add> <sentinel>` then a
BARE `<entry> <list>` with no key, which structurally cannot verify a `set <key> <value>` /
`get <key>` contract (a bare `get` returns nothing). This was the real blocker keeping
`sqlite-persistent-kv-cli` from greening — not a reasoning issue.

#### Acceptance Criteria
- [x] `harness/system_builder.py::_derive_kv_roundtrip(spec) -> (set_cmd, get_cmd) | None` —
  detects a key-value SET/GET contract: the spec names a store verb (`set`/`put`/`store`) AND
  a `get` retrieve verb, both as whole words (reusing `_first_word_match`). Conservatively
  EXCLUDES a spec that describes a stdin-driven multi-command SESSION protocol
  (`_STDIN_SESSION_RE`, matching "standard input"/"stdin") — a per-command subprocess
  invocation is structurally the WRONG shape for that contract (e.g. `kv-store-ttl-cli`/
  `lru-cache-cli` also name `set`/`put`+`get` as whole words but are in-memory, single-session
  stores that never claim cross-process persistence; MEASURED via a sweep of all 24
  `ALL_CREATION_TASKS` specs that the KV round-trip fires ONLY for `sqlite-persistent-kv-cli`).
  Never raises. — **DONE 2026-07-08**
- [x] `harness/system_builder.py::_roundtrip_kv_acceptance_check(entry, set_cmd, get_cmd)` —
  from a FRESH invocation, runs `<entry> <set_cmd> <SENTINEL_KEY> <SENTINEL_VAL>` as one
  subprocess, then a SEPARATE `<entry> <get_cmd> <SENTINEL_KEY>` subprocess, and asserts the
  fixed literal `SENTINEL_VAL` appears in the get output — reading back BY THE SAME KEY it was
  just written under (unlike the add/list check's bare, keyless list). Two INDEPENDENT
  subprocess invocations (a fresh Python interpreter each time) make this a genuine
  CROSS-PROCESS persistence check: a non-persistent (in-memory-only) store cannot pass it. —
  **DONE 2026-07-08**
- [x] NO ORACLE LEAK (Tenet 3): `_KV_ROUNDTRIP_SENTINEL_KEY`/`_KV_ROUNDTRIP_SENTINEL_VAL` are
  fixed literals, never derived from/leaked into the solving prompt or from `task.checks`/
  `system_suite` — the check only asserts the system's OWN stated set/get contract holds. —
  **DONE 2026-07-08**
- [x] Wired into `_minimum_acceptance`: when the KV set/get contract is detected, the KV
  round-trip is emitted INSTEAD OF the add/list round-trip (precedence, never double-counted)
  — closes the exact mis-pairing (`'create'+'get'`) MEASURED above. A spec that only names
  add/list (e.g. `todo-list-cli`) is UNCHANGED — still gets exactly the pre-existing add/list
  round-trip. — **DONE 2026-07-08**
- [x] STRONG (Tenet 3, not weakened into a false-done): a genuinely non-persistent store
  (state kept only in a module-level dict, lost across separate process invocations) still
  FAILS the round-trip; a genuinely-persistent store (writes to disk) passes. — **DONE
  2026-07-08**
- [x] The committed SQLite-kv leaf (`graph_dsl.SQLITE_KV_LEAF`) now passes
  `_minimum_acceptance` 8/8 (was 7/8) for the real `sqlite-persistent-kv-cli` spec. — **DONE
  2026-07-08**
- [x] Proven OFFLINE (`tests/test_ext036_acceptance_completeness.py`, extended, no live
  model): `_derive_kv_roundtrip` unit behavior (finds set+get, conservative when only one
  side present, excludes the stdin-session protocol shape, a 24-task sweep confirming
  no-over-trigger, never raises); `_minimum_acceptance` prefers the KV round-trip over add/
  list for a KV spec and leaves an add/list-only spec unchanged; the real SQLite-kv leaf
  passes all 8 minimum checks (a dedicated regression test); an end-to-end `build_system` run
  against a genuinely-persistent (disk-backed) kv CLI reports `done=True`, and against a
  genuinely non-persistent (in-memory-only) kv CLI reports `done=False` with the KV
  round-trip in `unmet`; full targeted suite (`tests/test_ext036_system_builder.py -k
  "roundtrip or persist or minimum or acceptance"` plus the extended
  `test_ext036_acceptance_completeness.py`) stays green. — **DONE 2026-07-08**

### [REQ-41] Interface ledger + AST seam check — the #1 generic fix for cross-module compositional coherence (DONE — offline mechanism, EXT-036 TASK-53, 2026-07-08)

**MEASURED (design review, compositional-failure diagnosis):** `_build_module` injects a
sibling module's FULL SOURCE for a module's DIRECT imports only (REQ-3) — for a 2B model,
once a system grows past ~3 modules the exact shape of a sibling's exported call (e.g.
`db.add(title, done)`) can still get lost/guessed wrong even when the dependency's source
is present, because the one relevant `def` line is buried in a full module body and the
model has no COMPACT, system-wide view of every contract at once. The measured symptom:
the model emits a cross-module call with the WRONG shape (e.g. calls `db.add(title)` when
the built `db` module actually exports `add(title, done)`) — a "compositional/seam-wiring"
defect that generically depresses every multi-module class, not one. This is the top
generic mechanism identified to lift it: a PREVENTIVE half (make the whole system's
contract cheap and impossible to miss during generation) and a DETECTIVE half (catch a
mismatch that slips through anyway, deterministically, and route it into the existing
repair loop).

#### Acceptance Criteria
- [x] A deterministic INTERFACE LEDGER is assembled from the PLAN (never the model, never
  `task.checks` — no oracle leak): for every module, its name + responsibility + its
  exported names WITH signatures (`exports[].signature`). — **DONE 2026-07-08**
  (`harness/system_builder.py::_build_interface_ledger`)
- [x] The ledger is injected into EVERY `_build_module` call (the WHOLE system's contract,
  not just one module's own direct imports), while FULL SOURCE injection stays reserved for
  a module's DIRECT imports only (`m.get("imports")`, unchanged from REQ-3) — the ledger
  costs ~10x fewer tokens than bodies, so the whole contract fits the small model's context
  window even past the point where full-source-only injection alone would blow it. — **DONE
  2026-07-08** (`_build_module`'s new `plan=` parameter; `build_system`'s BUILD loop passes
  `plan=plan` on its one call site)
- [x] Preserves current behavior when a module has no plan/exports — degrades to today's
  behavior (an empty ledger, byte-identical prompt otherwise), never crashes. — **DONE
  2026-07-08** (`plan=None`, the default, is a complete no-op; every pre-existing
  `_build_module` caller is unaffected)
- [x] A deterministic, POST-ASSEMBLE AST seam check (`check_interface_seams`): scans every
  built module for cross-module calls (`alias.method(...)` where `alias` is bound to a
  sibling module via a plain `import <sibling>`) and verifies each resolves to a top-level
  function/class of that sibling with COMPATIBLE positional arity (accounting for
  defaults/`*args`, `self`/`cls` excluded for a class `__init__`). — **DONE 2026-07-08**
- [x] CONSERVATIVE by construction (a false positive that forces needless repair is worse
  than a miss, per Tenet 3): NEVER flags a call using any keyword argument or starred
  (`*args`/`**kwargs`) unpacking; NEVER flags a call resolving to a plain module-level VALUE
  (arity unknowable) or to a symbol it cannot confidently resolve (arity-only, not a
  name-mismatch heuristic); NEVER judges a module whose surface is UNCERTAIN (a wildcard
  `from x import *`, a module-level `__getattr__` — PEP 562 — or a call to
  `globals`/`setattr`/`exec`/`eval` anywhere in it); stdlib calls and same-module calls are
  never even candidates (only a local `import <sibling>` of another built module is
  considered). Never raises on malformed/non-string input. — **DONE 2026-07-08**
- [x] On a CONFIDENT mismatch, produces a CONCRETE message (e.g. "main.py calls
  db.add(title) [1 arg] but db.py defines add(...) requiring 2 args") and feeds it into the
  EXISTING `_repair_system` (REQ-5) repair loop as a genuinely DYNAMIC unmet check — a
  self-contained, stdlib-only script that RE-DERIVES the same check fresh from the files on
  disk each run (never a static always-fail marker), so a later repair round that fixes
  EITHER side of the mismatch (the caller's call site or the callee's signature) makes it
  pass for real. Purely ADDITIVE to the composed acceptance checklist (never removes/weakens
  an existing check); runs AFTER the optional 7B-review step (REQ-30) so a deterministic,
  ground-truth seam finding is never treated as a reviewable model proposal — peer to the
  deterministic minimum (REQ-26), always gated as-is. — **DONE 2026-07-08**
  (`harness/system_builder.py::_seam_check_code`, wired into `build_system` right before the
  acceptance checklist's empty-check guard)
- [x] NO ORACLE LEAK (Tenet 3): the ledger derives only from the PLAN (itself derived from
  the visible spec); the seam check derives only from the assembled module SOURCE — neither
  ever reads `task.checks` or any held-out oracle. Does not weaken any existing acceptance
  gate — purely additive to the composed checklist. — **DONE 2026-07-08**
- [x] Every `build_system`-family wrapper (`build_system_escalating`,
  `build_system_governed`, `build_system_best_of_k`) calls `build_system` internally, so all
  of them inherit the ledger + seam check for free with no additional wiring. — **DONE
  2026-07-08** (verified by inspection: the single `_build_module` call site and the single
  seam-check wiring point both live inside `build_system` itself)
- [x] Proven OFFLINE (`tests/test_ext036_interface_seam.py`, no live model): ledger assembly
  contains every module's exported signatures and degrades gracefully on a missing/malformed
  plan; a module's build prompt carries the WHOLE ledger but FULL SOURCE only for its direct
  imports (a non-imported sibling's signature appears in the ledger, never its full source);
  the seam check catches the exact measured arity-mismatch shape with the concrete message,
  does NOT flag a correct-arity call, correctly judges class-constructor arity and
  defaults/`*args`, and is proven conservative (same-module calls, stdlib calls, keyword/
  starred calls, and calls into a dynamic/uncertain module are never flagged, and an
  unresolved symbol is deliberately not treated as a name-mismatch); the generated seam
  check script is proven genuinely DYNAMIC (fails while the mismatch stands, passes once a
  real fix is applied to either side, driven as a real subprocess); and an end-to-end
  `build_system` run with a canned 2-module arity-mismatch draw shows the seam finding
  enters `unmet` and the SAME repair loop that fixes the underlying no-crash defect also
  resolves the seam check, reaching `done=True`, while a correct-arity draw is never
  flagged. Full targeted suite (`tests/test_ext036_system_builder.py`,
  `tests/test_ext036_system_repair.py`, `tests/test_ext036_interface_seam.py`) stays green;
  no regression to the byte-identical direct-imports-full-source behavior REQ-3 already
  proved.

### [REQ-42] Execution-feedback enrichment — repair sees the ACTUAL wrong output, not a bare AssertionError

MEASURED (2026-07-08, csv-column-aggregator, the sole 0/2 weak class on the harder scoreboard):
build_system produces a multi-module system that RUNS cleanly (rc=0, no exception) but prints
the WRONG value (`0.00` for every aggregate; expected `35.00`/`15.00`) — a plan-signature-induced
sibling bug (`parse_csv_stream -> list[list[float]]` floats the string name column, drops all rows).
`done=False` is correctly detected, but the repair round fails to fix it. Root cause: the repair
feedback (`_repair_module_for_check`'s `error`) for a wrong-VALUE failure is a bare `AssertionError`
traceback that does NOT show the built system's actual output — the model is told "assert '35.00' in
output failed" but never that the output was `0.00`, so it cannot localize the defect. This is the
"runs but prints wrong" failure class generically (not csv-specific): the biggest per-task repair
lift is making execution feedback carry the concrete observed-vs-expected signal.

#### Acceptance Criteria
- [x] When an acceptance check fails on a wrong VALUE (assertion mismatch, not a crash/timeout), the
      repair feedback fed to the model includes the built system's ACTUAL observed output (the stdout/
      stderr it produced for that check's scenario) alongside the expected value — e.g. "expected
      '35.00' in output, got: '0.00'".
- [x] Implemented generically for the deterministic acceptance checks (no per-class special-casing);
      honest and leak-free (it surfaces the built system's OWN output vs the expected already encoded
      in the check — never the hidden suite oracle, never the reference implementation).
- [x] A unit test proves that for a build whose entrypoint prints the wrong value, the string handed
      to `_repair_module_for_check` (or the repair prompt it builds) contains the actual observed
      output, whereas today it contains only a bare AssertionError. Offline (no model/Jetson call).
- [x] No regression: `tests/test_ext036_system_repair.py` + `tests/test_ext036_system_builder.py`
      stay green; the non-degrading repair guarantee (REQ-23) is preserved.

### [REQ-43] Single-file retry fallback — recover from OVER-DECOMPOSITION of a simple spec

MEASURED + CONFIRMED (2026-07-08, csv-column-aggregator, the sole 0/2 harder-scoreboard class, still
0/3 after the REQ-42 feedback fix): the task is trivially solvable in ~12 lines single-file (verified: a
hand-written single-file version passes both independent checks), but the model OVER-DECOMPOSES it into
3 modules and bakes a defect into a sibling's design (a `parse_csv_stream -> list[list[float]]` signature
that floats the string column and drops every row -> prints 0.00). Repairing MODULE code cannot fix a
wrong PLAN. The generic lever (not csv-specific): when a multi-module build fails acceptance, ALSO try
building the whole system as ONE file and keep whichever passes — a single file has no seams/cross-module
signatures to botch, which is exactly the failure class.

#### Acceptance Criteria
- [x] When `build_system`'s repair loop finishes NOT done AND the plan produced more than one module,
      it performs ONE single-file retry: build the entire system as a single `main.py` module from the
      same spec, then grade it against the SAME composed acceptance checklist.
- [x] Non-degrading + additive: the better of {multi-module result, single-file result} is kept
      (done > shipped > fewer-unmet); a build that was already `done` is never retried, and the retry
      can only improve or leave the result unchanged — it can NEVER regress a passing multi-module build
      or manufacture a false-done (graded by the same real checks).
- [x] Honest + leak-free: the single-file retry sees only the spec (never the suite oracle / reference /
      independent checks); the kept result's `build_path` records that a single-file retry was used.
- [x] Tests prove: a spec whose multi-module build stays unmet triggers the single-file retry and the
      single-file result is kept when it scores better; a spec whose multi-module build is already done
      is NOT retried (byte-identical). Offline where possible (mock the build calls); no oracle leak.
- [x] No regression to the existing repair/escalation flow; `tests/test_ext036_system_builder.py` +
      `tests/test_ext036_system_repair.py` stay green.

**REFINED 2026-07-08 (TASK-56):** MEASURED that the mechanism above, as first committed, did NOT
actually recover csv-column-aggregator — the single-file retry's build call routed through
`_build_module`/`BUILD_PROMPT`, the SAME plan-laden prompt path (carrying the retry's own synthetic
module's responsibility framing) every other module build uses, so the model reproduced the identical
over-decomposed shape the retry exists to escape and the class stayed 0/3. PROVEN FIX: a hand-verified
direct probe showed that prompting the model with a clean, single-purpose instruction — "write the whole
system in one file, output only code," carrying NO plan/responsibility/signature/interface-ledger
context — produces a correct solution first try. `harness/system_builder.py` now builds the retry's
candidate via a dedicated `SINGLE_FILE_PROMPT`/`_build_single_file` (a direct `_call` + the same
`syntax_ok`/`REPAIR_PROMPT` gate `_build_module` uses, only the prompt differs) instead of
`_build_module`. Every other guarantee above (non-degrading `_better_result` ranking, honest/leak-free
grading against the same composed checklist, atomic adopt + rollback against `root`) is unchanged.
Proven OFFLINE (`tests/test_ext036_system_builder.py`, canned `_call`, no live model).

### [REQ-44] Modify path — bounded, regression-gated NEW-BEHAVIOR repair loop

MEASURED (2026-07-09, sql-mini-add-projection, the sole 0/2 modify-frontier class — also the soft
spot on the build side): `modify_system` regenerates the target module ONCE, hard-gates on the
REGRESSION checks (existing behavior preserved — correct), then checks new behavior only ADVISORILY
and ships regardless. So a regression-safe-but-behaviorally-WRONG edit (the model wrote a `SELECT
<col>` projection branch guarded by `parts[1] in tables` where `parts[1]` is the column not the
table → projection outputs nothing) just ships with `new_behavior_ok=False` and is never repaired.
The build path has an acceptance-repair loop; the modify path has none. Add the analog: when the
applied edit preserves regression but fails the new-behavior checks, feed the model its ACTUAL wrong
output (the REQ-42 enriched feedback) and re-regenerate, bounded — keeping a re-try ONLY if it still
preserves regression AND passes strictly more new-behavior checks.

#### Acceptance Criteria
- [x] After `modify_system`'s regression-gated apply, if the new-behavior checks (derived from
      `mod_sentence`) do not all pass, run a BOUNDED repair loop (≤2 rounds) that re-regenerates the
      target module(s) given the change request + the concrete failing new-behavior output (reuse the
      REQ-42 enriched `_run_check_verbose` feedback), re-assembles, and re-evaluates.
- [x] NON-DEGRADING + REGRESSION-SAFE by construction: a re-regeneration is kept ONLY if it still
      passes ALL baseline/regression checks AND passes strictly more new-behavior checks than the
      current best; otherwise it is reverted (disk + returned dict). The regression guarantee (REQ-14)
      is never weakened, and the loop can only improve or leave the result unchanged.
- [x] Honest: `applied` still does not strictly REQUIRE new behavior (a model-authored new-behavior
      check can be wrong), but `new_behavior_ok` reflects the repaired result; no oracle leak (the
      loop sees only the built system's own output + `mod_sentence`, never the suite's independent
      checks). Bounded — never an unbounded loop.
- [x] Tests (offline, injected llm): an edit that is regression-safe but new-broken is driven to
      new-behavior-passing by the repair loop and kept; an edit whose retry would regress is reverted;
      an already-fully-working edit is not repaired (byte-identical). `tests/test_ext036_system_repair.py`
      + `tests/test_ext036_system_builder.py` stay green.

### [REQ-45] Deterministic signature-contract repair — restore a documented default parameter gemma's build silently dropped

MEASURED via `.jaros-data/sigcontract_probe.py` (2026-07-08/09) on the retry/backoff-lib real-system
task, currently pass@1 0/3: gemma writes a library function with CORRECT LOGIC but DROPS a documented
default parameter -- it emits `def retry(times, exceptions):` while the visible build spec documents
the signature in backticks as `retry(times, exceptions=Exception)`, and the spec's own primary usage
`@retry(times=3)` then raises `TypeError: retry() missing 1 required positional argument: 'exceptions'`.
This is analogous to the existing deterministic import-resolver (EXT-035 REQ-3) / entrypoint-not-listed
(REQ-1) / guard-index (REQ-39) repairs already wired into `build_system` -- a deterministic AST-level
fix for a specific, provably-safe defect shape, not a model re-call. The prototype's
`repair_signature_defaults` applied to gemma's actual retry.py source makes `retry(times=3)` work --
confirmed via the full import-driver oracle (`accepted=True`).

#### Acceptance Criteria
- [ ] Documented-default extraction: a `documented_defaults(spec_text)` helper parses backtick-quoted
      `name(params)` signatures containing at least one `param=default` from the visible spec text, via
      `ast`, and returns `{func: {param: default_src}}`; malformed signatures are skipped, never raise.
- [ ] Repair transform: a `repair_signature_defaults(code, documented)` helper adds a
      documented-but-missing default to each matching top-level function def via AST (`ast.unparse` +
      `ast.fix_missing_locations`), ONLY when doing so keeps the signature legal (no bare parameter
      after a defaulted one); returns the code unchanged with a note if the code doesn't parse; never
      removes/alters an existing default; returns `(new_code, changed, notes)`.
- [ ] Wired into `harness/system_builder.py`'s `build_system` deterministic-repair pass over the built
      modules (same seam/style as the import-resolver / guard-index repairs), using the build's own
      spec text, before the acceptance checklist is composed.
- [ ] Leak-free (Tenet 3): the added default value comes only from the visible build spec text, never
      from a hidden oracle/test/reference implementation.
- [ ] Proven OFFLINE (no model/Jetson call) with tests covering: gemma's actual bad `retry()`
      reproduction is repaired and the documented usage then works; an already-correct signature is a
      no-op (idempotent, `changed=False`); a documented default whose insertion would be illegal is
      left unchanged, never raising; a function not documented in the spec is untouched.

### [REQ-46] Deterministic spec-demanded filename/entrypoint normalization

MEASURED via two validated prototypes: `.jaros-data/filename_norm_probe.py` (memoize-lib case,
`accepted=True`) -- gemma emits CORRECT `memoize(maxsize=128)` logic but names the file
`test_memoize.py` instead of the spec-demanded `memoize.py`; the import oracle does `import memoize`
-> `ModuleNotFoundError`. Renaming the sole module to the spec-demanded name greens the full import
oracle. And `.jaros-data/entrypoint_norm_probe.py` (INI cli-exact case, `accepted=True`, exact stdout
matched) -- gemma emits CORRECT logic split across `config_parser.py` + `cli_handler.py`, but there is
no `main.py` and `cli_handler.py`'s top-level `main(args)` has no `if __name__ == '__main__'` guard, so
the cli-exact grader finds no runnable entrypoint. The fix: pick the ROOT module (imports a local
sibling, imported by no sibling) and rename it to the spec-demanded `main.py`, injecting a `__main__`
guard that calls `main(sys.argv[1:])`. This is analogous to the already-landed deterministic
import-resolver (EXT-035 REQ-3), guard-index repair (REQ-39), and signature-contract repair (REQ-45)
already wired into `build_system` -- an AST-based, leak-free, non-degrading repair over the built
modules, not a model re-call.

#### Acceptance Criteria
- [ ] `demanded_filenames(spec_text)` parses filenames the visible spec explicitly demands (e.g. a
      "file named `X.py`" or "file named X.py" phrasing) via regex, deduplicated, order-preserving.
- [ ] `normalize_entrypoint(modules, spec_text)` is a UNIFIED repair covering both measured shapes:
      (a) single-module rename when exactly one module exists and the demanded filename is absent, and
      (b) multi-module entrypoint designation -- the entrypoint is the unique module that imports a
      local sibling and is imported by no sibling (the "root") -- renamed to the demanded filename; if
      that entrypoint defines a top-level `main(...)` with no `if __name__ == '__main__'` guard, inject
      one, calling `main(sys.argv[1:])` when `main` takes >=1 positional parameter (inspected via
      `ast`) else `main()`.
- [ ] Renaming is SAFE: only ever renames a module that is imported by no local sibling (so no
      sibling's `import` statement breaks); sibling modules keep their original names.
- [ ] Non-degrading: a no-op (returns the input modules unchanged, plus an explanatory note) when the
      demanded filename is already present, when the entrypoint is ambiguous (zero or more than one
      candidate root/single module), or when any relevant module's code fails to parse. Never raises.
- [ ] Leak-free (Tenet 3): the demanded target filename(s) come ONLY from the visible build spec text
      handed to `demanded_filenames`, never from a hidden oracle, test, or reference implementation.
- [ ] `apply_filename_contract(modules, spec_text)` maps the repair across the demanded filenames and
      is wired into `harness/system_builder.py`'s `build_system`, as a deterministic pass over `built`
      using `spec`, in the same seam/style as the import-resolver (EXT-035-REQ-3), guard-index
      (EXT-036-REQ-39), and signature-contract (EXT-036-REQ-45) repairs, before the ASSEMBLE step.
- [ ] Proven OFFLINE (no model/Jetson call) with tests covering: the memoize single-module rename
      case; the INI multi-module entrypoint-designation + `__main__` guard injection case (verifying
      the injected call matches `main`'s arity); a no-op when the demanded file is already present; a
      no-op/safe outcome when the entrypoint is ambiguous; correct `main()` vs `main(sys.argv[1:])`
      guard-call selection; never raising on unparseable code.

### [REQ-47] Stdlib `http.server` launch+drive mode for the server oracle (DONE — EXT-036 TASK-60, 2026-07-09)

**Owner directive (2026-07-09):** the next real-systems rung is SaaS/cloud Python systems (REST APIs,
DB-backed services), starting with a stdlib REST API + SQLite service, graded HONESTLY by actually running
it and hitting it over HTTP. MEASURED: `harness/server_oracle.py::serve_and_check` only knows how to launch
a FastAPI/Starlette app via `uvicorn` or a Flask app via `flask run` (see `_launch`, keyed off
`detect_web_service`'s ASGI/WSGI `kind`) — a plain stdlib `http.server`/`socketserver` service (no framework
dependency at all) has neither an ASGI/WSGI app object nor a `uvicorn`/`flask` CLI entrypoint, so it cannot be
launched or HTTP-verified by the existing oracle, and would silently fall back to the import-only smoke
checklist exactly like the FastAPI hollow-pass gap REQ-22 fixed.

#### Acceptance Criteria
- [x] `harness/server_oracle.py::detect_stdlib_http_service(modules)` — best-effort, never-raise scan of
  module SOURCES (`{filename: code}`) that returns the entry FILENAME (e.g. `"main.py"`) of the first module
  using `http.server`/`socketserver` (`HTTPServer`/`ThreadingHTTPServer`) with NO Flask/FastAPI/Starlette
  import present (those route through the existing `detect_web_service`), else `None`.
- [x] `harness/server_oracle.py::serve_and_check_stdlib(root, entry, http_checks, *, startup_timeout,
  request_timeout, env=None)` — the stdlib analog of `serve_and_check`: picks a FREE ephemeral localhost port
  via the EXISTING `_free_port()`, launches the service as a plain SCRIPT (`python <entry>` in `root`) with
  the child environment given `PORT=<port>` (the 12-factor "listen on `$PORT`" contract a stdlib service is
  expected to read via `os.environ["PORT"]`, since there is no `--port` CLI flag convention for a bare
  script), waits for the port via the EXISTING `_wait_for_port`, and drives every check via the EXISTING
  `_check_one`/`_do_request` — the SAME `http_check` dict contract `serve_and_check` uses (`method`, `path`,
  optional `status`/`json_contains`/`body_contains`).
- [x] Returns the SAME result shape as `serve_and_check`: `{"ok": bool, "results": [per-check dicts], "note":
  str}`.
- [x] ALWAYS tears the launched process (and descendants) down via the EXISTING `_kill_tree` in a `finally`
  block — no orphaned process on any path, pass or fail — proven with a precise no-orphan check (the exact
  allocated port is bindable again immediately after teardown).
- [x] NEVER raises: a missing/invalid `entry`, a bad `root`, an unlaunchable process, a server that never
  binds, or a malformed check dict is always reported as `ok: False` with a diagnostic `note` (including a
  stderr tail on a bind failure) — never coerced to a pass, never propagates an exception.
- [x] Proven OFFLINE (no model/Jetson call): a HAND-WRITTEN stdlib fixture serving `GET /health` and a
  `POST`/`GET /items` round-trip passes end-to-end; a broken fixture (wrong status/body) fails honestly; a
  fixture that never binds fails with a note and leaves no orphan; garbage input (missing entry, non-dict
  checks) never raises. `tests/test_ext036_server_oracle_stdlib.py`.

### [REQ-48] Deterministic http.server SCAFFOLD repair — wire a recognized handler into a real serve loop

MEASURED via `.jaros-data/artifacts/saas_diag.log` (2026-07-09, the first on-Jetson SaaS build, 0/3
against `REST_SQLITE_CRUD_TASK`): gemma writes CORRECT business logic -- a SQLite DB layer
(`database.py`) and a request-routing handler (`api.py`'s `APIHandler.handle_request(method, path,
data) -> (status, body)`) -- but the entrypoint (`main.py`) it emits imports `http.server`/
`socketserver` and then NEVER calls `HTTPServer(...).serve_forever()`: it re-declares a stray
`DatabaseManager` stub and stops. No real server ever binds the `PORT` the stdlib server oracle
(REQ-47's `serve_and_check_stdlib`) expects, so every http check fails before a single request is
sent -- a build-time gap, not a request-handling gap. This is a TWO-PLANE fix, the same shape as the
already-landed deterministic filename/signature/guard-index contract repairs (REQ-45/REQ-46,
EXT-035 REQ-3): the model supplies the judgement (the routing + DB logic already in `built`); a
deterministic tool supplies the mechanical scaffold (the event loop + PORT binding + request
parsing/dispatch). Validated via `.jaros-data/saas_scaffold_probe.py`: gemma's measured
`(method, path, data) -> (status, body)` dispatcher shape is recognized by a plain AST scan and,
wired into a generated stdlib skeleton, actually binds `PORT` and passes a full
`serve_and_check_stdlib` POST/GET/DELETE round-trip.

#### Acceptance Criteria
- [x] `spec_demands_stdlib_http_service(spec_text)` detects a visible spec that demands a plain
      stdlib `http.server` service (mentions `http.server`/"web service"/"REST"/"PORT environment
      variable" AND names at least one HTTP-method endpoint), leak-free (reads only the visible spec
      text), never raises.
- [x] `has_real_serve_loop(modules)` detects whether ANY built module already contains a real serve
      construct (`serve_forever(`/`HTTPServer(`/`ThreadingHTTPServer(`/`TCPServer(`) -- the
      non-degrading guard so an already-working service is never touched.
- [x] `find_dispatch_handler(modules)` is a best-effort, never-raising AST scan that confidently
      recognizes gemma's measured dispatcher shape (a class method or top-level function taking
      exactly 3 params after `self` and returning >=2 distinct 2-element tuples), including a
      confident no-arg-instantiability check for the enclosing class's `__init__` when the match is a
      method.
- [x] `generate_skeleton(handler, *, same_module, existing_code=None)` deterministically composes a
      correct stdlib `http.server` MAIN skeleton: reads `port = int(os.environ.get("PORT",
      "8000"))`, defines a `BaseHTTPRequestHandler` subclass with `do_GET`/`do_POST`/`do_PUT`/
      `do_DELETE`/`do_PATCH` that parse the method/path/JSON body and dispatch to the recognized
      handler, and runs `HTTPServer(("", port), ...).serve_forever()` under `if __name__ ==
      "__main__":`. Wires an already-recognized handler either by IMPORTING it (different module
      than the entrypoint) or by APPENDING the wiring block to the entrypoint's own existing code
      (handler already defined there) -- never destroys sibling modules' logic.
- [x] `apply_http_service_scaffold(modules, spec_text, *, llm=None)` is the public, non-degrading,
      never-raising repair: fires ONLY when `spec_demands_stdlib_http_service` is true AND
      `has_real_serve_loop` is false AND no Flask/FastAPI/Starlette service is detected
      (`harness.server_oracle.detect_web_service`, that shape belongs to the OTHER oracle path);
      resolves the entry filename via `harness.filename_contract.demanded_filenames` (falling back to
      `main.py`); wires a confidently-recognized handler via `generate_skeleton`; when no handler is
      confidently recognizable AND an `llm` is supplied, falls back to ONE targeted clean-prompt retry
      (the REQ-43 analog: a single self-contained call re-asking the model for one `main.py`
      implementing the endpoints inside this module's own skeleton contract, built ONLY from the
      visible spec text -- no oracle leak); with no recognizable handler and no `llm`, a safe no-op.
- [x] Wired into `harness/system_builder.py`'s `build_system` deterministic-repair pass over the built
      modules (same seam/style as the import-resolver, guard-index, signature-contract, and
      filename-contract repairs), after the filename-contract repair and before the ASSEMBLE step,
      passing the build's own `llm` through for the fallback retry.
- [x] Proven OFFLINE (no model/Jetson call) with tests covering: gemma's actual measured handler
      shape is recognized and wired, and the REPAIRED `main.py`, when actually RUN with `PORT` set,
      binds the port and passes a real `serve_and_check_stdlib` POST/GET/DELETE round-trip
      end-to-end; a no-op when a real serve loop already exists; a no-op/safe outcome when the spec
      is not a web service or a Flask/FastAPI service is detected; never raising on garbage input.
      `tests/test_ext036_http_service_scaffold.py`.

### [REQ-49] Deterministic AGENT-LOOP SCAFFOLD repair — wire a correct tool-calling protocol boilerplate loop

MEASURED via `.jaros-data/artifacts/realsys_agent.log` (2026-07-09, the first on-Jetson agent
build, 0/3 against `plain-tool-calling-agent`): gemma builds the AGENT LOGIC (the goal reasoning
shape) but mis-handles the mechanical OpenAI tool-call PARSING boilerplate `harness/agent_oracle.py`
pins as the injection contract -- 2 of 3 built agents made ZERO tool calls at all (no
request/dispatch loop ever wired), and 1 of 3 extracted the WRONG JSON field for a tool's
arguments (grabbed `tool_call_id` instead of `function.arguments`). This is the direct analog of
the already-landed `http.server` scaffold repair (REQ-48): a TWO-PLANE fix where the model supplies
the judgement (WHICH tool to call, decided entirely at RUNTIME through the actual chat-completions
responses it sends -- never baked into build-time code) and a deterministic tool supplies the
MECHANICAL protocol boilerplate (parse `tool_calls[].function.name` + `json.loads(.arguments)`,
POST to `{JAROS_TOOL_URL}/<name>`, feed the observation back into the message list, loop, and emit
the `__JAROS_AGENT_FINAL__...__END__` sentinel on termination).

#### Acceptance Criteria
- [x] `spec_demands_tool_calling_agent(spec_text)` detects a visible spec that demands the pinned
      OpenAI-protocol tool-calling agent contract (`OPENAI_BASE_URL`/`JAROS_TOOL_URL`/"tool
      calling"/`tool_calls` conventions AND a chat-completions round-trip), leak-free (reads only
      the visible spec text), never raises.
- [x] `has_correct_agent_loop(modules)` is a generous, never-raising heuristic scan recognizing
      whether the built modules (combined) ALREADY correctly perform the full mechanical protocol:
      a `JAROS_TOOL_URL`-addressed tool dispatch, a `tool_calls` field read, tool-name extraction
      via `["function"]["name"]` (never a wrong sibling key), `json.loads(...)` applied to the
      `arguments` field, and the `__JAROS_AGENT_FINAL__` sentinel -- the non-degrading guard so an
      already-working agent (including one with extra task-specific logic layered on top) is never
      touched.
- [x] `generate_agent_skeleton()` deterministically returns the standard, correct tool-calling
      agent-loop skeleton (stdlib-only: `json`/`os`/`sys`/`urllib.request`) -- reads
      `OPENAI_BASE_URL`/`JAROS_TOOL_URL` and the goal from `sys.argv[1]`, loops POSTing the message
      list to `{OPENAI_BASE_URL}/chat/completions`, on a `tool_calls` response extracts
      `["function"]["name"]` + `json.loads(["function"]["arguments"])`, POSTs to
      `{JAROS_TOOL_URL}/<name>`, appends the observation as a tool message and continues; on a
      plain-content response, prints the `__JAROS_AGENT_FINAL__...__END__` sentinel and exits 0.
- [x] `apply_agent_scaffold(modules, spec_text, *, llm=None)` is the public, non-degrading,
      never-raising repair: fires ONLY when `spec_demands_tool_calling_agent` is true AND
      `has_correct_agent_loop` is false; resolves the entry filename via
      `harness.filename_contract.demanded_filenames` (falling back to `main.py`) and REPLACES it
      wholesale with `generate_agent_skeleton()`'s output (the mechanical loop is fixed/standard,
      so it is always generated fresh rather than patched); `llm` is accepted for call-site parity
      with the sibling `http.server` scaffold but is intentionally unused (no separable build-time
      judgement fragment exists here worth a retry over).
- [x] Wired into `harness/system_builder.py`'s `build_system` deterministic-repair pass, immediately
      after the `http.server` scaffold repair (REQ-48) and before the ASSEMBLE step, passing the
      build's own `llm` through for API parity.
- [x] Proven OFFLINE (no model/Jetson call) with tests covering: applying the scaffold to
      RECONSTRUCTED measured-broken shapes (zero tool calls; wrong-field extraction; an empty
      build) and then DRIVING the repaired agent through `harness.agent_oracle.drive_agent`/
      `check_agent` against `harness.real_systems_suite.PLAIN_AGENT_TASK`'s own scripted
      2-tool-call-then-final oracle spec asserts the repaired agent actually PASSES; a no-op when a
      correct loop already exists (including idempotency on the scaffold's own generated output);
      a no-op when the spec is not this agent contract; never raising on garbage input.
      `tests/test_ext036_agent_scaffold.py`.

### [REQ-50] Deterministic PORT int-coercion repair — fix a str-typed port at the server bind site

MEASURED ROOT CAUSE (diagnosed via code-dump, `scratchpad/saas_crud_diag.out`): the canonical-board
SaaS HTTP-service classes (rest-sqlite-crud CREATE and rest-put MODIFY) both measure 0/3 because
gemma writes FULLY CORRECT service logic -- a real SQLite layer, real routing, a REAL serve loop
(so `has_real_serve_loop`, REQ-48's non-degrading guard, correctly no-ops) -- but reads the port
from the environment as a STRING and passes it un-coerced to the server bind site:

    port = os.getenv("PORT")
    with socketserver.TCPServer(("", port), handler) as httpd:   # port is a str

`TypeError: 'str' object cannot be interpreted as an integer` is raised at bind time, so the
service never binds and every http check fails before a single request is sent -- a build-time
gap, not a request-handling gap. This is the direct analog of the already-landed deterministic
signature-contract (REQ-45), filename-contract (REQ-46), and http.server-scaffold (REQ-48)
repairs: a mechanical AST pass over the built modules, never a model re-call.

#### Acceptance Criteria
- [x] `coerce_ports_in_code(code)` parses with `ast` and wraps the PORT element of a recognized
  stdlib server bind-site tuple in `int(...)` if it isn't already an int literal or an `int(...)`
  call. Recognized bind sites: `HTTPServer`/`ThreadingHTTPServer`/`socketserver.TCPServer`/
  `socketserver.ThreadingTCPServer`/`TCPServer`/`ThreadingTCPServer` (and `http.server.HTTPServer`)
  constructor calls whose first positional arg is a `(host, port)` 2-tuple, and a
  `<sock>.bind((host, port))` call.
- [x] Idempotent + non-degrading: a port is always numeric, so `int(<expr>)` is a no-op on an
  already-int expression and a correct coercion on a numeric string; an already-int-literal or
  already-`int(...)`-wrapped port element is left byte-identical. Never raises: any parse/unparse
  failure, or a module with no recognized bind site, leaves the code byte-identical.
- [x] `apply_port_coercion(modules)` maps `coerce_ports_in_code` across a `{module: code}` dict,
  returning a NEW dict where only the modules that actually got a coercion differ from the input.
- [x] Wired into `harness/system_builder.py`'s `build_system` deterministic-repair pass, right
  after the filename-contract repair (REQ-46) and BEFORE the http.server scaffold repair (REQ-48)
  -- so a correct-but-str-port serve loop is fixed IN PLACE rather than scaffolded over.
- [x] Proven OFFLINE (no model/Jetson call): the EXACT measured broken shape
  (`os.getenv("PORT")` -> `socketserver.TCPServer(("", port), handler)`) is repaired and then
  actually RUN with a str-typed `PORT` env var, binding the port and passing a real
  `serve_and_check_stdlib` round-trip end-to-end (with an unrepaired control proving the same
  fixture genuinely fails to bind without the fix); the `HTTPServer` and raw `sock.bind` variants
  are recognized and coerced; idempotency on an already-`int(...)`/int-literal port; never raises
  on garbage/unparseable input; `apply_port_coercion` over a multi-module dict changes only the
  offending module. `tests/test_ext036_port_coercion.py`.

### [REQ-51] The stdlib-HTTP-service ROUTING CONTRACT — two-plane thesis applied at the PROMPT level for the SaaS service tier (DONE — EXT-036 TASK-64, 2026-07-10)

MEASURED MOTIVATION (4 code-dumped draws, `.jaros-data/artifacts/saas_diag.log` + the port-coercion/
scaffold repairs already landed as REQ-45/46/48/50): gemma builds CORRECT DB/business logic but its
hand-rolled `http.server` PROTOCOL is UNSTABLE per draw — draw shapes seen: `api.py` with
`handle_request(request, db_manager)` (passing a FUNCTION where `TCPServer` needs a handler CLASS,
hallucinating `request.end_positive()`), an earlier `handle_request(method, path, data) -> (status,
body)`, an `api_handler.py` that failed the syntax gate, plus a str-PORT crash (fixed by REQ-50's
port-coercion repair). Post-PORT-lever both canonical SaaS classes still measured 0/3 ("http checks
failed"). CONCLUSION: extraction can't chase every per-draw shape; instead CONTRACT the model's
output and let the deterministic plane own ALL protocol — the same two-plane thesis (Tenet 1) already
proven at the tool/agent level, applied here at the PROMPT level for the stdlib SaaS service tier.

Two halves:
(A) PROMPT half — every per-module build prompt, for a spec demanding a stdlib `http.server`
service, is told to expose EXACTLY a pure `def route(method: str, path: str, body: dict | None) ->
tuple[int, dict | list | None]:` function and write NO protocol code (no `http.server`/
`socketserver`/`socket`/serve loop, no reading `PORT`).
(B) SCAFFOLD half — the deterministic scaffold ALWAYS recognizes a top-level `route()` and wires a
generated, correct `BaseHTTPRequestHandler`/`HTTPServer` driver around it, REPLACING whatever
entrypoint/serve-loop code the model emitted (broken OR already-working) — the routing contract, once
honored, takes precedence over every older per-draw recognition path.

#### Acceptance Criteria
- [x] `harness/system_builder.py`'s `_routing_contract_guidance(spec)` returns the fixed
  `ROUTING_CONTRACT_GUIDANCE` instruction text (the exact `def route(method: str, path: str, body:
  dict | None) -> tuple[int, dict | list | None]:` contract, a ban on `http.server`/`socketserver`/
  `socket`/any serve loop, and a ban on reading `PORT`) when `spec` demands a stdlib `http.server`
  service (`harness.http_service_scaffold.spec_demands_stdlib_http_service`), and `""` for any
  non-http-service spec or malformed input. Never raises.
- [x] Wired into `_build_module`'s `BUILD_PROMPT` assembly (the same seam that already injects the
  REQ-41 interface ledger) so EVERY per-module build prompt for an http-service spec carries the
  routing contract — verified by exercising `_build_module` directly with a stub `llm` that records
  the prompt it received: the contract text is present for an http-service spec's module prompt and
  absent for a non-http-service spec's module prompt.
- [x] `harness/http_service_scaffold.py`'s `find_route_function(modules)` AST-scans `{filename:
  source}` module sources for a TOP-LEVEL `def route(...)` with EXACTLY 3 parameters and no
  `*args`, ignoring a wrong-arity `route` def and a `route` def NESTED inside a class or another
  function. Returns the first match's module stem, or `None` on no match / malformed input. Never
  raises.
- [x] `apply_http_service_scaffold` gives the routing contract TOP PRECEDENCE: when
  `find_route_function` recognizes a `route()`, a generated `BaseHTTPRequestHandler`/`HTTPServer`
  driver (`generate_route_skeleton`) — do_GET/do_POST/do_PUT/do_DELETE/do_PATCH parse the
  method/path/JSON body, call `route(method, path, body)`, write the returned status + JSON body
  (empty body forced for a 204 regardless of the returned body value, correct `Content-Length`
  always), reads `PORT` via `os.environ.get("PORT", "8000")` — is wired at the spec-demanded
  entrypoint filename, UNCONDITIONALLY REPLACING whatever entrypoint/serve-loop code the model
  emitted there, whether broken OR already a real serve loop (the `has_real_serve_loop`
  non-degrading guard is deliberately bypassed on this path). Precedence overall: route() contract
  > existing recognized dispatch shapes (`find_dispatch_handler`, REQ-48) > skeleton fallback /
  clean-prompt retry. Never mutates the input dict; never raises.
- [x] Non-degrading for every OLDER shape: when NO `route()` is recognized, behavior is BYTE-
  IDENTICAL to before this requirement — the pre-existing `has_real_serve_loop`/
  `find_dispatch_handler`/clean-prompt-retry precedence (REQ-48) is unchanged, a non-http-service
  spec is a no-op, and garbage/malformed input never raises.
- [x] Proven OFFLINE (no model/Jetson call): a hand-written CORRECT `route()` module, once scaffolded,
  actually RUNS and passes a real `serve_and_check_stdlib` round-trip (POST 201, GET 200, DELETE 204,
  GET-after-delete 404) end-to-end; the SAME scaffold REPLACES a broken model serve loop (the
  measured `TCPServer(("", port), handler_function)` shape passing a function where a handler class
  is required) when a `route()` exists elsewhere, and the repaired tree passes the same serve check;
  `find_route_function` correctly ignores wrong-arity and nested `route` defs; the prompt-injection
  seam is verified directly against `_build_module`. `tests/test_ext036_routing_contract.py`, plus no
  regression in `tests/test_ext036_http_service_scaffold.py` / `tests/test_ext036_port_coercion.py`.

### [REQ-52] Wire the deterministic repair chain into the MODIFY path (DONE — EXT-036 TASK-65, 2026-07-10)

MEASURED MOTIVATION: the build path runs a deterministic repair chain (`apply_signature_contract`
~system_builder.py:3317, `apply_port_coercion` ~3352, `apply_http_service_scaffold` ~3371,
`apply_agent_scaffold` ~3389, plus the REQ-51 routing-contract prompt guidance in `_build_module`)
over every module it BUILDS — and the SaaS CREATE class improved 0/3 -> 1/3 across these levers.
But `modify_system` (system_builder.py:4193+) ran NONE of them: when a modification regenerates a
module (e.g. rewrite `api.py`/`main.py` to add PUT), gemma re-introduces the same mechanical
protocol bugs (str-PORT, broken serve loop, dropped signature defaults) and nothing repaired them.
Measured: `rest-put-modify` stuck at 0/3 while CREATE improved. Every repair is idempotent +
non-degrading by construction, and `modify_system` already has a REGRESSION GATE (REQ-14) + a
new-behavior gate that reject any candidate that breaks existing behavior — so applying the repair
chain to the regenerated module set is safe end-to-end.

#### Acceptance Criteria
- [x] `harness/system_builder.py::_apply_deterministic_repairs(modules, spec_text, *, llm=None) ->
  dict` runs, in the SAME order the build path applies them: `apply_signature_contract` ->
  `apply_port_coercion` -> `apply_http_service_scaffold` -> `apply_agent_scaffold`, tolerating
  each repair's own return shape (`apply_port_coercion` returns a plain dict; the other three
  return a `(dict, notes)` tuple — unpacked exactly the way the build path already does). Never
  raises — any internal failure (import error, unexpected exception) returns `modules` completely
  UNCHANGED. Deliberately EXCLUDES `apply_filename_contract` from the chain — a rename is safe at
  CREATE time (nothing yet depends on the chosen filename) but NOT at MODIFY time, where a rename
  could break an EXISTING system's already-agreed-upon import/entrypoint expectations (a sibling
  module, the caller, or the regression-gate oracle itself may already reference the CURRENT
  filename).
- [x] `modify_system` calls `_apply_deterministic_repairs` on EVERY candidate module set it
  produces before that set is assembled for the regression gate: (a) the main regenerate/
  build-new-module seam (scoped to exactly `changed_names + added_names` — the modules the
  ASSEMBLE step actually (re)writes to disk, so every repaired byte stays reachable by the
  existing `pre_mod`/`added_names` revert path if the regression gate later rejects the
  modification); (b) the REQ-44 `_modify_newbehavior_repair` bounded repair loop, applied to each
  round's freshly-regenerated candidate module(s) before that round is written/checked, so a
  repair round can't reintroduce the same mechanical protocol bug the round it's replacing had.
- [x] `modify_system` gains an optional `spec_hint: str | None = None` parameter (default
  `None`, fully backward-compatible — no existing caller passes it). The http/agent scaffold
  repairs key on spec TEXT keywords (`spec_demands_stdlib_http_service`/
  `spec_demands_tool_calling_agent`) to decide whether they apply at all; a modification's OWN
  `mod_sentence` may name an HTTP method+path (e.g. "Add a `PUT /items/<id>` endpoint...")
  without repeating those indicator words — MEASURED: `spec_demands_stdlib_http_service` on the
  real `rest-sqlite-items-put-modify` suite task's `mod_sentence` alone returns `False` (no
  "REST"/"web service"/"http.server"/"PORT environment variable" indicator, only the endpoint
  pattern). When a caller has the original build spec/sentence in scope, it can pass it as
  `spec_hint` (combined with `mod_sentence`, `spec_hint` first) so the repair chain's
  spec-detection sees it too. HONEST SCOPE: `harness/real_systems_suite.py` (read-only for this
  task; not modified) does not carry an original build sentence for its hand-written
  `RealSystemModifyTask.start_system` fixtures, so its live call does not yet pass `spec_hint` —
  that wiring is an explicit follow-up, not claimed done here.
- [x] The build path (`build_system`, ~system_builder.py:3317-3390) is left UNTOUCHED — its
  repair-chain order interleaves `apply_filename_contract` between `apply_signature_contract` and
  `apply_port_coercion`, which is NOT identical to the modify-path chain (filename-contract
  deliberately excluded), so refactoring it to share `_apply_deterministic_repairs` would require
  either a behavior change or a second helper — out of scope; duplication is accepted, safety
  first.
- [x] Optional REQ-51 routing-contract PROMPT-level guidance (`_routing_contract_guidance`) is
  NOT injected into `modify_system`'s own regeneration prompts (`MODIFY_MODULE_PROMPT`/
  `NEW_MODULE_PROMPT`) — unlike `_build_module`'s single `BUILD_PROMPT` seam, there is no ONE
  clean prompt-assembly seam here (two prompt templates, three call sites: the main regenerate
  loop, `_build_new_module`, and the REQ-44 repair round's regenerate call), so wiring it in would
  require a broader refactor than this task's scope permits. Not required for correctness: the
  SCAFFOLD half (`apply_http_service_scaffold`'s `find_route_function` precedence) is a purely
  deterministic AST recognition + replacement, independent of any prompt-level guidance, and is
  proven to fire on a MODIFY-regenerated `route()` module without it.
- [x] Proven OFFLINE (no model/Jetson call): `tests/test_ext036_modify_repair_seam.py` — (a) a
  modify-regenerated module reintroducing the measured str-PORT bug is repaired (`int(port)` at
  the bind site) and genuinely RUNS a real `serve_and_check_stdlib` round-trip; (b) a
  modify-regenerated candidate carrying a top-level `route()` function alongside a broken model
  serve loop is scaffolded (REQ-51 precedence fires) via `spec_hint`, and genuinely RUNS a real
  POST/GET/DELETE round-trip; (c) a non-http modification is a byte-identical pass-through (the
  chain is a genuine no-op for plain code); (d) `_apply_deterministic_repairs` never raises on
  garbage (`None`, a non-dict, unparseable module code); (e) the REQ-14 regression gate still
  REJECTS a genuinely-regressing modification with the repair chain wired in (reverted, byte-
  identical to the pre-modification content). No regression in
  `tests/test_ext036_routing_contract.py` / `tests/test_ext036_port_coercion.py` /
  `tests/test_ext036_http_service_scaffold.py` / `tests/test_ext036_agent_scaffold.py` /
  `tests/test_ext036_system_builder.py` / `tests/test_ext036_modify.py` /
  `tests/test_ext036_modify_add.py` / `tests/test_ext036_system_repair.py` (191 passed).

### [REQ-53] Deterministic endpoint-shape contract repair (DONE — EXT-036 TASK-66, 2026-07-10)

MEASURED MOTIVATION (2 code-dumped draws, `scratchpad/restput_diag.out`): the canonical-board
`rest-sqlite-items-put-modify` MODIFY class measures 0/3 — gemma writes a PERFECT `do_PUT` body (a
real SQLite `UPDATE` + `rowcount` check + re-`SELECT` of the updated row + correct 200/404
statuses) but guards it with `parts = path.strip('/').split('/'); if len(parts) == 3 and
parts[0] == 'items' and parts[1].isdigit():` — `"/items/1"` always splits into exactly TWO
segments, so the guard never matches and every `PUT` silently falls through to a generic 404.
IDENTICAL across both draws (deterministic, not sampling variance). The existing length-guard
repair (`repair_guard_index_mismatch`, REQ-39) correctly does NOT fire — there is no
unreachable-INDEX contradiction (the body only ever indexes `parts[0]`/`parts[1]`, both valid at
`len(parts) == 3`); the bug is only provable against the VISIBLE spec's own endpoint template
(`"PUT /items/<id>"` implies exactly TWO path segments) — the same epistemics as the
signature-contract repair (REQ-45): a documented contract in the visible spec vs. the code's
actual shape, mechanical + leak-free.

#### Acceptance Criteria
- [x] `harness/endpoint_shape.py::endpoint_segment_counts(spec_text) -> set[int]` parses URL path
  TEMPLATES (`/`-starting tokens, e.g. `/items`, `/items/<id>`, `/items/{id}`, `/items/:id`,
  `/users/<user_id>/orders`) out of the visible spec text and returns the SET of segment counts
  those templates imply (counted the same way built code counts them:
  `path.strip('/').split('/')`). Returns an empty set for absent/garbage/no-match spec text.
  Never raises.
- [x] `harness/endpoint_shape.py::repair_endpoint_shape_guards(code, spec_text) -> str` AST-parses
  `code`; for each `if` whose test (bare, or the FIRST clause of an `and`-BoolOp) is
  `len(<name>) == N` where `<name>` was assigned from a `.split('/')` call traced within the SAME
  function (accepts `path.strip('/').split('/')` and similar chains — only the final `.split('/')`
  call is inspected, not the intermediate chain), rewrites the numeric literal `N` — via a
  surgical, literal-span-only edit (mirrors `system_builder._apply_line_col_edits`, reimplemented
  locally to avoid a build<->repair circular import) — to the SMALLEST count `C` in
  `endpoint_segment_counts(spec_text)` such that: (1) `N` is NOT itself already in that set, and
  (2) `C` is strictly greater than the largest constant index the guard's own true-branch body
  reads off `<name>` (so the rewrite can never make a previously-safe index access go
  out-of-range; a body with no constant index at all treats every count in the set as safe).
  CONSERVATIVE (Tenet 3 — a false repair is a real regression): fires ONLY on a leading `==`
  guard on a split-derived name with a non-empty parsed endpoint set satisfying (1)+(2); never
  touches a chained/other comparison beyond the leading `==` clause inside an `and`; never
  touches `!=`/`<`/`>`/etc. guards; never guesses when the literal's source span can't be
  located; returns `code` BYTE-IDENTICAL on any parse failure or when no repair applies. Never
  raises.
- [x] `harness/endpoint_shape.py::apply_endpoint_shape(modules, spec_text) -> dict[str, str]` maps
  `repair_endpoint_shape_guards` across a `{module_name: code}` dict. Returns a NEW dict (never
  mutates `modules`); a module whose repair fails to apply cleanly, or that has no matching
  defect, is left unchanged in the returned dict. Never raises.
- [x] Wired into BOTH deterministic-repair chains: the BUILD path (`build_system`,
  `harness/system_builder.py`, right after the REQ-45 signature-contract repair and before the
  REQ-46 filename-contract repair) AND the MODIFY path (`_apply_deterministic_repairs`, REQ-52,
  in the same relative position — right after `apply_signature_contract` and before
  `apply_port_coercion`). Both wire points wrapped in `# #EXT-036-REQ-53 Start`/`End` markers.
- [x] Leak-free (Tenet 3): the corrected segment count comes ONLY from URL path templates parsed
  out of the visible build spec text handed to `endpoint_segment_counts` — never a hidden
  oracle/test/reference implementation.
- [x] Proven OFFLINE (no model/Jetson call, `tests/test_ext036_endpoint_shape.py`): (a)
  `endpoint_segment_counts` parses `/items`/`/items/<id>`/`/items/{id}`/`/items/:id`/
  multi-segment templates correctly, empty/garbage spec text -> empty set; (b) THE MEASURED
  SHAPE — the exact broken `do_PUT` reproduction is rewritten from `len(parts) == 3` to
  `len(parts) == 2`, with ONLY that one literal changed (byte-identical elsewhere) and the
  repaired module still compiling; (c) END-TO-END — the repaired module genuinely SERVES a real
  `POST`/`PUT` round-trip via `harness.server_oracle.serve_and_check_stdlib` (PUT /items/1 -> 200
  with the updated name), while the UNREPAIRED control genuinely FAILS the identical check (not a
  fabricated pass); (d) non-firing safety — an already-consistent guard, a spec with no
  parseable endpoints, a non-split-derived name, and `!=`/`<` guards are all left byte-identical;
  garbage input never raises; a multi-module dict only changes the offending module; (e) wired
  correctly via `_apply_deterministic_repairs` — a modules dict with the broken shape + an http
  `spec_text` comes out repaired, proving the MODIFY-path wire. No regression in
  `tests/test_ext036_modify_repair_seam.py` / `tests/test_ext036_port_coercion.py` /
  `tests/test_ext036_routing_contract.py` / `tests/test_ext036_http_service_scaffold.py` /
  `tests/test_ext036_signature_contract.py` / `tests/test_ext036_system_builder.py` (148 passed).

### [REQ-54] Conservative gating for the AGENT tool-call-parse scaffold (DONE — EXT-036 TASK-67, 2026-07-10)

MEASURED MOTIVATION: the canonical board class `schema-validation-retry-loop` (EXT-060 REQ-30)
measures 0/3 with the signature "tool_call count mismatch: expected 2, got 20". The task's
contract requires the built agent to LOCALLY VALIDATE each structured payload and DECIDE ITSELF to
stop after a successful validation (a task-specific stop judgement). REQ-49's generic
`apply_agent_scaffold` skeleton finalizes ONLY on a model final/content turn and otherwise
dispatches every `tool_calls` turn — with this task's 2-turn stub script it dispatches to
max-steps (=20) instead of stopping after the second, valid submission. Because the spec's
`OPENAI_BASE_URL`/`tool_calls`/chat-completions keywords DO trigger
`spec_demands_tool_calling_agent`, the scaffold was firing and REPLACING (or filling in on an
empty build) the entrypoint with the fixed skeleton — making this class STRUCTURALLY unable to
pass, breaking REQ-49's "non-degrading" claim for validation/retry-style orchestration the generic
skeleton cannot express.

#### Acceptance Criteria
- [x] `harness/agent_scaffold.py::spec_demands_custom_stop_logic(spec_text) -> bool` — True when
  the visible spec demands orchestration judgement beyond plain dispatch-until-final: matches
  validate/validation, schema, retry, a max-attempts/retries/requests cap, or an explicit
  stop-decision phrase ("decide when to stop", "stop after", "finalize when", "until ... valid").
  Precise (Tenet 3 — never a blanket "tool" or bare "stop" match, so a plain step-count guard
  phrased only as "stop after 3 tool calls" is NOT flagged). Never raises — non-string/empty input
  is simply not a demand.
- [x] `apply_agent_scaffold` gated: when `spec_demands_tool_calling_agent(spec)` AND
  `spec_demands_custom_stop_logic(spec)` → returns `modules` unchanged plus an explanatory note
  ("agent-scaffold skipped: spec demands custom stop/validation orchestration the generic skeleton
  cannot express"), checked BEFORE the empty-modules/broken-loop paths so the empty-build fallback
  also respects the gate — better to leave repair/retry paths a chance to work on gemma's own
  attempt than ship a skeleton structurally unable to pass.
- [x] Regression-guard verified against the ACTUAL real-system sentences (not just synthetic
  phrasings): `PLAIN_AGENT_TASK.sentence` (the plain tool-calling-agent CREATE class) and
  `AGENT_ADD_STEP_GUARD_MODIFY.mod_sentence` (combined with its `base_sentence`, the agent MODIFY
  class) do NOT trigger `spec_demands_custom_stop_logic` — both classes still scaffold exactly as
  before; `VALIDATION_RETRY_TASK.sentence` (the schema-validation-retry-loop class) DOES trigger
  it, gating the scaffold to a no-op on that class.
- [x] Proven OFFLINE (no model/Jetson call, `tests/test_ext036_agent_scaffold_gating.py`): (a)
  `spec_demands_custom_stop_logic` is True for the real validation-retry sentence + representative
  validation/retry phrasings, False for the real plain-agent + agent-modify sentences and generic
  tool-calling phrasings, never raises on garbage; (b) `apply_agent_scaffold` no-ops
  (byte-identical modules + the skip note) on the real validation-retry spec whether the loop is
  broken, absent, or the modules dict is empty, and on generic validation phrasings combined with
  agent-demanding boilerplate; (c) the plain-agent and agent-modify real sentences still trigger
  the scaffold exactly as before (a broken loop is still replaced with the skeleton). All 19
  pre-existing `tests/test_ext036_agent_scaffold.py` tests stay green (no regression to REQ-49),
  and `tests/test_ext060_clock_agent_tasks.py` stays green (its offline fixtures don't go through
  `build_system`, so unaffected by this gate).

### [REQ-58] `_extract_json` LAST-RESORT truncation-salvage stage (DONE — EXT-036 TASK-71, 2026-07-10)

MEASURED MOTIVATION (live-reproduced): the board class `backup-retention-gfs-pruning-lib` fails
2/3 with note "planner produced no parseable JSON plan". The planner emits a WELL-FORMED ```json
plan whose `"acceptance"` value is a giant multi-line Python string, and the completion hard-
truncates at `PLAN_MAX_TOKENS=900` MID-STRING — the raw completion ends `...test_gfs_retention`
with no closing quote, no closing brace, and no closing fence. Every existing `_extract_json`
stage (REQ-33's greedy match/balanced span/repair, and the TASK-48 structural-bracket recovery)
fails on this shape: the greedy/balanced stages both need a closer that was never emitted (and
the greedy match, when it finds SOME `}` earlier in the text, cuts the candidate off there —
before the `"entrypoint"`/`"acceptance"` fields even begin); `_recover_missing_braces`
deliberately leaves an end-of-input-open stack untouched (its own explicit non-goal, a
DIFFERENT defect class than the one it fixes).

#### Acceptance Criteria
- [x] `harness/system_builder.py::_salvage_truncated_json(text, opener, closer)` — a new,
  LAST-RESORT stage reached only when every earlier `_extract_json` stage has already failed.
  Unlike every earlier stage (which extracts a span ending at the LAST closer PRESENT in the
  text, so it never includes content emitted after a mid-string truncation point), this walks
  `text` from its FIRST `opener` to the END of the string, tracking JSON string-literal state
  (quote + backslash-escape awareness) and a bracket stack (the same string-aware scan
  `_recover_missing_braces` uses). If the walk ends INSIDE a string literal, closes it (appends
  `"`); then appends the closer for every still-open bracket, innermost first.
- [x] Returns the salvaged text ONLY when `json.loads` on it (optionally after
  `_repair_json_candidate`, for a stray control character or trailing comma left in the
  surviving text) actually succeeds — never fabricates content beyond the closers/quote needed
  to make the JSON syntactically well-formed, and never returns a partial/garbage payload. A
  no-op (returns None) when `text` was not actually truncated (the walk ends outside any string
  with an empty bracket stack — a shape an earlier stage would already have handled) or when no
  salvage attempt parses. Never raises.
- [x] Wired into `_extract_json` as the true final stage, after the TASK-48 structural-bracket
  recovery and before the function's final `return None` — additive, deterministic, leak-free
  (operates purely on the model's own emitted text; no oracle/expected content involved).
- [x] HONEST SCOPE: the salvage necessarily loses the TAIL of the truncated string value —
  typically a throwaway acceptance-hint string in a build plan. Downstream `validate_plan` still
  gates plan sanity on the surviving `modules`/`entrypoint` fields, and acceptance-checklist
  derivation has its own deterministic floor, so a truncated acceptance hint is safe to lose.
- [x] Proven OFFLINE (no model/Jetson call, `tests/test_ext036_truncation_salvage.py`): (a) the
  EXACT measured `backup-retention-gfs-pruning-lib` completion (embedded verbatim) now salvages
  — parses cleanly, keeps the complete `modules`/`entrypoint` fields, and `validate_plan` reports
  zero defects; (b) truncation mid-key or at a structural (non-string) position never crashes and
  never yields invalid JSON; (c) the stage is proven LAST-RESORT — every pre-existing
  valid/repairable shape (already-valid JSON, a trailing-comma defect, a TASK-48 missing-brace
  shape) still resolves via its own earlier stage, with `_salvage_truncated_json` itself a
  confirmed no-op on those inputs; (d) garbage/empty input returns None, never raises; (e) a
  truncated fragment whose salvage attempt does not `json.loads` returns None, never a
  partial/garbage payload. `tests/test_ext036_plan_brace_recovery.py`'s pre-existing
  end-of-input-truncation test is updated (not removed) to assert the new, superseding
  behavior — `_recover_missing_braces` itself is unchanged (still leaves that shape untouched),
  but `_extract_json` as a whole no longer returns `None` on it. All pre-existing
  `_extract_json`/`_recover_missing_braces`/plan-repair tests stay green (`python -m pytest
  tests/ -k "extract_json or planrepair" -q`).

### [REQ-65] HTTP-service scaffold calls the model's own DB/state-init before `serve_forever()` (DONE — EXT-036 TASK-80, 2026-07-10)

MEASURED MOTIVATION (`scratchpad/batch3_diag_urlshort_d1.out`): `url-shortener-http-service`
fails with "Remote end closed connection without response" -- gemma's own `route()`/logic module
defines a correct zero-arg `initialize_db()` (creates the SQLite table) and calls it from ITS OWN
(bypassed) `start_server()`, but the deterministic route-skeleton generated by
`harness/http_service_scaffold.py` never calls it -- only `HTTPServer(...).serve_forever()` runs,
so the first real request hits `sqlite3.OperationalError: no such table` and the handler dies
mid-request (a connection reset, not a clean HTTP error). The scaffold must carry forward the
app's own initialization, not just its routing.

#### Acceptance Criteria
- [x] `harness/http_service_scaffold.py::find_init_functions(modules) -> list[dict]` — a best-
  effort, NEVER-RAISE AST scan of `{filename: source}` module sources for TOP-LEVEL, zero-arg
  DB/state-init exports: a top-level `def` whose name matches `initialize_db`/`init_db`/
  `initialise_db`/`create_table(s)`/`setup_db`/`init_storage`/`setup_database` (case-
  insensitive) AND is callable with zero required arguments (default-only positional/keyword
  args and no required keyword-only arg both count as zero-arg). A same-named method NESTED
  inside a class, or a nested/inner function, is ignored — only a genuine top-level, module-
  scope function counts. Returns candidates in module order, then top-to-bottom source order
  within a module, as `{"module": <stem>, "callable": <name>}` dicts — empty list on no match or
  any malformed input.
- [x] `generate_skeleton` and `generate_route_skeleton` gain optional `init_candidates`/
  `entry_stem` kwargs: when `init_candidates` is non-empty, each candidate is imported (unless
  already in scope in `entry_stem`, the generated module's own filename stem) and CALLED ONCE,
  in the given module order, right BEFORE `HTTPServer(...).serve_forever()`. The call is
  deliberately NOT wrapped in try/except — an init failure PROPAGATES, so a service whose DB/
  state init genuinely fails to start fails HONESTLY at startup rather than silently serving a
  broken handler. Omitted/empty `init_candidates` → the generated skeleton is byte-identical to
  the skeleton emitted before this requirement existed, on both the dispatch (`generate_skeleton`)
  and routing-contract (`generate_route_skeleton`) paths.
- [x] `apply_http_service_scaffold` computes `entry_stem` from the resolved entry filename, calls
  `find_init_functions(mods)` once per apply, and threads `init_candidates=`/`entry_stem=` into
  both the route-skeleton and dispatch-skeleton generation call sites.
- [x] Proven OFFLINE + END-TO-END (`tests/test_ext036_http_init_scaffold.py`, 15 tests, no model/
  Jetson call): (a) the MEASURED shape — a `route()` module owning a correct zero-arg
  `initialize_db()` — produces a generated `main.py` that imports + calls it before
  `serve_forever()`, and a REAL stdlib server (`harness.server_oracle.serve_and_check_stdlib`)
  GENUINELY passes a POST-then-GET round trip requiring the table, while the UNREPAIRED control
  (no init call wired) GENUINELY fails the same way — proving the fix is real, not fabricated;
  (b) no init function found → byte-identical generated main on both scaffold paths; (c) a
  required-arg init function is detected but never called, and the AST scan never raises on
  malformed/garbage input; (d) multiple init candidates across modules are called in module
  order, proven end-to-end; (e) `find_init_functions` ignores a same-named nested/class method
  and matches case-insensitively. No regression: `tests/test_ext036_routing_contract.py` (REQ-51)
  and `tests/test_ext036_http_service_scaffold.py` (REQ-48) stay green alongside the new file
  (60 passed together).
