# EXT-021 — Multi-Model Routing Harness: Design

The harness gains an **outer routing layer** above the existing two-plane solve. A task is first
classified and routed to the Jetson-fitting model whose measured profile covers its class; the
harness rewires to that model; then the existing orchestrator/solve runs, now wired with that
model's adaptation.

## Components

```text
   solve(problem)
        │
        ▼
   ┌─ model_router.route(problem) ───────────────────────────────────┐   REASONING PLANE
   │   classify class+difficulty (on-device) → Decision{model_id,…}   │   (inert Decision)
   │   unsure → deterministic DEFAULT model (never fails to route)    │
   └───────────────────────────────┬──────────────────────────────────┘
                                    │ Decision
                                    ▼
   ┌─ model_registry ────────────────────────────────────────────────┐   DATA
   │   profiles loaded from .jaros-data/config/models/<id>.json        │
   │   ModelProfile{ id, alias, serve{gguf,ctx,fits}, classes:[…+ev],  │
   │                 adaptation{ tools, agents, config, prompts } }    │
   │   lookup_by_id() · lookup_by_class() · default_model()           │
   └───────────────────────────────┬──────────────────────────────────┘
                                    ▼
   ┌─ model_rewire.rewire(model_id) ─────────────────────────────────┐   EXECUTION PLANE
   │   if served_model != target: Jetson swap (serve.sh -m + restart) │   (the clerk:
   │   point LLM client at <model>; activate its adaptation set       │    validate→execute,
   │   idempotent · guarded · honest-on-failure                       │    logged, replayable)
   └───────────────────────────────┬──────────────────────────────────┘
                                    ▼
            existing two-plane solve, now wired for <model>
       (orchestrator composes THAT model's agents + deterministic tools)
```

## ModelProfile (the registry record)

```text
   ModelProfile
   ├── id            "gemma-4-e2b"                       stable key
   ├── alias         "gemma-4-e2b"                       llama.cpp --alias served name
   ├── serve         { gguf, ctx, ngl, fits_jetson:true }  how to serve it
   ├── classes       [ { name:"standalone-fn-gen", bar:"HumanEval/MBPP", score, date },
   │                    { name:"single-file-repair", … } ]   MEASURED coverage only
   └── adaptation    { tools:[…], agents:[…], config:{…}, prompts:{…} }  per-model wiring
```

A profile lives in `.jaros-data/config/models/<id>.json`. `classes` is append-only by
measurement: a class entry exists only with recorded held-out evidence (Tenet 3). `adaptation`
names which existing tools/agents/config/prompt-variants to activate when this model is chosen —
this is what makes the harness "rewire itself" per model.

## Routing decision (Tenet 1: inert)

`route()` returns a `Decision`, never a side effect:

```text
   Decision{
     model_id:       "gemma-4-e2b",
     problem_class:  "standalone-fn-gen",
     confidence:     0.0..1.0,
     rationale:      "docstring+examples, single function — Gemma profile covers this"
   }
```

The clerk (the runtime) is what acts on it via `rewire`. When the classifier is unsure
(low confidence / unknown class), routing falls to the **deterministic default model** — the
strongest general roster member — so a task is always routed to *something capable*.

## Rewire (Tenet 1: deterministic clerk)

```text
   rewire(model_id):
     profile = registry.lookup_by_id(model_id)
     if serving.current() != profile.alias:          # idempotent: skip when already served
         jetson_swap(profile.serve)                  # edit serve.sh -m/--alias + restart gemma
     llm_client.point_at(profile.alias)
     activate(profile.adaptation)                    # tools/agents/config/prompts for this model
```

The Jetson swap is the only host-mutating step; it is guarded (cannot run an arbitrary command),
scoped to llama.cpp serving on the known device, and never escalates off-device (Tenet 2). A swap
failure is surfaced honestly (Tenet 3), never hidden.

## Profiling loop (REQ-4: earn the profiles)

```text
   for candidate in roster (best-first, Jetson-fitting only):
       serve(candidate)
       for class in held-out class-evals:
           score = run_eval(class)                  # honest, visible-spec, held-out
           if score clears the class bar:
               profile.classes += { class, bar, score, date }   # earned, with evidence
```

The roster is explored strongest-that-fits first. Routing quality is then a function of truthful
profiles; a misroute is a profiling/feature gap to close (the convergence loop, PRIME-001), never a
model limit to accept until proven across the roster.

