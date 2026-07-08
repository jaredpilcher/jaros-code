# Implementation Tasks — Compositional build (EXT-058)

Tasks are authored for the forward plan. They are executed (builder → architect) once EXT-058 becomes a
`NOW` roadmap item — AFTER the current single-class weak spots (creation timeouts + plan-JSON-parse mode)
are green, per the sequencing in `intent.md`.

### [TASK-1] Leaf-library registry seeded by the ADT oracle

Detailed: create a deterministic registry of atomic problem-classes keyed by class name, each pointing at a
build path and a reference oracle, seeded from the existing EXT-056 ADT references.

#### Steps
1. Add `harness/leaf_library.py` with a `LEAF_LIBRARY` mapping `name -> {build_path, reference_oracle}`, reusing `harness/adt_oracle.py`'s five references (`lru`, `priority-queue`, `ttl-store`, `fifo`, `ring-buffer`) — no duplication of reference code.
2. Add `lookup(name)` / `is_leaf(name)` deterministic accessors that never raise and make no model call.
3. Document the earned-membership rule (admit a class only on measured, held-out per-class passing).
4. Add offline tests for lookup, membership, and never-raises on unknown names.

#### Implements
- [REQ-1] Verified leaf-library registry (earned membership)

### [TASK-2] Prompt → DAG decomposer

Detailed: map a build prompt to an acyclic graph of leaf sub-specs + connector edges, deterministic-first.

#### Steps
1. Add `decompose_to_dag(prompt)` to a new `harness/compositional_build.py`, producing `{nodes, edges}`.
2. Tag each node with a matched library class (deterministic keyword/structure signals) or `NOVEL`; the model-assisted glue choice is an inert `Decision`.
3. Degrade a single-leaf prompt to a one-node DAG (strict superset of today's single build).
4. Validate the DAG acyclic (reuse `validate_plan`'s cycle check) before returning.
5. Offline tests: multi-leaf decomposition, single-leaf degrade, cycle rejection.

#### Implements
- [REQ-2] Prompt → DAG decomposer

### [TASK-3] Composer + connectors + bottom-up verification

Detailed: build/retrieve+verify each leaf, then deterministically wire and verify the whole.

#### Steps
1. In `harness/compositional_build.py`, add `compose(dag, root, *, llm)` — build/retrieve each leaf, verify it against its oracle, then synthesize connectors + entrypoint reusing `_repair_plan_entrypoint_multi` (REQ-32/TASK-47).
2. Add deterministic inter-leaf contract checks; a broken contract fails composition with a localized witness.
3. Compose system-level acceptance from the leaf oracles by UNION (0-false-done preserved by construction).
4. Route all host writes through the existing gated `code.write_file` Decision (Tenet 1); confirm replayability.
5. Offline + on-Jetson tests: a two-leaf composition builds, verifies bottom-up, and ships.

#### Implements
- [REQ-3] Deterministic composer + connectors + bottom-up verification

### [TASK-4] Composition suite + per-composition measurement

Detailed: add a held-out composition tier to the creation suite and report per-composition accept-rates.

#### Steps
1. Add a `COMPOSITION_SLICE` to `harness/system_suite.py` (e.g. rate-limited TTL cache = rate-limiter + ttl-store), each with independent `checks` (no oracle leak).
2. Extend `.jaros-data/scoreboard_run.py` to report composition accept-rate per composition-class alongside atomic classes.
3. Run the tier on the Jetson; record which compositions hold once their leaves are individually solid.
4. Update the empirical leaf taxonomy from the results.

#### Implements
- [REQ-4] Composition suite + honest per-composition measurement
