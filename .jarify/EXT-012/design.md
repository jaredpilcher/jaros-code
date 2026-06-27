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
| stronger-oracle docstring augmenter (#12 — **LIKELY LIFT, 2 runs**) | 8/37 & 9/37 = 21.6/24.3% | 11.4–40.1% |

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

**CONFIRMATION (2026-06-27, augment2_37.txt): the re-run scored 9/37 = 24.3%** [Wilson 13.4–40.1%].
BOTH augment runs (**8 and 9**) exceed the single baseline run (**7**), and BOTH re-solve the same
mechanism tasks the default misses — `Reject by ID` + `product_index`-iterator (run 2 also took a
`repeat`-cluster task). This is a **reproducible, principled mechanism** (the stronger docstring-derived
oracle gives the fix-loop better red signal on tasks that have docstring examples), not random variance.
Mean ~8.5 vs 7. **REMAINING RIGOR before integrating:** I have 2 augment runs but only 1 baseline run —
running a DEFAULT (no-augment) re-run (`default2_37.txt`) to confirm the baseline's 7 is STABLE (not
itself varying to 8–9). If the baseline holds ~6–7, this is a genuine honest lift and the augmenter
becomes the default solve path; if the baseline also reaches 8–9, it was shared variance (parity). Not
integrated until that check clears — honest measurement to the end.

**FINAL VERDICT (2026-06-27, default2_37.txt = 5/37): CONFIRMED LIFT → INTEGRATED.** Baseline is now 2
runs **[7, 5]** (mean 6) — and NEITHER baseline run solves the mechanism tasks. Augment is 2 runs
**[8, 9]** (mean 8.5) — and BOTH solve `Reject by ID` + `product_index`. The augment range **[8,9] sits
entirely above the baseline range [5,7]** (the *worst* augment run beats the *best* baseline run), with a
reproducible, principled mechanism (stronger docstring-derived oracle → better fix-loop red signal on
tasks that carry docstring examples). The docstring-augmenter is now the **DEFAULT Jaros-native solve**
(`behavioral_solve_jaros` augments self-tests from the VISIBLE docstring by default; 229 tests pass, no
regressions; honest — never reads the hidden oracle). **jaros-code's first honestly-confirmed capability
lift: 7/37 → ~8.5/37 mean on held-out more-itertools, via STRONGER ORACLES (the #12 lever, validated).**
Evidence base is 2 runs each + a clean mechanism asymmetry; reversible if larger-N data disagrees.

**INTEGRATION CORRECTION (2026-06-27 06:20):** the FIRST integration attempt (`23f67a4` — re-wiring
`attempt_gherkin_jaros` to augment via a new `behavioral_solve_jaros(augment_source=...)` path) REGRESSED
the default: a confirmation run (augment3) FAILED `fix last()` and `Reject by ID` at tasks 1–2 — tasks
that ALL 5 prior runs (both augment runs, both baselines, agentic) passed. The re-implemented path did
NOT match the PROVEN standalone `--augment` (`attempt_gherkin_jaros_augment`). **REVERTED** (restored the
clean default + the proven standalone path; 227 tests pass). The LIFT itself remains real and proven via
`--augment` (8, 9 vs 7, 5). It must be RE-INTEGRATED correctly — make the default *call the proven
`attempt_gherkin_jaros_augment`*, not a re-implementation — and re-confirmed by a fresh run before
claiming "integrated". Honest self-correction: the regression was caught at 4/37 (a basic-task failure),
not shipped silently. The "integrated" claim in the prior commit/overnight log is hereby corrected to
"confirmed, integration reverted pending a correct redo".

**LIFT RE-ASSESSMENT (2026-06-27 07:44) — the lift is NOT robust; largely VARIANCE.** A 3rd run of the
SAME proven `--augment` path (`augment3_37.txt`) tracks the BASELINE: by 21/37 it had only 4 pass and
solved NEITHER `Reject by ID` NOR `product_index` — the very "mechanism" tasks that runs 1 & 2 solved.
So the 8 and 9 were largely lucky generation variance, not a reliable docstring-oracle effect. 3-run
augment picture (FINAL) = **[8, 9, 6]** (mean 7.7) vs baseline **[7, 5]** (mean 6) — heavily overlapping
ranges; augment3 = 6/37 solved 0/2 mechanism tasks, confirming they were variance. **Honest verdict: the
docstring-augmenter is ≈ PARITY within noise on this 37-task suite; the docstring mechanism is NOT
reliably reproducible; NOT integrated.** This is the 3rd honest non-win (after best-of-N and
generate-and-test). **Methodological lesson:** a 37-task suite is too noisy to confirm a +1–2 lift — a
single run's mechanism wins can be variance. The #12 lever needs (a) a more RELIABLE mechanism and/or
(b) a bigger, less-noisy benchmark (HumanEval/MBPP, hundreds of items) where a real signal can't hide in
37-task variance. Honest measurement caught this — the 2-run excitement did not survive a 3rd run.

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

## Clean low-noise bar VALIDATED (2026-06-27)
The noisy 37-task commit-replay suite gave 4 FALSE PARITIES (best-of-N, gen-and-test, augmenter, plan-then-code). The deterministic HumanEval pass@1 bar (pass1_eval, single-shot temp=0, ZERO run-to-run variance) DETECTS real effects. On HumanEval[:70] (the run hung at task 71 on an LLM-client no-timeout bug): base solve_pass1 = **58/70 = 82.9
## HumanEval A/B: self-gated thinking (2026-06-27, pass1_ab.txt, full 164, robust runner)
solve_pass1 (direct) = 115/164 = 70.1%; solve_gated (self-gated thinking) = 136/164 = 82.9%; DELTA = +21, DETERMINISTIC (temp=0, same tasks+harness -> zero run-to-run variance). The +21 is a REAL A/B mechanism win: self-gated thinking (solve direct; if it fails the VISIBLE docstring examples, spend one <think> reasoning pass) genuinely solves 21 that direct misses on the HIDDEN tests. HONEST (visible examples only TRIGGER the think; hidden tests score -> no leakage). HONESTY CAVEAT (binding, Tenet 3): the ABSOLUTE (70-83% for a 2B) is implausibly high = HumanEval CONTAMINATION (model has seen it). The absolute is NOT an honest capability number and is NOT a claimed external-benchmark milestone. Takeaways: (1) self-gated thinking is a STRONG real mechanism -> test on the held-out repo bar; (2) HumanEval contaminated -> the 101-task held-out repo bar is the honest instrument.
