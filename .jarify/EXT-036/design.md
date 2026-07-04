# Design — EXT-036: Sentence-to-System

## Overview

EXT-036 is the **PLANNER + orchestration + agentic-substrate + parity-instrument** layer that
turns a natural-language prompt into a complete, working Python system (creation) or evolves an
existing one (modification). It sits on top of the Foundry EXECUTOR (EXT-035/EXT-008:
`build_from_intent` → deterministic import wiring → assemble → ship-gate). The capability
decomposes into layers **A** spec-expansion, **B** architecture, **C** interface design, **D**
ordered implementation, **E** per-module test/validate, **F** integration/assemble/run, **G**
cross-level repair, **H** scale — the executor covers D/E/F + per-level G; this spec adds A/B/C,
end-to-end orchestration, and H, plus the Claude-Code agentic substrate (session, memory, tasks,
experiments, JAROS.md, ask-user) and the held-out parity suites.

A measured surprise reshapes the gap: the small model produces STRUCTURALLY coherent plans from a
sentence (valid module DAG, per-module signatures, entrypoint, acceptance line) — so "a 2-3B can't
architect" is false at the structural level. The real gaps are downstream (semantic coherence,
executable done-ness, scale, drift), which is where the deterministic plane and escalation do the
work.

## The build pipeline (two-plane)

```text
   sentence / paragraph / conversational prompt
                    │
     [REQ-8] ask-the-user if genuinely ambiguous ──► fold answer into request
                    │
                    ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │ PLANNER  [REQ-1]  (model judges; deterministic plane guarantees shape) │
   │   model → JSON plan {modules, responsibilities, exports+signatures,    │
   │            imports, entrypoint, acceptance}                            │
   │   validate_plan(): parseable · exports well-formed · imports ref real  │
   │            modules (stdlib exempt) · DAG acyclic · entrypoint listed   │
   │   deterministic plan-repair for the measured single-module/entrypoint  │
   │            mismatch; incoherent multi-module plans still rejected       │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │ ORDERED BUILD  [REQ-3/4]  build each module leaves-first (deps as      │
   │   context) → per-module py_compile syntax gate + bounded syntax-repair  │
   │   → EXT-035 resolve_imports wires cross-module imports deterministically│
   │   → ASSEMBLE onto root                                                  │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │ SECURITY SCAN GATE (EXT-037 REQ-7) — refuse a dangerous build          │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │ EXECUTABLE ACCEPTANCE  [REQ-2/7]  derive a runnable checklist from the  │
   │   SPEC + module API, filtered to real parse+assert checks:             │
   │     tier 1: model checks (parse + assert)                              │
   │     tier 2: one stricter retry (runnable Python only)                  │
   │     tier 3: subprocess checks (drive the real entrypoint)  ── stateful │
   │     tier 4: deterministic SMOKE checklist (import + hasattr)   CLIs     │
   │   web service detected? → server_oracle: START uvicorn/flask on an      │
   │     ephemeral port, hit real HTTP endpoints  [REQ-22]                   │
   │   sqlite persistence? → datastore oracle: independently query the .db,  │
   │     verify cross-invocation persistence  (EXT-039)                     │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │ CROSS-LEVEL REPAIR  [REQ-5]  unmet check + error + module sources →     │
   │   targeted module-body fix, syntax-gated, re-run FULL checklist,        │
   │   NON-DEGRADING (revert a round that regresses a previously-passing     │
   │   check), bounded max_repair rounds                                     │
   └───────────────────────────────┬───────────────────────────────────────┘
                                    ▼
        ShipResult { modules, shipped, done, unmet, security, quality, note }
```

## Reliability + long-horizon variants (all wrap build_system, never modify it)

```text
  build_system_escalating [REQ-13]     run default model; escalate to a measured stronger
                                       Jetson-fit fallback (e.g. Qwen2.5-Coder-7B) ONLY when
                                       the default failed to ship; restore primary after.

  build_system_best_of_k  [REQ-25]     build up to k attempts in isolated temp dirs; score each
                                       by an INDEPENDENT acceptance checklist; keep the best;
                                       early-exit on all-pass; assemble winner onto root.

  build_system_governed   [REQ-23]     decompose prompt → independent per-requirement black-box
                                       CLI checks (spec of record) → build → verify EVERY
                                       requirement independently → re-ground+repair unmet →
                                       NO-REGRESS FLOOR: guaranteed max(baseline, governed),
                                       never worse than a plain build_system call.

  modify_system           [REQ-14]     identify target module(s) → regenerate WITH the change →
                                       regression-gate: baseline-passing checks + import
                                       smoke-gate must still pass, else REVERT to pre-mod source.
```

## Agentic substrate (the Claude-Code-like surroundings, per repo)

```text
  harness/session.py       conversational multi-turn session + resume; condense() folds old
                           turns into a running summary when over budget            [REQ-12/15]
  harness/repo_memory.py   per-repo durable FACTS (<root>/.jaros/memory.jsonl);
                           select_relevant = narrow memory-agent precise recall       [REQ-16]
  harness/episodic_memory  chronological action+rationale log; deterministic lexical/
                           tag recall_similar for plan-from-experience                [REQ-24]
  harness/project_md.py    JAROS.md (≈ CLAUDE.md) injected every prompt, bounded       [REQ-17]
  harness/task_store.py    per-repo TODO tasks + propose_tasks decomposition           [REQ-18]
  harness/experiment_store real experiments: define → run (guarded subprocess) → record [REQ-19]
  harness/ask_user.py      conservative ambiguity judgment → one clarifying question   [REQ-8]
```

## Parity instruments (held-out, independent oracles — the scoreboard)

```text
  system_suite.py        CREATION suite: sentence + INDEPENDENT black-box CLI checks;
                         run_creation_suite → ship/done/accept rate per class × tier   [REQ-20]
  modification_suite.py  MODIFICATION suite: known-good start system + one-sentence
                         change + new-behavior AND regression checks                    [REQ-21]
  coherence_suite.py     LONG-HORIZON: prompt with N requirements → per-requirement
                         coverage (drift signal, not all-or-nothing); FIRST_SLICE +
                         HARD_SLICE (11-req interdependent CLIs); median-of-k repeats    [REQ-23]
```

## Design principles

- **Two-plane throughout (Tenet 1).** The model judges decomposition, module bodies, targeted
  fixes; the deterministic plane guarantees structural coherence, wires imports, runs every
  acceptance check, gates security, and decides ship/done — the model never self-certifies.
- **Independent, executable acceptance (Tenet 3).** Done-ness is a real run of real checks, never
  prose or self-report. Web services are HTTP-verified, persistence is independently queried, and
  the parity suites' oracles are independent of the system under test — a no-op scores zero.
- **Never regress, never fabricate.** The escalating/best-of-k/governed floors and the
  modification regression-gate all guarantee the returned system is never worse than the honest
  baseline, and an unmet requirement is listed honestly rather than papered into a false `done`.
- **Spec-first anti-drift (Tenet 4).** The governed path decomposes into a requirement list of
  record and continuously re-grounds against it — the mechanism for staying aligned across a
  long-horizon build.
- **Escalation in cost order (Tenet 2).** The default local model runs first; a stronger
  Jetson-fitting model is paid for only on failure; no cloud/paid model, ever.
