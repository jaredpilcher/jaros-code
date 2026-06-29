---
id: EXT-021
title: Multi-Model Routing Harness
status: partial
priority: high
implementation:
  - file: harness/model_registry.py
    ranges: []
  - file: harness/model_router.py
    ranges: []
  - file: harness/model_rewire.py
    ranges: []
---

### [REQ-1] Model registry with per-model profiles

A deterministic registry of the Jetson-fitting models, each described by an explicit **profile**:
a stable model id/alias, its llama.cpp serving parameters (gguf path/alias, ctx, fits-Jetson flag),
the problem **classes** it is *measured* to handle (with the held-out evidence that earned each),
and the harness **adaptation** for that model — the set of tools, agents, config, and prompt
variants to activate when this model is selected. The registry is data (JSON/py), loadable and
queryable; Gemma 4 2B (`e2b`) is the founding entry and the baseline anchor.

#### Acceptance Criteria
- [x] Define a `ModelProfile` (id, alias, serve params, fits_jetson, classes-handled with evidence, adaptation = {tools, agents, config, prompts}).
- [x] A registry that loads all profiles from `.jaros-data/config/models/` (one file per model) and exposes lookup by id and by class.
- [x] Gemma 4 2B (`e2b`) registered as the founding profile with its current adaptation + measured classes.
- [x] A registry never invents a class for a model that has no recorded held-out evidence (honest profiling, Tenet 3).

### [REQ-2] Deterministic model-router (class → model; NO model-as-judge)

A **deterministic** router that classifies a problem's **class** from deterministic features
(standalone-vs-repo, has-docstring-examples, multi-file, function size, language — *not* a model's
judgement) and selects the model via the deterministic coverage tally (REQ-5), emitting an inert
`Decision` (Tenet 1). **A model is never used to route or to pick between models** — model-as-judge
was *measured* net-negative (#20/#21: the 2B orchestrator was ~parity with a 80%-accurate blind spot),
and letting a model choose models would re-introduce the very randomness multi-model exists to tame
(external review, 2026-06-28). It ALWAYS yields a choice (a deterministic default when no tally entry
covers the class) and is hash-chain logged + replayable. (The earlier implementation's optional
LLM class-label path is dropped — classification stays deterministic.)

#### Acceptance Criteria
- [x] `route(problem) -> Decision{model_id, problem_class, confidence, rationale}` — inert data, no side effects.
- [x] Selection consults the registry's class→model coverage; ties/uncertainty fall back to the deterministic default model.
- [x] The router is offline-testable with a stub registry (deterministic — no LLM needed).
- [x] A misroute is treated as a harness gap to close (better profile/features), never a model limit — recorded for the convergence loop.
- [ ] The router uses ONLY deterministic features to classify the class — no model is asked to route or to choose between models (model-as-judge forbidden here; the earlier optional-LLM path is removed/disabled).

### [REQ-3] Deterministic rewire to the selected model

Given a router Decision naming a model, deterministically **rewire** the harness to it: ensure that
model is the one served on the Jetson (issue the llama.cpp model-swap only when the currently-served
model differs), point the LLM client at it, and activate that model's adaptation (its tools/agents/
config/prompts) for the ensuing solve. The rewire is an execution-plane operation (the clerk) with
`validate()`/`execute()` semantics; it is idempotent (no swap when already serving the target) and
records what it did.

#### Acceptance Criteria
- [x] `rewire(model_id)` resolves the profile, and if the served model differs, performs the documented Jetson swap (edit serve params + restart `gemma.service`) — otherwise a no-op.
- [x] After rewire, the active LLM client + the active tool/agent/config/prompt set match the chosen model's profile.
- [x] Idempotent and safe: re-rewiring to the already-served model performs no swap; a failed swap is reported honestly, never silently.
- [x] The swap path is gated/guarded so it cannot run an unsafe command (Tenet 1) and never escalates off-device (Tenet 2).

### [REQ-4] Per-model profiling / roster exploration loop

A measurement loop that grows the roster **best-first** and earns each model's class profile
honestly: for a candidate Jetson-fitting model, serve it, run the held-out class evals, and record
which classes it handles (updating its profile) — so routing decisions rest on measured coverage,
not assumption. This is how the system "explores and learns each model" and how the router's
profiles stay truthful.

