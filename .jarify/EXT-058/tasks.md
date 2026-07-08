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

### [TASK-7] Fix leaf-repair false-done: ship EXACTLY the leaf, not the stale free-form files

Detailed: closes a MEASURED Tenet-3 false-done in the TASK-6 leaf-repair adopt block. When leaf-repair
adopts a verified leaf, it currently writes `main.py` (the leaf) into `root` and flips `done=True`, but
leaves the free-form build's OTHER already-written files (e.g. `cli.py`, `store.py`, `data_manager.py`) on
disk in `root`, and leaves the returned `plan` as the free-form plan (whose `entrypoint` names a free-form
module, not `main.py`). Acceptance was validated against a clean temp dir holding only the leaf, so
`done=True` — but the SHIPPED `root` still runs the buggy free-form entrypoint via the free-form `plan`.
The leaf itself is correct in isolation; the adopt step just failed to make the shipped artifact match what
was graded. Fix makes `root` contain exactly the leaf, points `plan` at it, and re-grades on `root` itself
(not a throwaway dir) before committing — with a fail-safe rollback to the untouched free-form result on
any error or re-verification failure, so 0-false-done is preserved by construction.

#### Steps
1. In `harness/system_builder.py`'s leaf-repair adopt block (`# #EXT-058-REQ-3`, inside `build_system`,
   currently ~lines 2742-2764), after `_jailed_write(root, "main.py", leaf_code, runtime)` succeeds, remove
   every pre-existing free-form `.py` module file from `root` except `main.py` (the module names come from
   the pre-adopt `built` dict) via a jailed delete (add a `_jailed_delete(root, name)` helper mirroring
   `_jailed_write`'s `path_jail` discipline — never deletes outside `root`, never raises).
2. Replace the returned `plan` with a minimal leaf plan `{"entrypoint": "main.py", "modules": [{"name":
   "main.py"}]}` once the leaf is adopted, so downstream entrypoint resolution (`_minimum_entry_filename`,
   `system_suite._resolve_entry`) and any later task/acceptance run against `root` use the leaf, not the
   stale free-form entrypoint.
3. Belt-and-suspenders: after making `root` the leaf (main.py written, stale files removed), re-run the SAME
   `leaf_checks` (`_run_check`) against `root` itself — not just the throwaway `cand_root` — before
   committing. If they still pass, commit `built`/`unmet`/`plan`/`build_path`/`quality` to the leaf result
   (byte-identical set of assignments as today, just gated on the stronger re-verification). If they do NOT
   pass, or the jailed delete reports any error, roll back: rewrite every pre-adopt free-form module's exact
   original content back into `root` (delete the leaf's `main.py` too if the free-form build never had one),
   and leave `built`/`plan`/`unmet`/`done` exactly as the free-form result (no adopt) — the existing outer
   `try/except Exception: pass` continues to guard any unexpected exception the same way.
4. Add `tests/test_ext058_leaf_repair_ships_leaf.py` (offline, stubbed `llm`, no model call): (a) a stubbed
   free-form build that writes multiple buggy modules (e.g. `cli.py` + `store.py`) and fails acceptance, then
   leaf-adopts — assert `root` on disk contains ONLY `main.py`, the returned `plan["entrypoint"] ==
   "main.py"`, the independent checks re-run against the shipped `root` PASS, and `done=True`; (b) the
   fail-safe case: force the belt-and-suspenders re-verification against `root` to fail (e.g. monkeypatch/stub
   so the leaf's checks pass in `cand_root` but not in `root`) and assert the free-form files remain on disk,
   `built`/`plan` are unchanged, and `done=False`.
5. Run `python -m pytest tests/test_ext058_leaf_repair.py tests/test_ext058_graph_dsl.py
   tests/test_ext058_leaf_repair_ships_leaf.py -q` green. Do NOT run `tests/test_ext036_system_builder.py`,
   broad `test_ext036*`/`test_ext056*` globs, or any `-k` sweep (triggers a live Jetson model-swap).

#### Implements
- [REQ-3] Deterministic composer + connectors — closes the false-done in the leaf-repair adopt path

### [TASK-8] Verified mini-SQL-engine leaf (sql-query-engine) — second earned leaf-library member

Detailed: adds a second verified leaf, `sql-query-engine`, to `harness/graph_dsl.py`'s `LEAF_LIBRARY` (the
same proven mechanism TASK-5 used for `ttl-store`), so the existing leaf-repair adopt path (TASK-6/TASK-7,
already generic over `leaf_for_spec`/`dsl_to_system` — no `system_builder.py` change needed) can ship a
working system for the held-out `sql-mini-query-cli` creation class. MEASURED this session: the class
scores 0/3 for gemma both as a multi-module build (incoherent module wiring, a runtime crash) and as a
forced single-file build (the small model bugs the grammar parsing) — genuinely parse-hard, warranting a
verified building-block leaf (not thin evidence). The reference leaf body (below) independently passed all
3 of the task's checks offline this session before being promoted here.

#### Steps
1. Add `SQL_MINI_LEAF` to `harness/graph_dsl.py`: a cleaned-up, PEP8, self-contained single `main.py`
   implementing an in-memory SQL-like engine (`CREATE TABLE <name> (<cols>)` -> `ok`; `INSERT INTO <name>
   VALUES (<vals>)` -> `ok`; `SELECT * FROM <name> WHERE <col>=<value>` -> one comma-joined line per exact
   match, insertion order, nothing on no match), authored ONLY from the VISIBLE grammar contract (never any
   task's hidden checks — Tenet 3, no oracle leak).
2. Register it in `LEAF_LIBRARY` under a new class key, `"sql-query-engine"`, and add that key to `VOCAB`.
3. Extend `leaf_for_spec(spec)` with a new, CONSERVATIVE, independent fingerprint (`_is_sql_mini_spec`) that
   requires STRONG, distinctive signals to CO-OCCUR (`create table` AND `select` AND (`insert` or `query
   engine`)) — never a single loose keyword alone — so it fires ONLY for genuine in-memory-SQL-engine specs
   and still returns the correct existing leaf (or `None`) for `ttl-store`, `kv-store`, and every other
   class (no over-trigger).
4. Confirm (no code change) that `build_system`'s existing leaf-repair adopt path (`# #EXT-058-REQ-3` in
   `harness/system_builder.py`) picks up the new leaf via `leaf_for_spec`/`dsl_to_system` unchanged — both
   are already class-generic, so this is a strict superset with no modification to that file.
5. Add `tests/test_ext058_sql_leaf.py` (offline, no model call): the emitted SQL leaf passes ALL 3 of
   `sql-mini-query-cli`'s independent checks (reusing `harness.system_suite._run_single_check`);
   `leaf_for_spec` returns `"sql-query-engine"` for the held-out `sql-mini-query-cli` spec, and explicitly
   does NOT return it for a `ttl-store` spec or a plain `kv-store` spec (no-over-trigger negatives);
   `dsl_to_system` emits the leaf for a single `sql-query-engine` node.
6. Run `python -m pytest tests/test_ext058_sql_leaf.py tests/test_ext058_graph_dsl.py -q` green. Do NOT run
   the broader suite or any on-Jetson/live test (host load must stay light — a Jetson measurement runs
   concurrently).

#### Implements
- [REQ-5] Verified mini-SQL-engine leaf (sql-query-engine)

### [TASK-9] Leaf-as-differential-oracle: close the false-done bypass for leaf-covered classes

Detailed: closes a MEASURED false-done (on-Jetson, 2/2 samples) that lets a broken free-form build ship as
`done=True` for a leaf-covered class. For `sql-mini-query-cli`, the deterministic-minimum + ADT-oracle
acceptance floor doesn't cover the stdin-line SQL protocol (`select` is not a minimum command verb and the
class has no ADT reference), so `done` can ride on a build that never crashes but silently mis-implements
`SELECT` — and the pre-existing leaf-repair adopt block (TASK-6/TASK-7) only fired when `not done`, so the
verified `sql-query-engine` leaf (TASK-8) never got a chance to fire. A verified leaf is a spec-faithful
reference for its class, so it doubles as a DIFFERENTIAL ORACLE: drive the shipped free-form build and the
leaf on the SAME deterministic seeded stdin and compare outputs, and adopt the leaf on divergence even when
`done=True` already.

#### Steps
1. Add `seeded_driver_input(leaf_cls) -> str | None` to `harness/graph_dsl.py`: a deterministic, never-raises
   exercise-input generator, implemented for `"sql-query-engine"` (a fixed stdin string: a CREATE TABLE,
   several INSERTs, a SELECT with a matching WHERE, a SELECT with NO match — must print nothing — and a
   SELECT matching multiple rows with insertion order preserved). Returns `None` for every other class
   (conservative skip, no behavior change for classes without a seeded input yet). Authored ONLY from the
   leaf's own VISIBLE grammar contract, never from any task's hidden `checks` — no oracle leak.
2. In `harness/system_builder.py`, add `_run_with_stdin(cwd, entry, stdin_text)` (reusing the existing
   `run_sandboxed`/`_run_acceptance_cmd` sandboxed-execution conventions: scrubbed env, resource caps,
   timeout + tree-kill, DENY_ALL egress — no new execution path) and `_leaf_differential_diverges(root, mods,
   plan, leaf_cls, runtime)`, which runs the free-form build's resolved entrypoint (`_minimum_entry_filename`)
   and the leaf (emitted to a throwaway temp dir via `graph_dsl.dsl_to_system`, never touching `root`) on the
   SAME seeded stdin and reports whether their stdout diverges, or the free-form run errors.
3. In the leaf-repair block (`# #EXT-058-REQ-3`, inside `build_system`), resolve `leaf_cls` UNCONDITIONALLY
   (once, ahead of both triggers) and compute `leaf_diverges` (ONLY when the build already has no unmet
   check, so it never duplicates the pre-existing `unmet` trigger's work). Trigger the SAME EXISTING
   ship-clean adopt path (TASK-7's atomicity/rollback logic, REUSED UNCHANGED — no reintroduced ship-stale-
   files false-done) when EITHER `unmet` (existing trigger) OR `leaf_diverges` (new trigger) is true.
4. Never raise anywhere in the new helpers; any differential error (missing entry, run failure, exception) is
   treated conservatively as "no divergence detected" and falls back to the pre-existing behavior — the
   differential can never itself break or worsen a build.
5. Add `tests/test_ext058_leaf_differential.py` (offline, no model call): (a) a stub free-form build that
   DIVERGES from the leaf on the seeded input (botches SELECT) is adopted (`build_path ==
   "leaf:sql-query-engine"`) EVEN THOUGH the deterministic-minimum floor alone already reports `done=True`;
   (b) a stub free-form build that MATCHES the leaf on the seeded input is left unchanged (`build_path ==
   "free-form"`); (c) over-trigger guard: a non-leaf-class spec (a plain calculator) never runs the
   differential; (d) honesty: the differential's source never references the task registry
   (`system_suite`/`FIRST_SLICE`/`HARDER_SLICE`/`CreationTask`), and a differential-triggered adopt still
   succeeds functionally even with `harness.system_suite` poisoned/unimportable during the call.
6. Run `python -m pytest tests/test_ext058_leaf_differential.py tests/test_ext058_leaf_repair.py
   tests/test_ext058_leaf_repair_ships_leaf.py tests/test_ext058_sql_leaf.py tests/test_ext058_graph_dsl.py
   -q` green. Do NOT run the broader suite or any on-Jetson/live test (host load must stay light).

#### Implements
- [REQ-6] Leaf-as-differential-oracle closes the false-done bypass

### [TASK-10] Verified json-path-query leaf (json-path-query) — third earned leaf-library member

Detailed: adds a third verified leaf, `json-path-query`, to `harness/graph_dsl.py`'s `LEAF_LIBRARY` (the
same proven mechanism TASK-5/TASK-8 used), so the existing leaf-repair adopt path (TASK-6/TASK-7, already
generic over `leaf_for_spec`/`dsl_to_system` — no `system_builder.py` change needed) can ship a working
system for the held-out `json-path-query-cli` creation class. MEASURED this session: the class scores 0/3
for gemma — the free-form build crashes (traceback, 0/4 checks), over-decomposed into 3 modules, and the
repair loop doesn't fix it — genuinely reasoning-hard. Unlike `sql-mini-query-cli` this class correctly
reports `done=False` (no false-done), so the existing "not done -> adopt leaf" trigger alone is
sufficient; no seeded-driver/differential-oracle extension is needed for this leaf (the
`seeded_driver_input` registry conservatively returns `None` for this class, same as every other leaf
besides `sql-query-engine`, so no `system_builder.py` change).

#### Steps
1. Add `JSON_PATH_LEAF` to `harness/graph_dsl.py`: a cleaned-up, self-contained single `main.py`
   implementing dotted-path JSON resolution (`python main.py <path>` reads a JSON document from stdin,
   walks each dot-separated segment of `<path>` as an object key or, for a list, a non-negative integer
   index; prints the resolved value's `json.dumps` form, or `null` on invalid JSON / any missing segment
   / out-of-range index / a segment applied to a non-object non-array value), authored ONLY from the
   VISIBLE grammar contract (never any task's hidden checks — Tenet 3, no oracle leak).
2. Register it in `LEAF_LIBRARY` under a new class key, `"json-path-query"`, and add that key to `VOCAB`.
3. Add `_is_json_path_spec(spec)` — a new, CONSERVATIVE, independent fingerprint requiring STRONG,
   distinctive signals to CO-OCCUR (mentions `json` AND a dotted-path signal AND resolving/querying) —
   never a single loose keyword — so it fires ONLY for genuine dotted-JSON-path specs and still returns
   the correct existing leaf (or `None`) for `sqlite-persistent-kv`, `sql-query-engine`, `ttl-store`, and
   every other class (no over-trigger). Extend `leaf_for_spec` to try this fingerprint as a fallback
   (after the existing ADT + sql-mini checks).
4. Confirm (no code change) that `build_system`'s existing leaf-repair adopt path picks up the new leaf
   via `leaf_for_spec`/`dsl_to_system` unchanged — both are already class-generic, so this is a strict
   superset with no modification to `harness/system_builder.py`. Because this class never false-dones, do
   NOT register a `seeded_driver_input` entry for it either (the registry's existing default-`None`
   behavior for any unregistered class is the correct, simpler choice here — relies purely on the
   pre-existing `not done` trigger).
5. Add `tests/test_ext058_jsonpath_leaf.py` (offline, no model call): the emitted `JSON_PATH_LEAF` passes
   ALL 4 of `json-path-query-cli`'s independent checks (reusing
   `harness.system_suite._run_single_check`); `leaf_for_spec` returns `"json-path-query"` for the
   held-out `json-path-query-cli` spec, and explicitly does NOT return it for a `sqlite-persistent-kv-cli`
   spec, a `sql-mini-query-cli` spec, or a `kv-store-ttl-cli` spec (no-over-trigger negatives, asserted
   explicitly); `dsl_to_system` emits the leaf for a single `json-path-query` node.
6. Run `python -m pytest tests/test_ext058_jsonpath_leaf.py tests/test_ext058_sql_leaf.py
   tests/test_ext058_leaf_differential.py tests/test_ext058_graph_dsl.py -q` green. Do NOT run the
   broader suite or any on-Jetson/live test.

#### Implements
- [REQ-7] Verified json-path-query leaf (json-path-query)

### [TASK-11] Fix json-path leaf crash on missing argv: survive the usage/no-args probe

Detailed: closes a MEASURED bug (on-Jetson, this session) that made the json-path-query leaf
(TASK-10) never actually get adopted by the existing leaf-repair path even though it passes all 4
real `json-path-query-cli` checks in isolation. Root cause: `JSON_PATH_LEAF` reads
`sys.argv[1]` with no guard, so invoking it with NO arguments crashes (rc=1, `IndexError`).
`build_system`'s derived minimum acceptance includes a "usage/--help runs without crashing" check
(no args supplied); the crashing leaf fails that check during the adopt re-verify, so the
leaf-repair block rolled back to the (broken) free-form build every time (`build_path` stayed
`free-form`, class stayed 0/3). The `sql-mini` leaf does not hit this because it reads stdin, not
`argv`, so it has no analogous no-args crash. Fix is narrowly scoped to the leaf template only —
no change to `harness/system_builder.py`'s acceptance/adopt logic.

#### Steps
1. In `harness/graph_dsl.py`'s `JSON_PATH_LEAF` template, at the top of `main()`, guard the
   missing-argument case: if `len(sys.argv) < 2`, print `null` and return cleanly (rc=0) before
   touching `sys.argv[1]` — matching the spec's existing "print `null` on any failure" convention.
   No other behavior change (a path argument is still required/consumed exactly as before for
   every real invocation).
2. Extend `tests/test_ext058_jsonpath_leaf.py`: (a) confirm the emitted leaf STILL passes all 4 of
   `json-path-query-cli`'s independent checks (byte-identical to TASK-10, unchanged 4/4); (b) NEW —
   running the emitted `main.py` as a subprocess with no command-line args exits rc=0, prints
   `null`, and produces no traceback on stderr — the exact usage-probe case that was failing.
3. Run `python -m pytest tests/test_ext058_jsonpath_leaf.py tests/test_ext058_sql_leaf.py
   tests/test_ext058_leaf_differential.py tests/test_ext058_graph_dsl.py -q` green. Do NOT run the
   broader suite or any on-Jetson/live test (host load must stay light).

#### Implements
- [REQ-7] Verified json-path-query leaf (json-path-query) — the no-args usage-probe robustness bullet
