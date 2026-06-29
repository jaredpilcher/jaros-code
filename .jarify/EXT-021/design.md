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