## APPENDIX: Candidate Jetson-Fitting Models (best-first roster)

Explore in this order — strongest measured coding capability first, all within the Jetson Orin
Nano ~8 GB VRAM budget.  Profile JSONs are created ONLY after honest measurement (EXT-021 REQ-4
profiling loop).  Do NOT serve any of these candidates here; the profiling loop does that.

| Rank | model_id | Params | Est. VRAM (Q4_K_M) | Coding notes |
|------|----------|--------|--------------------|--------------|
| 1 | `qwen2.5-coder-3b-instruct` | 3B | ~2.0 GB | Strongest coding 3B available (2025); HumanEval 75%+ reported; explore first |
| 2 | `phi-4-mini-instruct` | 3.8B | ~2.5 GB | Microsoft Phi-4 mini; strong reasoning + code; fits Jetson with headroom |
| 3 | `deepseek-coder-v2-lite` | 2.4B active | ~1.6 GB | DeepSeek MoE lite; good coding; very small active-param footprint |
| 4 | `gemma-4-e2b` (baseline) | 2B | ~1.4 GB | Current default; measured classes: standalone-fn-gen + single-file-repair |

Profile notes:
- A model enters the roster's `_roster.json` `order` array when it is judged Jetson-fitting
  (`fits_jetson` check in `model_profiler.py`).
- A model's profile JSON (`.jaros-data/config/models/<id>.json`) is created + a class added
  ONLY after `profile_model` confirms it cleared the bar on held-out tasks.
- The roster is explored best-first; stop when coverage is sufficient for the routing classes
  needed (no need to profile every candidate if the first one covers the hard classes).

## REQ-5: the coverage tally, judgement/deterministic split, and roster progression

