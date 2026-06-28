---
id: EXT-021
title: Multi-Model Routing Harness
status: uncovered
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
- [ ] Define a `ModelProfile` (id, alias, serve params, fits_jetson, classes-handled with evidence, adaptation = {tools, agents, config, prompts}).
- [ ] A registry that loads all profiles from `.jaros-data/config/models/` (one file per model) and exposes lookup by id and by class.
- [ ] Gemma 4 2B (`e2b`) registered as the founding profile with its current adaptation + measured classes.
- [ ] A registry never invents a class for a model that has no recorded held-out evidence (honest profiling, Tenet 3).

### [REQ-2] Model-router judge (class → model Decision)

A judge that, given a problem, classifies its **class and difficulty** and selects the registry
model whose profile best covers that class, emitting an inert `Decision` (Tenet 1). It runs
on-device (a small classification, optionally backed by deterministic features) and ALWAYS yields a
choice: a **deterministic default** routes to a known-capable model when the judge is unsure, so the
system never fails to route. The routing decision is hash-chain logged and replayable.

#### Acceptance Criteria
- [ ] `route(problem) -> Decision{model_id, problem_class, confidence, rationale}` — inert data, no side effects.
- [ ] Selection consults the registry's class→model coverage; ties/uncertainty fall back to the deterministic default model.
- [ ] The router is offline-testable with a fake LLM (classification stubbed) and a stub registry.
- [ ] A misroute is treated as a harness gap to close (better profile/features), never a model limit — recorded for the convergence loop.

### [REQ-3] Deterministic rewire to the selected model

Given a router Decision naming a model, deterministically **rewire** the harness to it: ensure that
model is the one served on the Jetson (issue the llama.cpp model-swap only when the currently-served
model differs), point the LLM client at it, and activate that model's adaptation (its tools/agents/
config/prompts) for the ensuing solve. The rewire is an execution-plane operation (the clerk) with
`validate()`/`execute()` semantics; it is idempotent (no swap when already serving the target) and
records what it did.

#### Acceptance Criteria
- [ ] `rewire(model_id)` resolves the profile, and if the served model differs, performs the documented Jetson swap (edit serve params + restart `gemma.service`) — otherwise a no-op.
- [ ] After rewire, the active LLM client + the active tool/agent/config/prompt set match the chosen model's profile.
- [ ] Idempotent and safe: re-rewiring to the already-served model performs no swap; a failed swap is reported honestly, never silently.
- [ ] The swap path is gated/guarded so it cannot run an unsafe command (Tenet 1) and never escalates off-device (Tenet 2).

### [REQ-4] Per-model profiling / roster exploration loop

A measurement loop that grows the roster **best-first** and earns each model's class profile
honestly: for a candidate Jetson-fitting model, serve it, run the held-out class evals, and record
which classes it handles (updating its profile) — so routing decisions rest on measured coverage,
not assumption. This is how the system "explores and learns each model" and how the router's
profiles stay truthful.

#### Acceptance Criteria
- [ ] A documented procedure + script to profile a model: serve it, run the per-class held-out evals, write the measured classes into its profile with the evidence (scores, dates, bar).
- [ ] The roster is ordered best-first (strongest Jetson-fitting model first) and only Jetson-fitting models are admitted (fits the ~8 GB budget).
- [ ] Profiling is honest (held-out, visible-spec, no hidden-test leakage) and a class is added to a profile ONLY with recorded evidence.
- [ ] The end-to-end path (route → rewire → solve with the chosen model's adaptation) is demonstrated on at least two classes routed to two different models.
