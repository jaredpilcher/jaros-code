# Published-numbers provenance ledger

Every figure the owner has stated publicly is recorded here with the exact commit(s)
and run behind it, so each public claim is reproducible on demand. This ledger is part
of **Tenet 3's surface** (reproducible & honest): if a future change makes any figure
here unreproducible, that is a **defect to fix or disclose**, never to ignore.

Priority raised by the outside review (2026-07-01): "Preserve provenance of published
numbers ... Published claims are now part of Tenet 3's surface."

Convention: each entry gives the HEADLINE figure, the bar it was measured on, the
mechanism commit(s), and how to reproduce. Where a figure spans a lineage of commits,
the one that produced the exact published number is marked **[headline]**.

---

## 1. Syntax-repair: 64 → 76 / 100 (+12%), held-out deterministic pass@1

- **Bar:** deterministic pass@1 (temp=0) on a held-out HumanEval 100-task slice, via
  `harness/pass1_eval.py` (the honest single-shot bar; NOT the noisy best-of-6).
- **Commit [headline]:** `3b1a861` — "parse-gated syntax-repair — lifts HELD-OUT
  deterministic pass@1 +12% (first real pursuit win)". The +12% is exactly 64%→76%.
- **Lineage:**
  - `f47de50` — deterministic pass@1 harness (`pass1_eval`) — the measurement foundation.
  - `3b1a861` — parse-gated syntax-repair mechanism (**the 64→76 lift**).
  - `0c7e29c` — "syntax-repair kept stripping leading imports — recover them (+5 more on
    0-50: 38→43)" — the extra lift taking the cumulative win toward +16%.
- **Reproduce:** `python -m harness.pass1_eval` on the held-out slice at these commits.
- **Why it's honest:** temp=0 single-shot on held-out tasks the mechanism was never tuned
  on; the 2B emitted correct logic with broken indentation → wouldn't import; the
  deterministic repair recovers it. See memory `jaros-code-deterministic-pass1`.

## 2. Commit-replay: 1/37 → 4/37 (10.8%), held-out repo-task gate

- **Bar:** the held-out 37-task commit-replay gate (real repo commits, red→green pipeline).
- **Commit [headline]:** `cf659bf` — "EXT-011: multi-function localization — intent-only
  1/37 → 4/37 = 10.8% (structural unlock)".
- **Baseline lineage:** `c2980e2` / `99af275` — "headline stays 1/37" (the think-jig was
  honestly REJECTED by the gate, so 1/37 was the standing baseline before the localization
  unlock). Later `448514d` — behavioral Gherkin loop 6/37 = 16.2% vs baseline 4/37 = 10.8%.
- **Reproduce:** the EXT-005/EXT-011 eval harness on the 37-task corpus at `cf659bf`.

## 3. MBPP: 65% (qwen) vs 48% gated / 25% direct (gemma), standalone-fn-gen

- **Bar:** MBPP clean bar (contamination-checked), standalone-fn-gen class.
- **Commit [headline]:** `f72df52` — "MBPP contamination check: qwen standalone-fn-gen edge
  is REAL — 65% MBPP (clean bar) vs gemma 25% direct/48% gated (~2.6x). NOT HumanEval
  contamination. First clean multi-model payoff".
- **Note:** the published "65-vs-48" pairs qwen's 65% against gemma's **gated** 48%
  (gemma direct is 25%). Recorded in `.jaros-data/config/models/qwen2.5-coder-3b.json`
  (classes[].mbpp_confirm). Later firmed on HumanEval-40 (qwen 90% vs gemma 82.5%).
- **Caveat (honest):** end-to-end routed MBPP is only +10pp directional, CI-overlapping at
  n=20 (`0202f6c`) — the *profile* gap is real but the *routed-system* lift is marginal on
  the current close roster. See item under review-priority-2 (system metric).

## 4. pass@k: 0/7 on the hard repo class (generation wall)

- **Bar:** hard multi-step-repo class (real more-itertools feature commits), fair-temp
  sampling k=20.
- **Commit [headline]:** `9856d52` — "pass@k VERDICT: fair-temp sampling solves 0/7 hard
  repo tasks the harness fails — genuine GENERATION wall on this class (not selection);
  k=20 caveat; next=decomposition".
- **Lineage:** `ba9c50d` (temp-0.8 run confounded → re-probe at temp 0.4), `e1c5b1c`
  (EXT-019 pass@k probe harness), then `ff7726f` (decomposition also 0/8 — the wall holds).
- **HONEST UPDATE (2026-07-01):** the "generation wall" is being re-examined. Some earlier
  reasoner trials were throttled by a 90s client-timeout bug (killed the 9000-token think);
  un-throttled, qwen3-4b-thinking *completes* these runs (cell #35). But the wall is REAL
  for at least some tasks even un-throttled (`_sorted_window`, `_running_median_windowed`
  fail with repair). See memory `jaros-code-hardclass-ceiling`. The 0/7 pass@k figure
  (gemma/qwen-coder, not the reasoner) stands as published.

## 5. Review regression: 2/17 → 1/17 (Gherkin slice reviews regress)

- **Bar:** the 17-task dev slice, review sub-tasks.
- **Commit [headline]:** `1096324` — "EXT-012: record dev findings — Slice 1a helps
  (2/17 vs 1/17), reviews regress (1/17), guard insufficient".
- **Note:** honestly recorded as a REGRESSION on the review sub-slice even while Slice 1a
  helped overall; the keep-or-improve guard (`0ee5527`) was the response. This is a
  published *negative* — its provenance matters as much as the wins (Tenet 3).

---

## Maintenance rule

When a new figure is stated publicly, add an entry here in the SAME commit that states it,
with the mechanism commit and reproduce steps. Before any release/launch, re-run the
reproduce steps for each entry; a figure that no longer reproduces is a Tenet-3 defect.