#### Acceptance Criteria
- [x] A documented procedure + script to profile a model: serve it, run the per-class held-out evals, write the measured classes into its profile with the evidence (scores, dates, bar). (`harness/model_profiler.py` — `profile_model` + `fits_jetson` + `roster_order`; 32 offline tests in `tests/test_model_profiler.py`.)
- [x] The roster is ordered best-first (strongest Jetson-fitting model first) and only Jetson-fitting models are admitted (fits the ~8 GB budget). (`_roster.json` `order` field; `fits_jetson()` admission check; APPENDIX in design.md.)
- [x] Profiling is honest (held-out, visible-spec, no hidden-test leakage) and a class is added to a profile ONLY with recorded evidence. (Honesty gate in `profile_model`: `passed=True` is the sole condition; below-bar classes go to `rejected`, never to the profile JSON — tested in `TestBelowTheBar`.)
- [x] The end-to-end path (route → rewire → solve with the chosen model's adaptation) is demonstrated on at least two classes routed to two different models. (`harness/solve_routed.py` `solve_routed`; `tests/test_solve_routed.py` — 12 offline tests; stub 2-profile registry proves model-alpha/standalone-fn-gen and model-beta/multi-step-repo end-to-end. TASK-5.)

### [REQ-5] Deterministic best-model-per-class tally + roster progression + new-class re-profiling

(Owner refinement, 2026-06-28.) Model selection splits two-plane: a model **JUDGEMENT** classifies the
problem's CLASS (an agent decision), and a **DETERMINISTIC tally** selects the best model for that
class. The tally is a persistent coverage **matrix** (model × class → measured score + evidence), kept
filled in by the profiler; `best_model_for(class)` is the deterministic argmax over that class's column.
The roster is explored **progressively**: a model is profiled across **all known classes** before the
system moves on; once its coverage is captured, the **next most capable Jetson-fitting model** is
admitted and profiled the same way — and so on, indefinitely. When a **new class** is discovered (the
new-class recording feature), it is a new column: **every existing roster model is re-profiled against
it** (go back to prior models) so the tally stays complete. A model's per-model adaptation includes its
own **evals** (alongside tools/agents/config/prompts). The router never credits a model for a class
without a tally entry (honest; otherwise default-fallback + record as a new/unhandled class).

#### Acceptance Criteria
- [x] A persisted, queryable coverage tally (model × class → {score, bar, date, evidence}); `best_model_for(class) -> model_id` is the deterministic argmax (ties broken by roster order / default). (`harness/model_tally.py` — `CoverageTally`, `_parse_score`; 38 offline tests in `tests/test_model_tally.py`.)
- [x] The router uses model JUDGEMENT to classify the CLASS, then the deterministic tally to SELECT the best model for it (judgement = class; deterministic = selection). (`harness/model_router.route` step 5 now calls `CoverageTally.best_model_for` — tally injectable for tests; REQ-5 anchors in `model_router.py` lines 275–304.)
- [ ] Roster progression: a model is profiled across ALL known classes; a documented "coverage captured" criterion gates admitting + profiling the next-most-capable Jetson-fitting model.
- [ ] New-class trigger: recording a new class re-profiles ALL existing roster models against it, filling that column of the tally.
- [ ] A `ModelProfile`'s adaptation set includes the EVALS used to measure its classes (not only tools/agents/config/prompts).

### [REQ-6] Test-gated roster escalation (the deterministic test is the judge, never a model)

(External review + owner, 2026-06-28.) When a class has more than one candidate model in the tally,
the winner is resolved by the **deterministic test gate, not by a model**: try the best-tally model,
run its solve, let the **given/visible test** (the task's own failing test, or the docstring examples)
decide pass/fail; on fail, **escalate to the next candidate model** for that class and retry. The
oracle/test — never a model — picks the winner, so the decorrelated errors of diverse small models are
harvested (diversity beats best-of-N resampling, which we measured as noise) WITHOUT re-introducing
model-as-judge. ALL candidate models are **local + Jetson-fitting + free** (Tenet 2): escalation goes
to the next-best LOCAL model, NEVER to a cloud or paid model — version "A" (many diverse small local
models, test-gated), never version "B" (cloud escalation). Escalation order is the deterministic tally
(best-measured-first), bounded by a max-models budget.

#### Acceptance Criteria
- [ ] On a multi-candidate class, `solve_routed` tries models best-tally-first and keeps the FIRST whose output passes the given/visible test (the deterministic gate), escalating on fail.
- [ ] The winner is chosen ONLY by the deterministic test/oracle — no model ranks or picks between model outputs (model-as-judge forbidden).
- [ ] Escalation is bounded (a max-models budget) and stays entirely on LOCAL Jetson-fitting models — cloud/paid is never a tier (Tenet 2).
- [ ] Honest: the visible test/spec gates selection at solve time; the hidden held-out oracle is used only to SCORE the eval, never to pick the model.

### [REQ-7] Class definition, classification & evolution (data-driven, test-gate-labeled)

(Owner design question, 2026-06-28.) A "class" is **not a guessed taxonomy** — it is a cluster of
problems with *correlated model success*, **discovered from the test-gate's honest labels**, kept only
while it stays *predictive* of which model wins. Classifying a given (files+code+task) is a **cheap
deterministic PRIOR**: the *failure signal* (parse the failing test/traceback — error type:
attribute/boundary/type/logic; the asserting line; the touched symbol) plus structural features
(language, standalone-vs-repo, #files, function size, has-examples). This prior need NOT be perfect —
the test gate (REQ-6) is the real judge, so a mis-class merely costs one extra escalation attempt
(self-correcting), and **every test-gated solve records a `(problem-signature, model, pass/fail)` label
for free**. Those labels EVOLVE the ontology: **DISCOVER** (a problem matching no class / no coverage →
`new_classes.jsonl`; when similar ones accumulate, name a class + re-profile the roster, REQ-5); **SPLIT**
(a class whose best-model wins on some members but loses on others — high within-class outcome variance —
is too coarse → split into sub-classes along the separating feature → re-profile); **VALIDATE** (retain a
class only while its named best-model wins above a bar; non-predictive classes are re-examined).
**Sub-problems:** decomposition splits a task into sub-tasks, each independently classified + routed +
test-gated (recursive). Embedding/cluster-based discovery is an *option* but kill-tested first
(retrieval/embeddings were a prior negative on the 2B — [[jaros-code-retrieval-fewshot-negative]]).

#### Acceptance Criteria
- [ ] Classification is a deterministic prior from the failure signal + structural features; the test gate is the final judge, so a mis-class is self-correcting (just escalates).
- [ ] Every test-gated solve records a `(problem-signature, model, outcome)` label to a persistent store (the labels that drive class evolution).
- [ ] DISCOVER: uncovered/unmatched problems accumulate → a named class + roster re-profile when a threshold cluster forms.
- [ ] SPLIT: a class with inconsistent best-model outcomes (variance > threshold) is flagged + split into sub-classes, then re-profiled.
- [ ] VALIDATE: a class is retained only while predictive (named best-model win-rate above a bar); decomposition-produced sub-tasks are classified + routed independently.
