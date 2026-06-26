# EXT-012 — Behavioral Gherkin-Driven Alignment Loop (2B-authored, all layers)

## Why

The real-repo frontier (EXT-011) is gated by the 2B *copying the parent instead of making the change*
and by having no decomposition for multi-step work. The owner's architecture (2026-06-26) attacks both:
the 2B reasons in a **behavioral layer (Gherkin)** first, derives **tests** from it, then writes **code**
to satisfy the tests — with **alignment enforced at every seam**. Gherkin is the persistent behavioral
source of truth; the model can hold only the *relevant* slice in context at a time, so any problem
decomposes massive→tiny. THE 2B AUTHORS EVERYTHING (Gherkin, tests, code — create/modify/delete);
the harness (deterministic plane) only runs tests and maintains exact pointers. Tenet-2 (local-2B-only)
and Tenet-1 (two-plane) intact.

## The loop (the 2B is the agent at every step)

0. **Bootstrap.** If the repo has no Gherkin index, the 2B generates Gherkin descriptions for ALL
   existing code units first, so it has a behavioral model to reason over. Persisted (reused across
   runs; foundation for the [[jaros-code-gherkin-vectordb-architecture]] verified behavior→code memory).
1. **Reconcile existing behavior.** Given a task, the 2B scans each existing Gherkin and decides
   keep / MODIFY / DELETE. A delete propagates: a test asserting the behavior is GONE → code that
   removes it.
2. **Author new behavior.** The 2B writes NEW Gherkin for the task and SELF-REVIEWS in a loop until it
   judges the full set (new + kept + modified) (a) satisfies the task AND (b) preserves all behavior
   that must not change.
3. **Tests.** The 2B generates/modifies tests and SELF-REVIEWS test↔Gherkin alignment (every scenario
   has a matching test; nothing stray).
4. **Code.** With the tests fixed as the target, the 2B generates/modifies code until ALL tests pass.
5. **Sign-off review.** The 2B reviews each modified code against its Gherkin to confirm alignment
   before declaring the task done.

Alignment seams (the point of the whole thing): Gherkin↔task, tests↔Gherkin, code↔tests, code↔Gherkin.
Executable tests are the HARD checkpoints; the 2B self-reviews are the soft ones.

## The Gherkin index

A separate file/files, one entry per code unit: the behavioral description + a POINTER to the code it
describes. **Design decision — CONFIRMED by owner ("sync anchors", 2026-06-26):** the 2B anchors each
entry to a SYMBOL (qualified name + file); the deterministic tool plane resolves symbol→line-range via
AST and re-resolves after every edit ("sync anchors"). The 2B owns behavioral CONTENT; the tool keeps
POINTERS exact (raw line numbers drift and a 2B counting lines desyncs the index — Tenet-1 keeps
deterministic bookkeeping in the tool plane). This lands in Slice 2 (the persisted index).

## Results so far (dev, honest — 2026-06-26)

- **Slice 1a (core loop: Gherkin -> self-tests -> code -> fix, NO reviews): dev 2/17 vs baseline 1/17.**
  The behavioral loop HELPS — matched the baseline's 1 (factor recipe) AND added a new pass (Reduce
  groupby in all_equal). Small-n, overlapping CIs; a directional dev signal, not a verdict.
- **Slice 1b (+ the self-review loops): dev 1/17 — REGRESSED.** The Gherkin/test self-review rewrote a
  spec that was already right and broke task 14 (factor recipe) that 1a passed. Naive review HURTS.
- **keep-or-improve guard on the sign-off: did NOT recover it (still 1/14).** Diagnosis: the damage is
  UPSTREAM (the Gherkin/test review changes the spec before code-gen), so guarding only the sign-off
  can't undo it. To salvage reviews, the Gherkin/test review output must itself be gated (keep the
  pre-review version unless the new one yields code that still passes) — deferred.
- **Decision: Slice 1a (no reviews) is the best variant -> taken to the held-out 37 gate** (vs the
  4/37 multi-function baseline). Target cap (>4 functions) committed to keep it tractable.

**HELD-OUT 37 GATE RESULT (2026-06-26) — the behavioral loop GENERALIZES and BEATS the baseline:**
- **Slice 1a (Gherkin -> self-tests -> code -> fix): 6/37 = 16.2% [Wilson 7.7-31.1%]** vs
  multi-function baseline **4/37 = 10.8%**. +2 passes; same direction as dev (2/17 vs 1/17). Honest
  intent-only (self-tests derived from the intent, hidden oracle alone scores; no leakage).
- **Pass-set DIFF (the real story = COMPLEMENTARY solvers):** common 3 (last, running_median,
  subfactorial); 1a-UNIQUE 3 (Reject by ID, Issue 900, Revert pairwise) — solved commits the baseline
  COULDN'T; baseline-unique 1 (exactly_n). **Union = 7/37 = 18.9%** — the ceiling of an honest ensemble.
- CIs overlap at n=37 (directional, not yet statistically conclusive) — needs the toolz cross-repo gate
  + more commits to firm up. NEXT: (a) toolz held-out gherkin gate (cross-repo); (b) honest ensemble
  (baseline + gherkin-loop, select via the gherkin loop's SELF-tests not the oracle) to capture ~7/37.

## Honesty / eval (binds the whole thing)

Measured on EXT-011 commit-replay: the 2B's self-generated tests are SCAFFOLDING derived from the
intent — it NEVER sees the hidden repo oracle, which remains the only score (red→green). No leakage.
Every slice gated on HELD-OUT commits across both repos; revert anything net-negative. Report pass@1
honestly with Wilson CI.

## Build order — faithful vertical slices (each a REAL piece of the loop, never a fragment)

- **Slice 1 (single unit = the eval's natural grain):** for each touched function — generate its current
  Gherkin → reconcile/author Gherkin for the intent (self-review) → generate self-tests (review
  test↔Gherkin) → implement to pass them (iterate to green) → code↔Gherkin sign-off → score on the
  hidden oracle. The FULL loop at one-unit scope.
- **Slice 2:** persist the Gherkin index (separate file, symbol-anchored pointers); bootstrap + reuse
  across tasks; seed the cross-run verified behavior→code store.
- **Slice 3:** whole-repo bootstrap + reconcile across multiple units (modify/delete neighbors,
  preserve-unchanged), multi-file changes.

Anti-rut rule (owner, 2026-06-26): rank by impact×tractability, structural/by-construction first, max
1-2 attempts per sub-lever then re-rank; the taxonomy is the worklist.

## Performance / parallelism (owner note 2026-06-26 — "parallelize what we can" in upcoming changes)

Measured cost of Slice 1a: ~3-4 min PER FUNCTION (6 LLM calls: Gherkin, self-tests, 3x code; + 4 Docker
runs: 3x self-test, 1x oracle). Multi-target commits multiply it (the 6-target "Add dft/idft" took
~10 min). HARD FLOOR: the single Jetson GPU serializes ALL LLM calls (llama.cpp serves one at a time) —
so "parallel" LLM calls mostly just queue; the run is LLM-bound. Genuine wins: (1) overlap CPU (Docker
tests) with GPU (LLM gen) in a pipeline; (2) run independent Docker tests concurrently across CPU
cores; (3) across-task parallelism via git WORKTREES (one per worker, no checkout conflict) — LLM still
queues on the one Jetson. BIGGER lever than parallelism = FEWER LLM calls: merge Gherkin+self-tests into
one call, cap fix iters, CAP TARGET COUNT (skip/limit huge multi-target commits the 2B can't nail
anyway). A second inference device is the other throughput axis. Do this AFTER Slice 1a's verdict.
