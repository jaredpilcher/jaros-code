---
id: EXT-058
title: Compositional build — verified leaf-library composed into complex systems
status: partial
priority: high
implementation: []
---

Implements PRIME-001 intent **(h)** ("BUILD LARGE SYSTEMS BY COMPOSITION OF VERIFIED CLASSES"). The
capability is planned; requirements below are authored for alignment and become tasks when this spec is
promoted to a `NOW` roadmap item. Sequencing: the current single-class weak spots (creation timeouts, the
plan-JSON-parse mode) are closed FIRST; then composition is built and measured.

### [REQ-1] Verified leaf-library registry (earned membership)

A registry of atomic problem-classes, each pairing a canonical builder path with a reference oracle, seeded
by the EXT-056 ADT differential oracle's five classes (`lru`, `priority-queue`, `ttl-store`, `fifo`,
`ring-buffer`). Membership is EARNED from measurement — a class is admitted only when the per-class scoreboard
shows it *solidly* passing (held-out), never by top-down declaration. Pure data + deterministic lookup; no
model call to query the registry.

#### Acceptance Criteria
- [ ] A `leaf_library` registry maps a class name → `{build_path, reference_oracle}` and is queryable deterministically.
- [ ] The five EXT-056 ADT classes are registered as the initial leaves, reusing their existing references (no duplication).
- [ ] Admission is gated on measured, held-out per-class passing (documented rule); adding a leaf never weakens 0-false-done.
- [ ] Registry lookup never raises and makes no model call.

### [REQ-2] Prompt → DAG decomposer

Map a build prompt to a DAG: a set of leaf sub-specs (each tagged with a matched library class, or `NOVEL`
when none fits) plus the connector edges (which leaf depends on / uses which). Deterministic classification
where structure/keywords allow; the model is used only for genuinely novel glue, and its choice is an inert
`Decision`.

#### Acceptance Criteria
- [ ] `decompose_to_dag(prompt) -> {nodes:[leaf sub-specs], edges:[connectors]}` produces an acyclic graph.
- [ ] Each node is tagged with a matched library class or `NOVEL`; matching uses deterministic signals first.
- [ ] A single-leaf prompt degrades to a one-node DAG (composition is a strict superset of today's single build).
- [ ] The DAG is validated acyclic before composition (reusing `validate_plan`'s cycle discipline).

### [REQ-3] Deterministic composer + connectors + bottom-up verification

Build or retrieve each leaf, verify it independently against its oracle, then wire the leaves: synthesize the
connector code and the entrypoint (reusing the EXT-036 REQ-32/TASK-47 entrypoint synthesis as the primitive),
and check the CONTRACTS between leaves deterministically. Verify bottom-up: each leaf passes its oracle, then
the composed whole passes a system-level acceptance derived from the visible prompt. All host writes go through
the existing gated `code.write_file` Decision (Tenet 1). No oracle leak.

#### Acceptance Criteria
- [ ] Each leaf is built/retrieved and independently verified against its oracle before wiring.
- [ ] Connector/entrypoint synthesis is deterministic (reuses REQ-32 root-import entrypoint repair); wiring is not left to the model.
- [ ] Inter-leaf contracts are checked deterministically; a broken contract fails composition with a localized witness.
- [ ] System-level acceptance composes leaf oracles by UNION (can only flip done True→False — 0-false-done preserved).
- [ ] All writes flow through the Jaros gate; the composed build is hash-chain logged and replayable.

### [REQ-4] Composition suite + honest per-composition measurement

A held-out instrument: a creation-suite tier of composition tasks (two or more already-passing leaves wired
into one system, e.g. a rate-limited TTL cache), graded end-to-end by independent oracles. Measures whether
composition holds when the leaves are individually solid, per-composition, no leak.

#### Acceptance Criteria
- [ ] A composition tier is added to the creation suite with independent per-task oracles (no oracle leak).
- [ ] The scoreboard reports composition accept-rate per composition-class, alongside the atomic per-class rates.
- [ ] Any measured lift is proven on HELD-OUT composition tasks the mechanism was not tuned on (Tenet 3).
- [ ] The empirical leaf taxonomy is updated from these results (which classes recur as verifiable units).

### [REQ-5] Verified mini-SQL-engine leaf (sql-query-engine)

A second earned leaf-library member (REQ-1's registry): a minimal in-memory SQL-like query engine
(`CREATE TABLE`/`INSERT INTO`/`SELECT * FROM ... WHERE`) covering the held-out `sql-mini-query-cli` creation
class. MEASURED: this class scores 0/3 for gemma both as a multi-module build (incoherent module wiring, a
runtime crash) and as a forced single-file build (the small model bugs the grammar parsing) -- genuinely
parse-hard for the 2B, the same class of gap the `ttl-store` leaf (TASK-5) closed. Admission follows REQ-1's
earned-membership rule: the reference implementation independently passed all 3 of the held-out task's
checks before being promoted into the library.

#### Acceptance Criteria
- [ ] A verified `sql-query-engine` leaf template is registered in `LEAF_LIBRARY`, authored ONLY from the
      VISIBLE grammar contract (never any task's hidden checks -- Tenet 3, no oracle leak).
- [ ] The leaf passes ALL of `sql-mini-query-cli`'s independent, oracle-authored checks.
- [ ] `leaf_for_spec` CONSERVATIVELY classifies a genuine mini-SQL-engine spec to this leaf, keyed on
      strong, co-occurring, distinctive signals -- never a single loose keyword.
- [ ] `leaf_for_spec` does NOT over-trigger: a `ttl-store` spec and a plain `kv-store` spec still resolve to
      their own correct leaf/`None`, never the SQL leaf.
- [ ] The existing `build_system` leaf-repair adopt path picks up the new leaf via `leaf_for_spec` with no
      change required to `harness/system_builder.py` (a strict superset, byte-identical behavior for every
      other class).
