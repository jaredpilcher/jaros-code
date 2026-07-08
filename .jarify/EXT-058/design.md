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

## Graph-DSL refinement — the DAG as an explicit LANGUAGE (owner idea, 2026-07-07)

The owner sharpened this direction: make the DAG a **graph DSL** — an explicit, parameterized language whose
NODES are verified leaf-classes and whose EDGES are typed connectors — so the pipeline splits at a clean,
checkable seam: **NL → DSL** (reasoning) and **DSL → system** (deterministic construction). The DSL is the
interface; it is where the reasoning is *reduced* to a compact, validatable artifact (this is PRIME-001's
"reduction is a first-class grain type", taken to the architecture level). Modification becomes a **declarative
diff**: describe the desired system as a DSL graph, diff it against the current graph, and deterministically apply
only the delta — far more deterministic than diffing raw code.

**Prior art (researched 2026-07-07 — the shape is validated, the small-model corner is the gap):** LLM→IR/DSL→
deterministic codegen is an active pattern — LLMLift (UC Berkeley, verified lifting: model emits an IR, verifies,
rewrites to code), ComplexVCoder (spec → hierarchical JSON graph IR of modules/ports/connectivity → synthesis),
and Anka (a DSL built for reliable LLM codegen). The reasoning/deterministic split is exactly program **sketching**
(Solar-Lezama: model writes structure with holes, a deterministic synthesizer fills them). The modification-by-diff
story is the industrial **Infrastructure-as-Code** pattern (Terraform declare-desired-state → `plan` diff → `apply`
delta; "drift" = the graph diff). What is genuinely under-explored is this at **whole-complex-system scale with an
extremely small LOCAL model + a VERIFIED node library** — jaros-code's exact niche.

**Tenet-2 CONSTRAINT (binds this refinement).** The DSL must be emitted by the **small local model**, NOT a frontier
model — the DSL's whole value is that a constrained graph (grammar-constrained decoding, tiny target vocabulary,
deterministic node/edge validation) is FAR easier for a 2B to emit correctly than raw code, so it *reduces* the
reasoning a small model needs. Using a cloud/frontier model as the product's orchestrator is forbidden (Tenet 2) and
would defeat the thesis. A frontier model may serve ONLY as a temporary, labeled VALIDATION SCAFFOLD to de-risk the
DSL→system backend in isolation (like gold labels for a grader), then be removed — never in the shipped product.

**Limit of the bet (honest):** "most systems reduce to a DAG of classic problems + connectors" holds for
composition/glue (pipelines, CRUD, orchestration, wiring — where our measured build failures actually were), but NOT
for irreducible novel algorithmic/domain logic. The DSL organizes and composes the KNOWN deterministically; a leaf
with novel logic still needs reasoning — so the DSL needs a **custom-node escape hatch**, and its power scales with
how rich + verified the node vocabulary is. **First experiment (when greenlit):** a minimal graph DSL over the
existing verified leaves (5 ADT oracles + CLI classes), grammar-constrain the 2B to emit only valid DSL, build
deterministically, and measure the compositional-task lift vs. free-form generation.

## Honesty & safety

- No oracle leak: leaf references and connector contracts derive only from the VISIBLE spec, never hidden tests.
- 0-false-done preserved: system-level acceptance composes leaf oracles by union (can only flip done True→False).
- The taxonomy grows only on measured, held-out passing — never by declaring a class solved.
