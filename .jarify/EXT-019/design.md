# EXT-019 Design: pass@k latent-capability probe

## Purpose

Measure the gap between pass@1 (what the current harness produces on one try) and
pass@k (whether the 2B CAN produce a correct solution within k tries). The gap
directly answers the founding no-ceiling question: is the bottleneck the MODEL
(incapable) or the HARNESS (fails to select from what the model can produce)?

## Architecture

```text
bigbar_jaros.txt ──► _parse_fail_shas(n) ──► [sha8 ...] (first N [fail] entries)
                                                    │
tasks_corpus(bar="big") ───────────────────────────►│
                                                    ▼
                                         _resolve_tasks(shas, corpus)
                                                    │
                                         [task dict, ...]  (N corpus tasks)
                                                    │
                         ┌──────────────────────────┘
                         │  for each task:
                         ▼
               probe_task(repo, task, branch, k, temp)
                │
                ├─ git checkout parent + test files
                ├─ read orig file content per code_file
                ├─ build file context (preamble, mirrors attempt_gherkin_jaros)
                ├─ g_gherkin(subject, name, parent_src, ctx) at temp=0  ← ONCE PER TARGET
                │
                └─► _core_probe(targets, orig, gherkins, task, repo, k, temp, ...)
                         │
                         ├─ [greedy] generate_fn(... temp=0.0) ──► apply ──► oracle ──► greedy_pass
                         │                                                    │
                         │                              (score-only, never fed back)
                         │
                         └─ for i in range(k):
                               generate_fn(... temp=T)  ← BLIND (no oracle feedback)
                                      │
                                      ▼
                               apply to repo files
                                      │
                                      ▼
                               oracle_fn(repo, redgreen, timeout)  ← score-only
                                      │
                                      ▼
                               restore files to orig
                                      │
                                      ▼
                               n_passed += (1 if passed else 0)
                         │
                         └─► {greedy_pass, n_passed, passk, k}
                         │
                         ▼
               git _reset(repo, branch)   ← always in finally

run_probe:
  ├─ collect per-task results
  └─ print summary table + verdict
       pass@1 = 0/N = 0.0%   (known fails)
       greedy = X/N = Y%      (informational: 1-shot temp=0, no fix-loop)
       pass@k = Z/N = W%      ← THE DECISIVE NUMBER
       Wilson95 CI
       Verdict: STRONG / WEAK / NO SIGNAL
```

## Honesty Invariants

1. The hidden oracle (`_run_nodes` / `oracle_fn`) is called ONLY after each
   sample is generated. Its output is NEVER passed back to `generate_fn`.
2. All k samples are drawn blind — generation order and oracle outcomes are
   independent for each sample.
3. pass@1 is declared 0 by definition (these are tasks the current harness
   already failed); greedy is measured separately and labelled informational.
4. File restoration between samples ensures each sample is applied to a
   clean parent state, not accumulating on a prior sample.

## Injectable Seams for Offline Testing

`_core_probe` accepts `generate_fn` and `oracle_fn` parameters that default to
`_g_code_sampled` (real LLM) and `_run_nodes` (real Docker) respectively. Tests
inject stubs — see `tests/test_passk_probe.py`.

`probe_task` additionally wraps the full git lifecycle. Tests that need to exercise
the sampling loop directly bypass `probe_task` and call `_core_probe` with a real
temp directory and stub functions.

## Estimated Runtime

15 tasks × (1 greedy + 20 samples) × ~30s/sample ≈ 2.5–3 hours wall-clock.
Runtime scales linearly with k. Use --tasks 5 --k 5 for a quick smoke run (Jetson
must be up):

    python -m harness.passk_probe --tasks 5 --k 5 --temp 0.8

## pass@k probe — temp 0.8 run CONFOUNDED (5/15, 2026-06-28)
At temp 0.8: pass@k=YES = 0/5 (NO task where any of 20 samples passes), greedy(temp0)=PASS = 1/5.
SMOKING GUN: task 1 greedy=PASS but all 20 temp-0.8 samples FAIL — the 2B can't even reproduce its OWN
known-correct answer when sampled at 0.8. -> temp 0.8 is TOO HIGH for this 2B; samples are incoherent,
so pass@k=0 measures NOISE not latent-capability-absence. Re-probing at temp 0.4 (the fair test: diverse
but coherent, samples stay near the correct region). Confounded run not used as the verdict.

## pass@k VERDICT (FAIR temp 0.4, concluded 8/15, 2026-06-28) — sampling does NOT reveal latent capability on hard repo tasks
Probed 8 tasks the FULL HARNESS fails, k=20 at temp 0.4 (validated COHERENT: solvable task1 = 19/20, vs 0/20 at temp 0.8).
RESULTS: greedy(temp0)=PASS 1/8 (only task1 — simple gen beats the full pipeline on that 1), passk=YES 1/8,
**pass@k-BEYOND-greedy = 0/7** — NOT ONE of the 7 greedy-FAIL hard tasks was solved by ANY of 20 fair-temp samples.
HONEST VERDICT (no spin): on repo-level red->green commit-replay (the hardest ~80% the harness fails), SAMPLING does NOT
extract latent capability the deterministic generation misses. The bottleneck here is genuine GENERATION capability, NOT
selection — the 'sample-at-scale + verifier' pivot does NOT pay off on this class (there was nothing correct to select).
A MEASURED STRESS on the no-ceiling founding assumption: within k=20 at a fair temp, the 2B cannot generate correct
solutions for these hard repo tasks.
BINDING CAVEATS: (a) k=20 only — pass@k may rise at k=100+ (literature uses large k); 0/7 at k=20 is strong, not
'no capability at any k'. (b) HARDEST class (full-harness-fails); does NOT imply a wall on easier tasks (HumanEval ~70%).
(c) temp 0.4 validated coherent -> not a temp confound. (d) greedy_pass only 1/8 -> simplifying the pipeline isn't a big win either.
NEXT + LAST untried lever: DECOMPOSITION — does breaking the function into explicit sub-steps crack what monolithic generation + sampling cannot?
