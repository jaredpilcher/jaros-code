# Intent

**EXT-058 — Compositional build: a library of verified atomic classes composed into complex systems.**

This spec exists to give jaros-code a *structural* path to large, real, multi-component systems that the
current from-scratch generator cannot reach reliably. Rather than generate a big system in one pass, the
product grows a **library of small, atomic problem-CLASSES** it can each build and verify in isolation —
an LRU cache, a rate limiter, a TTL store, a parser, a state machine, a datastore — **each backed by its
own reference oracle**, and then **composes them as a DAG** into larger systems: a big prompt is decomposed
into a DAG of known leaf-classes plus the novel glue between them, each leaf is built (or retrieved from the
library) and **independently verified**, and the whole is wired together and verified bottom-up.

Two things are first-class and are the reason this spec is worth having:

1. **The verified leaf-library.** Every class the per-class scoreboard shows *solidly* passing is promoted
   into a reusable, oracle-backed building block (the ADT differential oracle in EXT-056 — five canonical
   data-structure leaves — is the seed). A large project then *reuses verified pieces instead of re-deriving
   them* — a flywheel of capability, not only of training data.
2. **The deterministic composer + connectors.** MEASURED 2026-07-07 (per-class creation scoreboard): the
   build failures are **compositional** — a missing entrypoint that ties modules together; the small model
   can write the pieces but stumbles on the wiring — while *modifying* an already-composed system is markedly
   more robust. So the connectors and the contracts between leaves are **deterministic, checkable grains**,
   not left to the model.

**How it converges toward the Prime Directive.** This is the direct implementation of PRIME-001 intent (h)
("BUILD LARGE SYSTEMS BY COMPOSITION OF VERIFIED CLASSES"). It advances the central CAPABILITY bar — building
the real, multi-component systems the directive demands — and it is the build-level twin of PRIME-001's
agent-swarm composition principle (the swarm composes tiny *agent judgments*; this composes verified *system
classes*). The leaf taxonomy is **grown empirically from measurement** (the scoreboard names which classes
recur as independently-verifiable units), never designed top-down, honoring Tenet 3. Not every problem
divides cleanly — a leaf may be a novel sub-problem the model must still solve fresh — so the DAG *organizes*
the work, it does not eliminate irreducible reasoning. This is the concrete shape of the difficulty ratchet:
master the atomic classes, then ratchet to compositions of them, then to larger DAGs.
