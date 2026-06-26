# EXT-012 Design — Behavioral solve + orchestration

The behavioral solve turns a commit's *intent* into code via a small fleet of single-purpose grains,
each backed by a deterministic tool, with the held-out test kept HIDDEN (intent-only — no leakage).

## Solve flow

```text
        commit intent (subject)               held-out test stays HIDDEN
               │
               ▼
   ┌───────────────────────┐   multi-function localize (cap >4)
   │ localize target(s)    │──────────────────────────────────────┐
   └───────────┬───────────┘                                       │
               ▼  per function                                     │
   ┌───────────────────────┐  Given/When/Then behavior spec        │
   │ gherkin grain         │  (proven prompt)                      │
   └───────────┬───────────┘                                       │
               ▼                                                    │
   ┌───────────────────────┐  pytest self-tests FROM the spec      │
   │ self-tests grain      │  (the model's own oracle)             │
   └───────────┬───────────┘                                       │
               ▼                                                    │
   ┌───────────────────────┐  implementation, piped through        │
   │ code grain            │  parse-gated syntax-repair            │
   └───────────┬───────────┘                                       │
               ▼                                                    │
   ┌───────────────────────┐  run self-tests; on fail, revise      │
   │ fix loop (max_fix=2)   │◀── deterministic fix-loop  ──┐        │
   └───────────┬───────────┘            OR                 │        │
               │              2B-judge orchestrator picks  │        │
               │              code/gherkin/repair/done ────┘        │
               ▼                                                    │
        red→green against the HIDDEN test  ◀───────────────────────┘
```

The two drivers of the fix loop are the alternatives measured below: a **deterministic fix-loop**
(fixed order: code→repair, bounded) versus a **2B-judge orchestrator** that picks the next revision
action (the EXT-013 grounded judge).

## Attribution — orchestration vs deterministic fix-loop

Held-out more-itertools, intent-only (test HIDDEN), identical tools (proven gherkin + parse-gated repair):

| Driver | red→green | Wilson 95% |
|--------|-----------|-----------|
| 2B-judge **orchestrator** (agentic) | 6/37 = 16.2% | 7.7–31.1% |
| Deterministic **fix-loop** (fixed)  | 7/37 = 18.9% | 9.5–34.2% |

**Finding:** the 2B-as-orchestrator adds **no benefit** over the deterministic fix-loop — marginally
worse, well within overlapping CIs. The judge picks sensible revisions, but the underlying **generation**
still cannot crack the hard classes (the "repeat-kwarg" cluster, reshape, derangements, concurrent-tee).
So the bottleneck is **generation, not orchestration**.

**Design consequence:** the Jaros-native solve (EXT-013) defaults to the **deterministic fix-loop**; the
orchestrator judge-agent is available but not the driver. The convergence lever (#12) targets
**empowering generation of the hard classes** (deterministic helpers, generate-and-test, richer
test-feedback + per-call validation), pursued generically — never special-casing benchmark items.
