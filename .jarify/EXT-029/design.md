# Design: EXT-029 Cross-Model Collaborative Solve

## Motivation

Prior probes (EXT-019 pass@k, EXT-026 maximal-help) showed the hard multi-step-repo
class (0/8 baseline for both gemma and qwen, correlated at the task level) resists:
- Sampling diversity (pass@20 near-zero)
- Maximal harness help (retrieved context + worked example + plan)

This suggests the failure mode is NOT missing harness scaffolding for a single model
but rather a systematic blind spot SHARED by both models when reasoning alone.

Collaboration hypothesis: the two models have COMPLEMENTARY partial-strengths.
- qwen2.5-coder-3b: stronger code structure, formatting, syntactic correctness.
- gemma-4-e2b: stronger reasoning about intent, logic, behavior specification.

A draft(qwen) + critique(gemma) + revise(qwen) loop exposes the code to gemma's
intent-reasoning BEFORE the final revision — potentially escaping the systematic
correlated blind spot.

## Architecture

```text
collaborative_solve(problem, *, draft_fn, critique_fn, revise_fn, test_fn, max_rounds)
                │
                │   All callables INJECTABLE (offline-testable, no Jetson needed)
                │
                ├── [Phase 1: Draft]
                │     draft_fn(problem) -> candidate_code
                │         │
                │     test_fn(problem, candidate_code) -> {passed: bool}
                │         │
                │         ├── passed=True  -> return {solved:True, rounds:0, winner:"draft"}
                │         └── passed=False -> enter loop
                │
                └── [Loop up to max_rounds]
                      │
                      ├── critique_fn(problem, candidate_code, test_result) -> critique_text
                      │       GENERATES only. Never selects / ranks. Not the arbiter.
                      │
                      ├── revise_fn(problem, candidate_code, critique_text) -> revised_code
                      │       GENERATES only. Never selects / ranks. Not the arbiter.
                      │
                      └── test_fn(problem, revised_code) -> {passed: bool}
                              SOLE ARBITER of solved (model-as-judge forbidden)
                              passed=True  -> return {solved:True, rounds:r, winner:"collab"}
                              passed=False -> next round or all-fail


_make_jetson_fns(draft_model, critique_model, revise_model, manager_url)
    Returns: (draft_fn, critique_fn, revise_fn)
    Each fn assumes correct model is ALREADY LOADED (no per-call swap)
    swap_fn / llm_fn INJECTABLE for offline tests


BATCHED PROBE RUNNER (collab_probe / run_collab_probe)
    Controls swaps externally to minimise Jetson swap count:

    Naive (per-task):     swap per task * n tasks * 2 swaps/round = 2 * n * R swaps
    Batched (per phase):  1 swap per phase * 3 phases/round      = 2 * R + 1 swaps

    (n=6, R=2 -> 24 naive vs 5 batched — 5x fewer Jetson restarts)

    Manager HTTP swap: POST http://192.168.1.183:8001/serve {model: model_id}
    Oracle gate: _run_nodes(repo, task["redgreen"], timeout) — score-only, never
    fed back to the model during generation.
```

## Key Design Decisions

1. **test_fn sole arbiter (Tenet 3 + REQ-1)**: The deterministic test is the ONLY
   gate. critique_fn and revise_fn only generate candidates; they never decide which
   is "correct". This is the same invariant as solve_routed_escalating (EXT-021 REQ-6)
   — model-as-judge is architecturally forbidden.

2. **Injectable callables (Tenet 1)**: All four callables (draft_fn, critique_fn,
   revise_fn, test_fn) are parameters. The loop itself is pure control-flow with no
   side effects. Fully offline-testable without a Jetson.

3. **Batching to minimise Jetson swaps**: Each model swap takes ~20s on the Jetson
   (llama-server restart). The batched runner (probe-level) drafts ALL tasks before
   swapping, reducing total swap count from O(n*R) to O(R). The factory fns expose
   this by NOT bundling swaps inside each call.

4. **Complementary role assignment**: qwen (stronger code structure) drafts and
   revises; gemma (stronger intent/logic reasoning) critiques. Roles are fixed and
   motivated by measured model profiles — not arbitrary.

5. **Transcripted attempts**: Every round's (draft, critique, revised) triple is
   recorded in `attempts` for post-hoc inspection. This enables diagnosis of WHY
   collaboration helps or fails on specific tasks.

6. **Honest reporting**: `run_collab_probe` compares against the explicit 0/8
   baseline, reports Wilson95 CI, and gives a clear verdict. No number is claimed
   without the oracle gate. (Tenet 3.)

## Relation to Other Specs

- **EXT-021** (multi-model routing): solve_routed_escalating is sequential (try A,
  then B). collaborative_solve is PARALLEL-logic (A drafts, B critiques, A revises) —
  complementary not redundant. Both use test_fn as the sole arbiter.
- **EXT-026** (maximal-help): three deepening layers (context + example + plan) for a
  SINGLE model. EXT-029 uses TWO models, minimal prompt depth. Together they form a
  2×2 matrix: {1 model, 2 models} × {shallow prompt, deep prompt}.
- **EXT-019** (pass@k): samples the SAME model k times. EXT-029 uses a DIFFERENT
  model in the critique slot — cross-model vs. within-model diversity.
- **Issue #33** (team discussion): the richer form of multi-model collaboration
  (structured debate, multiple critics). EXT-029 is the base case; #33 builds on it.
- **EXT-028** (dependency structure): feeds the `context` field in the problem dict,
  enriching the draft and revise prompts with structured dependency information.
