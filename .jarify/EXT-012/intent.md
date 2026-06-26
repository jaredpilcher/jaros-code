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
