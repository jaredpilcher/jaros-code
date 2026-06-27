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
| **Jaros-native** fix-loop via Runtime (EXT-013) | 7/37 = 18.9% | 9.5–34.2% |
| generate-and-test N=4 by self-tests (#12 — **PRUNED**) | 5/37 = 13.5% | 5.9–28.0% |
| stronger-oracle docstring augmenter (#12 — **PROMISING, unconfirmed**) | 8/37 = 21.6% | 11.4–37.2% |

**#12 stronger-oracle augmenter — PROMISING but NOT a confirmed lift (2026-06-27, augment_37.txt):**
strengthening the model's self-tests with assertions parsed from the target's VISIBLE docstring examples
(honest — AST-scan + unit test confirm it never reads `test_more.py`/`redgreen`) scored **8/37 = 21.6%**,
a nominal **+1 over the 7/37 single-shot baseline**. It solved `Reject by ID` and `product_index`-iterator
that the default missed (plausibly the stronger oracle driving more corrective fix iterations) — but it
LOST `gray_product` the default got, so the net is +1. **HONESTY CAVEAT (binding):** the Wilson CIs
overlap heavily (11.4–37.2% vs 9.5–34.2%), n=37, single run — **a +1/37 is INSIDE the noise band, not a
statistically confident improvement.** Per the project's honest-measurement discipline (a +6% best-of-6
earlier was pure noise), this is NOT claimed as a win and is NOT wired into the default solve until
**confirmed stable by re-measurement** (does augment ≥ baseline across repeated paired runs, re-solving
the same mechanism tasks?). Verdict pending confirmation.

**#12 generate-and-test PRUNED (2026-06-26, held-out gen4_37.txt):** best-of-N (N=4) selecting by the
model's OWN self-tests scored **5/37 — a REGRESSION** below the single-shot 7/37 (and the 6/37 agentic).
It dropped `exactly_n` and `gray_product` that single-shot solved. **Root cause:** the model's
spec-derived self-tests are WEAK/incomplete oracles, so selecting the candidate that passes the most
self-tests picks **self-test false-positives** (a wrong candidate that passes the flaky self-tests) over
a more-correct candidate that happened to fail one. With weak oracles, *more candidates + self-test
selection makes it worse, not better.* **Lesson for #12:** the lever is **STRONGER ORACLES** (better
self-tests / deterministic property + edge-case + docstring-example checks that discriminate real
correctness), NOT more candidates. Best-of-N pruned again — but this time with a mechanism, not a noisy
number. The mechanism is kept (additive, behind the gate) but never wired into the default solve.

**Parity confirmed (2026-06-26):** the Jaros-native solve (EXT-013 — agents emit inert Decisions, every
host effect through `Runtime.apply`, DecisionLog-logged + replayable) scores **7/37 = 18.9%, EXACTLY the
Python fix-loop's number** (same Wilson CI). Different pass-set in places (2B variance — e.g. Jaros-native
cracked the `gray_product` repeat-kwarg task the others missed, but missed `Reject by ID`) yet the same
count: the two-plane migration preserves capability with zero loss. Prove-out-Jaros: done.

**Finding:** the 2B-as-orchestrator adds **no benefit** over the deterministic fix-loop — marginally
worse, well within overlapping CIs. The judge picks sensible revisions, but the underlying **generation**
still cannot crack the hard classes (the "repeat-kwarg" cluster, reshape, derangements, concurrent-tee).
So the bottleneck is **generation, not orchestration**.

**Design consequence:** the Jaros-native solve (EXT-013) defaults to the **deterministic fix-loop**; the
orchestrator judge-agent is available but not the driver. The convergence lever (#12) targets
**empowering generation of the hard classes** (deterministic helpers, generate-and-test, richer
test-feedback + per-call validation), pursued generically — never special-casing benchmark items.