Selection is split cleanly across the two planes (the owner's refinement, 2026-06-28):

```text
   problem
     │
     ▼
   [model-router AGENT]  JUDGEMENT: what CLASS is this problem?   ← reasoning plane (a Decision)
     │  class = "multi-step-repo"
     ▼
   best_model_for(class)  DETERMINISTIC argmax over the class column ← execution plane (a tool)
     │
     ▼  model_id = the measured-best model for that class

   THE COVERAGE TALLY  (deterministic, persisted, kept filled in by the profiler)
   ┌────────────────────┬───────────────┬───────────────────┬──────────────────┐
   │ model \ class       │ standalone-fn │ single-file-repair│ multi-step-repo  │
   ├────────────────────┼───────────────┼───────────────────┼──────────────────┤
   │ gemma-4-e2b         │ 0.82 ✓        │ 0.18              │  —  (fails)       │
   │ qwen2.5-coder-3b    │  ? (profiling)│  ? (profiling)    │  ? (profiling)   │
   │ <next best model>   │  —            │  —                │  —               │
   └────────────────────┴───────────────┴───────────────────┴──────────────────┘
   best_model_for(class) = argmax down the class COLUMN (ties → roster order / default)
```

The class is a **judgement** (only a model can read "what kind of problem is this?"); the best model
for a known class is a **deterministic table lookup** (argmax over measured scores) — never a model
guess. Cells are filled ONLY by honest held-out measurement (Tenet 3); an empty cell means "not yet
measured," and the router falls back + records a new/unhandled class rather than fabricating coverage.

**Roster progression (keep going, indefinitely):**

```text
   profile current model across ALL known classes (fill its ROW)
        │  coverage captured?  (every known class measured for this model)
        ▼ yes
   admit the NEXT most capable Jetson-fitting model → profile it across all classes → repeat …
```

**New class → re-profile the whole roster (go back to prior models):**

```text
   new class discovered (new-class recording)  ──►  add a COLUMN to the tally
        │
        ▼  re-profile EVERY roster model against it (gemma, qwen, …) — fill the column
   the tally stays COMPLETE, so best_model_for(new_class) is always measured, not assumed
```

So the system never "finishes" a model and forgets it: a new class pulls every prior model back for
measurement, and the deterministic tally is the single source of truth for which model wins each class.
Each model's profile also carries the **evals** used to measure its classes (part of its adaptation),
so re-profiling is reproducible.

## Relationship to existing specs

- EXT-013/EXT-012 (behavioral solve + orchestrator) is the INNER solve the router wraps — unchanged
  except that its tools/agents/config/prompts become the *active model's adaptation set*.
- EXT-014 (model migration) generalizes from "the single selected model" to "the registry of
  Jetson-fitting models"; the founding Gemma profile is the EXT-014 anchor.
- The router/rewire run NATIVE on Jaros (inert Decision → gate → clerk → log → replay), satisfying
  Tenet 1 and Tenet 3 like every other grain.

## QWEN PROFILING VERDICT (2026-06-28 — first roster expansion)
qwen2.5-coder-3b profiled via the model-manager (served on demand, gemma restored after).
NOTE: the FIRST run was a HARNESS BUG (qwen_code dropped the import preamble -> fake 12% HumanEval,
impossible for qwen-coder; fixed 0ac0c2f). Corrected results:
- standalone-fn-gen: 11/12 = 92% HumanEval (gemma ~82%) -> EARNED; best_model_for = qwen.
  CAVEAT: HumanEval is contaminated for both models, so the +10% is NOT a clean capability delta —
  verify on MBPP (less contaminated) before over-claiming.
- multi-step-repo (8 hardest bigbar [fail] tasks; gemma 0 + pass@k 0 + decomp 0): qwen 0/8 -> REJECTED.
  The repo-eval path was VERIFIED sound (proper _file_context, _apply_func keeps imports, oracle-only
  scoring) so 0/8 is HONEST: this hard class is beyond qwen too.
HONEST SYNTHESIS: multi-model helps where models DIFFER (standalone-fn-gen -> route to qwen). The hard
repo class is CORRELATED failure (two general coding models fail it together) -> "diversity beats
resampling" needs DECORRELATED errors, which two similar general models don't give on this class. So
that class needs harness-DEEPENING (#26 maximal-help) or a genuinely DIFFERENT model, not just a 2nd
capable-but-similar one. The multi-model INFRASTRUCTURE works end-to-end (manager swap, profiler, honest
tally); the PAYOFF so far = per-class routing (qwen for standalone-fn-gen), not cracking the hard class.

## MBPP CONTAMINATION CHECK (2026-06-28) — qwen standalone-fn-gen edge is REAL
qwen2.5-coder-3b MBPP[:20] = 13/20 = 65% (qwen_code direct, correct fn-name from test asserts, no import
errors). Gemma baseline: direct ~25%, gated ~48%. VERDICT: qwen 65% DIRECT beats gemma 25% direct (~2.6x)
AND gemma's 48% gated -> the standalone-fn-gen advantage is GENUINE, not HumanEval contamination (MBPP is
the cleaner bar). So best_model_for(standalone-fn-gen) = qwen is a REAL, measured multi-model win — the
first clean payoff: routing standalone function-gen to qwen genuinely outperforms gemma. (The hard
multi-step-repo class remains uncracked by both — correlated failure, needs harness-deepening #26 or a
decorrelated model.) Honest scorecard: multi-model delivers per-class routing wins where models DIFFER;
qwen>>gemma on standalone-fn-gen is now confirmed on a clean benchmark.

## ROSTER ADMISSION POLICY — decorrelation + security (owner + external review, 2026-06-28)

THE DECORRELATION LAW (the law of this whole direction): multi-model buys capability ONLY to the extent
the models' FAILURES are decorrelated. Two competent-but-SIMILAR small models fail the same hard problems
(MEASURED: gemma-4-e2b AND qwen2.5-coder-3b both 0/8 on the hard multi-step-repo class — correlated
failure). So a new model EARNS a slot ONLY by covering, TEST-GATED + MEASURED, tasks/a class the current
roster CANNOT — not by being "a strong model." Optimize DECORRELATION-PER-SLOT, not model count: five
similar models ~= one model with extra latency.

JETSON SERIAL CONSTRAINT: the model-manager swaps ONE model onto :8000 at a time (~15-20s). Every slot has
a swap cost; roster size is bounded by this single-GPU reality -> each slot must cover a class the others
can't. Mitigation: batch-by-model routing (group queued tasks by routed model to amortize swaps).

ADMISSION GATE (a model joins ONLY when ALL hold):
1. DECORRELATED + MEASURED: solves, test-gated, tasks/a class the current roster FAILS (run a decorrelation
   probe: does it crack the hard tasks gemma+qwen both fail?). No measured decorrelation -> no slot.
2. JETSON-FITTING: ~8 GB budget (<= ~7-8B at Q4).
3. SECURITY-VETTED (below).
4. GENUINELY DIFFERENT (diversity not count): prefer a different TRAINING/strength — e.g. a REASONING-
   specialized model — over another general-purpose coder.

SECURITY VETTING (owner directive — "make sure they're safe security-wise"):
- THE TWO-PLANE GATE IS THE RUNTIME BACKSTOP: the model emits only inert Decisions; the deterministic clerk
  + test-gate validate every side effect. So even an adversarial / jailbroken / weakly-aligned model CANNOT
  escalate — it can only suggest, and the deterministic plane catches bad output. We therefore do NOT rely
  on a model's built-in safety (research: open-weight models incl. DeepSeek-R1 fail most prompt-injection
  tests + carry high offensive-cyber knowledge) — the ARCHITECTURE is the safety, not the model.
