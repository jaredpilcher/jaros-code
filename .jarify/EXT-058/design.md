# Design — Compositional build (EXT-058)

## Overview

Three cooperating pieces turn "build a large system" into "compose verified leaves":

1. **Leaf-library** — a registry of atomic problem-classes, each with a canonical builder path AND a
   reference oracle. Seeded by the ADT differential oracle (EXT-056): `lru`, `priority-queue`, `ttl-store`,
   `fifo`, `ring-buffer`. Membership is EARNED: a class enters the library only when the per-class scoreboard
   shows it *solidly* passing (grown empirically, never declared).
2. **Decomposer** — maps a build prompt to a **DAG**: a set of leaf-class sub-specs (each tagged with a
   known library class where one fits, else marked NOVEL) plus the connector edges (which leaf uses which).
   Deterministic where possible (structure/keyword classification), model-assisted only for the genuinely
   novel glue.
3. **Composer + connectors** — builds/retrieves each leaf, verifies it independently against its oracle,
   then wires them: synthesizes the connector code and entrypoint, and checks the CONTRACTS between leaves
   deterministically. The wiring is the measured failure surface (2026-07-07), so it is a deterministic,
   checkable grain — reusing the entrypoint-synthesis plan-repair (EXT-036 REQ-32/TASK-47) as its primitive.

Verification is **bottom-up**: each leaf passes its own oracle, then the composed whole passes a
system-level acceptance derived from the prompt.

## Flow

```text
                 build prompt (a large / multi-component system)
                                   │
                                   ▼
                         ┌───────────────────┐
                         │    DECOMPOSER      │  prompt → DAG
                         │  (deterministic +  │
                         │   model for glue)  │
                         └─────────┬─────────┘
                                   ▼
              DAG of leaf sub-specs + connector edges
        ┌──────────────┬──────────────┬───────────────┐
        ▼              ▼              ▼                ▼
   ┌─────────┐   ┌──────────┐   ┌──────────┐    ┌───────────┐
   │ leaf A  │   │  leaf B  │   │  leaf C  │    │ NOVEL leaf │
   │(library:│   │(library: │   │(library: │    │(build fresh│
   │ ttl-str)│   │rate-limit)│  │  fifo)   │    │  + oracle) │
   └────┬────┘   └────┬─────┘   └────┬─────┘    └─────┬─────┘
        │ oracle✓     │ oracle✓      │ oracle✓        │ verify✓
        └──────────────┴──────┬───────┴────────────────┘
                              ▼
                    ┌───────────────────┐
                    │  COMPOSER +        │  wire leaves, synthesize
                    │  CONNECTORS        │  entrypoint, check contracts
                    │ (deterministic)    │  (reuses REQ-32 entrypoint repair)
                    └─────────┬─────────┘
                              ▼
                 system-level acceptance (bottom-up verified)
                              ▼
                     composed system (shipped / done)
```

## Placement (two-plane discipline)

- **Deterministic plane (tools):** the leaf-library registry + oracle lookup; the DAG structure, topological
  order, and connector/contract checks; the entrypoint/wiring synthesis; bottom-up verification. These are
  counting/searching/structure grains — exactly the plane the model is weak at (measured: wiring failures).
- **Reasoning plane (agents):** classify a sub-spec to a leaf class or NOVEL; generate a novel leaf's code
  and the genuinely novel glue logic. Each is a narrow judgment emitting an inert `Decision`.

Every host write flows through the existing Jaros `code.write_file` Decision path (Tenet 1), reusing
`build_system`'s gated write chokepoint — no new raw-write path.

## Relationship to existing specs

- **EXT-056** (ADT differential oracle) — the seed of the leaf-library; its 5 references are the first leaves.
- **EXT-036** (build/modify from a sentence) — the composer reuses `build_system`'s plan/validate/repair and
  the REQ-32/TASK-47 entrypoint synthesis as the connector primitive; the per-class scoreboard (creation +
  modification suites) is the empirical taxonomy source and the honest measurement of composition lift.
- The composition suite (a new creation-suite tier: two+ already-passing leaves wired into one system) is the
  held-out instrument that proves composition works when the leaves are individually solid.

## Honesty & safety

- No oracle leak: leaf references and connector contracts derive only from the VISIBLE spec, never hidden tests.
- 0-false-done preserved: system-level acceptance composes leaf oracles by union (can only flip done True→False).
- The taxonomy grows only on measured, held-out passing — never by declaring a class solved.
