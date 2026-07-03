# UNFILLED GAPS — the honest running log of limitations we cannot fill YET

**Owner directive (2026-07-02):** *"if that doesn't work, mark this as the true limitation of the system and
keep a running log of that as a gap that we cannot fill yet. We'll fill it eventually but we fill as much
as we can now, honestly and without giving up."*

This is that log. Each entry is a **MEASURED** limitation (not assumed), with the evidence, the mechanism,
and the concrete **revisit triggers** that would let us fill it. A gap here is a **dated bookmark, never a
surrender** — the pursuit is unbounded (PRIME-001). When any revisit trigger fires, we re-attempt and move
the gap toward `filled`. Complements `docs/GAP-MAP.md` (the live steering wheel) and its "measured walls".

States: `open (dated)` → `narrowed (partial win)` → `filled (number)`.

---

## GAP-1 — SWE-bench uncurated resolve-rate stuck at the small-local-model frontier (~13%)

**State:** `open (2026-07-02)`. Current honest number: **uncurated SWE-bench-Lite ≈ 13% (2/15, Wilson95 [4%,38%])**
with qwen2.5-coder-3b + our harness at $0 on the Jetson. Claude-Code-on-Opus is ~62.7%. The gap is the parity gap.

**What we MEASURED (this is why it's a real limitation, not an assumption):**
- **Harness levers saturated (L0–L5):** localization, SEARCH/REPLACE parsing, best-of-N, repair loop, line-level
  apply — all built + productionized (16 tests). Four earlier "model ceilings" were harness bugs we fixed. No
  remaining harness lever moves the number.
- **Selection exhausted:** oracle best-of-6 = first-applicable (gap ZERO) — for the misses, NOT ONE of 6 samples
  resolves. A ranker / test-gate cannot recover them (no correct candidate hiding in the N). The misses are
  **genuine GENERATION limits**, and they are "applied-but-wrong" = right location, **wrong logic (reasoning)**.
- **Training lever (L7 LoRA) — BUILT END-TO-END + TESTED ON THE SCOREBOARD, NULL across model sizes:**
  - Full pipeline proven on the Jetson GPU: torch cu130, QLoRA-4bit, GGUF-convert, llama.cpp `--lora` serving.
  - Trained **qwen2.5-coder-3B** on 230 SWE-Gym issue→patch pairs → **−13% held-out loss on SWE-bench-Lite**
    (clean, leakage-verified cross-distribution). BUT resolve-rate: **0/11 new resolves on the misses + no
    regression on 2 controls** = specialist ≡ base on the scoreboard (airtight).
  - Trained **qwen2.5-coder-1.5B** likewise → **also 0/11 misses + 2/2 controls** (airtight). Same null, smaller model.
  - **Held-out loss is a MISLEADING proxy:** a LoRA lowers token-loss (fits the patch distribution) WITHOUT
    instilling the REASONING to fix a novel issue. The misses need correct reasoning on unseen problems, which a
    token-distribution adapter does not add — at any size we can train. **Lesson: validate on the scoreboard, never the proxy.**
- **Reasoner (L6) low-EV:** qwen3-4b-thinking ~22min/instance on the hard class, 0 on the multi-step-repo wall.

**MECHANISM (why it's stuck):** the residual misses are **reasoning-limited** — the small models emit an applicable
edit in the right place but with wrong logic, and neither more sampling, nor selection, nor issue→patch training
(which only shifts token-distribution) supplies the missing reasoning. Independent research agrees the small-model
SWE frontier is ~11–15% (SWE-AGILE-8B 14.77%, SWE-smith-7B 11.7%); **our 3B+harness at ~13% is already AT that
frontier.** The gap to Claude is fundamental **small-vs-large-model reasoning capacity**, not a harness or training-infra deficiency.

**What we did NOT yet try (honest — the remaining threads, low-but-nonzero EV):**
- A model whose differentiator is REASONING, with reasoning INTACT (e.g. base deepseek-r1-distill on the misses) —
  training it on issue→diff would destroy the reasoning, so the informative test is the base reasoning model. UNTESTED.
- Reasoning-DISTILLED training data (reasoning traces → patch, not issue→patch) — we lack a sovereign source of
  correct reasoning traces for hard SWE (our best local reasoner is itself at the wall). Needs a data source.
- A gemma-2B / other-family specialist (expected same null by the mechanism; not yet run).

**REVISIT TRIGGERS (fill this gap when any fires):**
1. A **stronger reasoning-capable model that fits the Jetson (~8GB)** appears (roster growth L6) — measured-better on SWE-bench.
2. A **sovereign source of correct hard-SWE reasoning traces** becomes available → reasoning-distillation training (L8), scoreboard-tested.
3. A **fundamentally different solve architecture** (multi-turn agentic repo interaction, reduction library) that adds reasoning at inference.
4. Owner **shadow-mode** tasks reveal the real distribution differs from SWE-bench-Lite (may be more tractable).

**Honest bottom line:** we filled every lever we could (harness, selection, training-infra) and MEASURED the boundary.
The ~13% is the honest small-local-model frontier today. Not giving up — bookmarked with concrete triggers.