- PROVENANCE is the real vet: download OFFICIAL or reputable-verified GGUFs only (community conversions risk
  wrong tokenizer/chat-template, unsafe mirrors, incomplete shards, quant drift); verify checksums; confirm
  the open-weight LICENSE permits use.
- OFFLINE: runs entirely on the Jetson via llama.cpp, NO network egress (Tenet 2) -> no data-exfiltration
  concern from the weights; the hosted-API/app concerns about a vendor do NOT apply to local GGUF inference.

REVISED CANDIDATE ROSTER (decorrelation-first; researched 2026-06-28 — supersedes the all-coders APPENDIX):
| Candidate | Decorrelation rationale | Caveats |
|-----------|------------------------|---------|
| DeepSeek-R1-Distill-Qwen-7B / -Llama-8B | REASONING-specialized (RL-distilled chain-of-thought) — different training from general coders -> failures should DECORRELATE on the reasoning-heavy hard class | CoT = many tokens -> SLOW on serial Jetson (~minutes/problem); use OFFICIAL R1-Distill GGUF + checksum; weak alignment (gate handles it) |
| Phi-4-mini / Phi-4-reasoning (3.8B) | Microsoft reasoning-leaning; ~3.5GB Q4 (fits w/ headroom); better-documented provenance (more-trusted source) | only PARTIALLY decorrelated (still fairly general) |
| AVOID: Qwen3 / Qwen3.5 | SAME FAMILY as qwen2.5-coder -> CORRELATED failures, zero decorrelation gain | would be "one model with extra latency" |

SEQUENCE: #26 (maximal-help harness-deepening) is tried FIRST on the hard class — cheaper than a slot; if it
cracks the class, no new model is needed. Only if harness-deepening fails do we add a decorrelated reasoning
model, and ONLY after the admission gate (measured decorrelation + security vet) passes. Deep research +
security-vet happens at that point; this section is the STANDING policy.

## DECORRELATED-MODEL TRIAL VERDICT (R1-distill, 2026-06-29) — hard class is beyond Jetson-FITTING models
Owner-approved trial of a DECORRELATED reasoning model on the hard multi-step-repo class (gemma+qwen both 0/8; sampling/decomp/maximal-deepening all 0):
- R1-Distill-Qwen-7B (capable reasoner): LOADS (5.5GB) but OOMs DURING generation on the 7.3GB Jetson (unified memory; ngl-offload doesn't help). NOT USABLE here.
- R1-Distill-Qwen-1.5B (fits, 5.3GB headroom, works — r1_code clean in 26s): 0/6 cracked. Too weak.
HONEST VERDICT: neither the CAPABLE decorrelated reasoner (7B, doesn't fit) nor the FITTING one (1.5B, too weak) cracks the hard class -> the binding constraint is the Jetson's 7.3GB RAM, a measured DEVICE ceiling (not a denied model ceiling; Tenet 3). On this hardware the fitting models (<=~3-4B) are too weak + the capable ones (7B+) don't fit.
BANKED + REAL: the multi-model BREADTH wins stand — qwen beats gemma on standalone-fn-gen (92% HE / 65% MBPP clean vs 82%/25%), routed per-class; the floor rose; the full architecture (registry/router/rewire/tally/test-gate/adaptation) works end-to-end. The hard class is the one ceiling, gated by the device.
OPTIONS (owner decision, NOT auto-picked): (a) accept it's beyond Jetson-class hardware + bank breadth; (b) bigger-RAM device (fit a 7B+ reasoner); (c) CPU-offload the 7B (slow); (d) a different kind of harness-deepening. R1-distill admission gate NOT met -> 1.5B stays CANDIDATE (empty classes, not routed). Security vet (both): bartowski/HF reputable, MIT, offline, two-plane backstop.
