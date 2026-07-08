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

### [TASK-5] Governed graph-DSL machinery + first verified leaf (ttl-store) — port the PROVEN prototype

Detailed: promote the throwaway go/no-go prototype (`.jaros-data/dsl_probe.py` + `.jaros-data/dsl_gate2.py`,
both gates PASSED 2026-07-07) into a governed harness module. This is the first REAL implementation of the
graph-DSL (PRIME-001 (h.1)): deterministic DSL parse/validate/signature + a verified leaf-library + a
deterministic `dsl_to_system` that emits a verified leaf's known-good code for a known-class node. Start
with the ttl-store leaf (the one Gate 2 proved beats free-form 3/3 vs 0/3 on the hard TTL task). SCOPE: this
task is the DETERMINISTIC DSL→system half for single-leaf known classes ONLY (NL→DSL and multi-leaf
composition are later tasks). Honesty: the leaf template is authored from the VISIBLE class contract, never
the task's checks (no oracle leak) — exactly like the ADT oracle reference models.

#### Steps
1. Add `harness/graph_dsl.py` porting the prototype's pure-stdlib, never-raises functions: `parse_dsl(text)`
   (via the existing `system_builder._extract_json`), `validate_dsl(graph)` (nodes have id+known class from a
   VOCAB, edges reference listed node ids, no unknown class), `signature(graph)` (structural: sorted
   node-class multiset + class→class edges, ignoring ids/params), and `equiv(g1,g2)`.
2. Add a `LEAF_LIBRARY` mapping class → a VERIFIED single-file CLI template; seed it with the `ttl-store`
   template from `.jaros-data/dsl_gate2.py` (`kv-store` with TTL maps to `ttl-store`). Each template is
   authored from the class contract, NOT from any task's checks.
3. Add `dsl_to_system(graph, root)` — for a single-node graph whose class is a library leaf, write the
   verified template to `root/main.py` and return True; return False otherwise (multi-node/unknown-class ->
   later composer). Route the host write through the Jaros `code.write_file` Decision path (Tenet 1) if a
   `runtime`/`root` is threaded, else the internal-scratch raw write is acceptable for the eval path (mirror
   `system_builder`'s existing convention).
4. Add `tests/test_ext058_graph_dsl.py`: parse/validate/signature/equiv unit tests (incl. unknown-class
   rejection, id/param-invariance, cycle-empty-roots), the ttl-store template PASSES the `kv-store-ttl-cli`
   task's independent checks (reuse `system_suite._run_single_check`), and `dsl_to_system` emits for a
   single ttl-store node and declines a multi-node graph. Offline, no model call.
5. Run `python -m pytest tests/test_ext058_graph_dsl.py -q` (green) + confirm no regression in the broader
   `tests/test_ext056*.py` / `tests/test_ext036*.py` slices touched.

#### Implements
- [REQ-1] Verified leaf-library registry (earned membership) — first governed slice
- [REQ-3] Deterministic composer + connectors — the single-leaf DSL→system deterministic path

### [TASK-6] Wire the verified leaf as a deterministic REPAIR candidate into `build_system`

Detailed: make the verified ttl-store leaf (TASK-5, `harness/graph_dsl.py`) actually FIRE in the real build
flow so the reconfirmed weak `kv-store-ttl` class (free-form 0/3 on the trustworthy baseline) can pass.
This is the single-leaf DSL→system path made live — NOT composition (still gated later). It is ADDITIVE and
HONEST by construction: the leaf template only fires AFTER a free-form build FAILS acceptance, and it must
pass the SAME independent `_minimum_acceptance` checks as any free-form build to win — so it competes on the
real gate (0-false-done preserved; the template can never make a broken build report done). The spec→leaf
classification must be GENERIC (a ttl-store contract fingerprint, e.g. reuse `adt_oracle`'s `ttl-store`
signals on the spec text), never benchmark-item detection.

#### Steps
1. Add a deterministic `harness/graph_dsl.py` helper `leaf_for_spec(spec) -> str | None` that returns a
   verified leaf class id (currently only `ttl-store`) when the VISIBLE spec text fingerprints that class's
   contract (reuse `adt_oracle` classification signals on the spec; never match on any hidden test/benchmark
   id), else `None`. Never raises, no model call.
2. In `harness/system_builder.py` `build_system`, AFTER the existing free-form build + `_minimum_acceptance`
   (and after the existing iterative replan-repair) — ONLY when the build is still not `done` — call
   `leaf_for_spec(spec)`; if it returns a library leaf, emit that leaf's verified template via
   `graph_dsl.dsl_to_system` (single-node graph) into a fresh candidate dir, re-run `_minimum_acceptance`
   on it, and adopt the leaf result ONLY if it now passes (done=True). Route the write through the same
   gated `code.write_file` path `build_system` already uses (Tenet 1). Record on the result which path won
   (`build_path: "free-form" | "leaf:ttl-store"`) for honest reporting.
3. Keep it a strict superset: a spec with no matching leaf, or a free-form build that already passed, is
   byte-identical to today (the leaf branch is unreachable). No behavior change for non-leaf builds.
4. Add `tests/test_ext058_leaf_repair.py` (offline, no model call): (a) `leaf_for_spec` returns `ttl-store`
   for the kv-store-ttl contract text and `None` for a sum-cli/todo spec; (b) a stubbed `llm` that emits a
   BROKEN ttl build drives `build_system` down the leaf-repair branch and the final result is `done=True`
   with `build_path == "leaf:ttl-store"` and passes the kv-store-ttl checks; (c) a stubbed `llm` whose
   free-form build already passes never enters the leaf branch (`build_path == "free-form"`).
5. Run `python -m pytest tests/test_ext058_leaf_repair.py tests/test_ext058_graph_dsl.py -q` green, then the
   `tests/test_ext036*.py` + `tests/test_ext056*.py` regression slices green (no regression on the critical
   build path). Do NOT run any on-Jetson build (the live A/B is queued separately, after the baseline).

#### Implements
- [REQ-3] Deterministic composer + connectors — the single-leaf DSL→system path made LIVE in `build_system`
