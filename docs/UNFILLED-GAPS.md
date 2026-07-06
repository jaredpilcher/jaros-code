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

**Reasoning-model lever — TESTED 2026-07-02, BLOCKED by harness-format incompatibility:** base
`deepseek-r1-distill-qwen-1.5b` (reasoning intact, the genuinely-different lever) run through the real harness on a
control + a miss → **NO applicable edit from 7 samples on BOTH** — it emits prose/markdown explanations, NOT the
SEARCH/REPLACE edit format the harness requires, so it produces ZERO parseable edits and can't be dropped in.
(CAVEAT/harness-bug noted: `grow_one.sh` doesn't delete a stale `pred_<id>.jsonl` when swapping models, so a
prior model's pred gets re-evaluated → a FALSE `resolved=True` on the control; the REAL deepseek signal is the
"NO applicable edit". Fix: `rm` the pred at grind start.) So using a reasoning model needs a **new prose/diff-parsing
solve path** (a harness build) AND its reasoning on hard SWE is itself uncertain — a larger, uncertain effort, deferred.

**What we did NOT yet try (honest — remaining threads, low-but-nonzero EV):**
- Reasoning-DISTILLED training data (reasoning traces → patch, not issue→patch) — we lack a sovereign source of
  correct reasoning traces for hard SWE (our best local reasoner is itself at the wall). Needs a data source.
- A gemma-2B / other-family CODER specialist (expected same null by the mechanism; not run — the 3B+1.5B airtight nulls make it low-EV).
- A prose/diff-parsing solve path so reasoning models (deepseek) become harness-usable (build + uncertain reasoning payoff).

**REVISIT TRIGGERS (fill this gap when any fires):**
1. A **stronger reasoning-capable model that fits the Jetson (~8GB)** appears (roster growth L6) — measured-better on SWE-bench.
2. A **sovereign source of correct hard-SWE reasoning traces** becomes available → reasoning-distillation training (L8), scoreboard-tested.
3. A **fundamentally different solve architecture** (multi-turn agentic repo interaction, reduction library) that adds reasoning at inference.
4. Owner **shadow-mode** tasks reveal the real distribution differs from SWE-bench-Lite (may be more tractable).

**Honest bottom line:** we filled every lever we could (harness, selection, training-infra) and MEASURED the boundary.
The ~13% is the honest small-local-model frontier today. Not giving up — bookmarked with concrete triggers.

---

## GAP-2 — Generic ORDERING check for the deterministic minimum (priority/LRU-class semantic false-dones)

**State:** `open (2026-07-06)`. Assessed (not built) per the EXT-036 REQ-26/27/28 done-honesty line
(`harness/system_builder.py`, HEAD `065815c`, `system_builder.py` clean at `cbced82`
"TASK-42 - multi-module entrypoint plan-repair").

**The measured gap:** `build_system`'s deterministic-minimum acceptance floor (REQ-26 `_minimum_acceptance`,
REQ-27 `_derive_roundtrip_pair`/`_roundtrip_acceptance_check`, REQ-28 `allow_usage_validation`) closes
runtime-defect false-dones (crash / graceful-error-at-rc=0 / silent-non-persistence) but is BLIND to
runs-fine-but-WRONG-ORDER semantic bugs. Measured on `priority-jobqueue-cli` (`harness/system_suite.py`
`FIRST_SLICE`): a build that runs, and round-trips (enqueues a job, `run` returns SOME job), still reports
`done=True` against the deterministic minimum even if it dequeues in INSERTION order rather than
priority order — the independent oracle (`checks=[(...,"enqueue low 1\nenqueue high 5\nrun\n","ran high")]`)
correctly rejects it. Same class: `kv-store-ttl` (TTL expiry timing), any `sorted`/LRU/FIFO/LIFO spec.

**Why a generic, SAFE ordering check was assessed as NOT feasible to build now (the honest verdict):**
1. **The motivating class's own interface is STDIN-line-protocol, not argv.** `priority-jobqueue-cli`'s
   sentence states `python main.py` with no argv, reading `enqueue <name> <priority>` / `run` as STDIN
   LINES. The existing REQ-27 round-trip mechanism (`_roundtrip_acceptance_check`) only knows how to probe
   an ARGV-style CLI (`subprocess.run([sys.executable, entry, add_cmd, *sentinel_args])`); it does not
   fire for this task at all today (`_derive_roundtrip_pair` finds no `add`/`list`-vocabulary word — the
   sentence uses `enqueue`/`run`). A generic ordering check would first need a GENERIC, spec-derived
   argv-vs-stdin-protocol detector (a materially different, unbuilt capability) before it could even probe
   the right invocation shape — building the ordering assertion on top of that gap compounds two unproven
   mechanisms into one gating check.
2. **The priority VALUE's argument position is not safely inferable in general.** Even where a spec pins
   an exact invocation (as `FIRST_SLICE`'s task deliberately does — `enqueue <name> <priority>`), a
   general user sentence has no such guarantee. Guessing the priority argument's position/shape
   (`name, priority` vs `priority, name` vs a flag) for an arbitrary spec risks the check either (a)
   silently mis-feeding the "priority" value as ordinary content, so a genuinely CORRECT priority queue
   fails our check for a spurious reason (a **false negative on the deterministic minimum floor** — the
   single worst outcome for a gating check, worse than the status quo semantic blind spot, because it
   would flip a real pass to `done=False` with no way for the builder loop to tell why), or (b) requiring
   agreement across multiple guessed conventions, which only reduces but does not eliminate that risk and
   starts to look like tuning the check to this benchmark's exact phrasing rather than a genuinely generic
   mechanism (the same overfitting concern Tenet 3 forbids).
3. **LRU is materially harder still** — "correct order" depends on an ACCESS HISTORY (a prior `get`
   interleaved with adds), not just insertion order of two sentinels; asserting it generically needs a
   multi-step probe sequence tied to an LRU-specific mental model, which is a different (harder) mechanism
   again, not a generalization of the add/list round-trip.
4. A narrower SAFE subset does exist — FIFO/LIFO order-of-two-sentinels (reusing the proven argv add/list
   round-trip verbatim, no new argument-shape guessing) and "sorted-by-the-single-added-value" (two
   sentinel values with a clear alphabetic/numeric order) — but neither covers the actual measured
   `priority-jobqueue-cli` false-done, and building only that subset would not close the motivating gap
   or satisfy a true-positive test on the priority class, so it was not pursued piecemeal without owner
   sign-off on a scoped-down version.

**Net: the false-negative risk (silently flipping a genuinely-correct build to `done=False` on a gating
floor) outweighs closing this one measured false-positive class, and a safe version would not actually
close the motivating example.** No code was changed for this gap (assessment only); this is a
`docs`-only bookmark commit, not a code change.

**REVISIT TRIGGERS (fill this gap when any fires):**
1. A generic, spec-derived argv-vs-stdin-line-protocol detector gets built for another reason (it would
   remove blocker #1 above and make the STDIN-driven classes probeable at all).
2. A CLI-interface convention gets PINNED harness-wide for order-bearing commands (e.g. `build_system`
   itself starts requiring/generating a machine-readable interface manifest per module, not just prose) —
   removing the argument-position guess entirely.
3. The FIFO/LIFO/sorted-by-value SAFE subset is explicitly requested as a scoped-down, honestly-labeled
   partial win (it would not close the priority-jobqueue example, but would close a related, narrower
   false-done class with near-zero incremental false-negative risk).
