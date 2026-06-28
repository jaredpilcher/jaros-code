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

## Relationship to existing specs

- EXT-013/EXT-012 (behavioral solve + orchestrator) is the INNER solve the router wraps — unchanged
  except that its tools/agents/config/prompts become the *active model's adaptation set*.
- EXT-014 (model migration) generalizes from "the single selected model" to "the registry of
  Jetson-fitting models"; the founding Gemma profile is the EXT-014 anchor.
- The router/rewire run NATIVE on Jaros (inert Decision → gate → clerk → log → replay), satisfying
  Tenet 1 and Tenet 3 like every other grain.
