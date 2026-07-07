# Implementation Tasks

### [TASK-1] Build the ADT differential oracle core (classify + LRU reference + seeded drive + first-divergence)

Create the first, load-bearing slice of `harness/adt_oracle.py`: the classifier, the LRU reference
model, the seeded sequence generator, and the differential-drive `verify` that reports the first
divergence. LRU is the beachhead ADT (the best-of-k blind spot and the raw-probe pointer-bug example
both live here); the other ADTs are added in follow-up tasks. This task does NOT yet wire the oracle
into `system_builder` acceptance — that is TASK-2 — so the build suite cannot regress from this task
alone.

#### Steps
1. Create `harness/adt_oracle.py` (pure stdlib, no model call). Add module-level `# #EXT-056-REQ-1`
   traceability markers around the implementation.
2. Define an `AdtResult` dataclass with fields: `applicable: bool`, `cls: str | None`, `ok: bool`,
   `first_divergence: dict | None` (keys: `index`, `op`, `args`, `expected`, `actual`), and
   `detail: str`. Add a helper `_inconclusive(detail) -> AdtResult` returning
   `AdtResult(applicable=False, cls=None, ok=True, first_divergence=None, detail=detail)`.
3. Implement `classify(spec: str, mods: list[str]) -> str | None`: fingerprint method/command names
   found in `mods` plus keywords in `spec` against a table for `lru`, `priority-queue`, `ttl-store`,
   `fifo`, `ring-buffer`. Return exactly one id when the fingerprint is unambiguous, else `None`
   (a non-ADT or ambiguous build classifies to `None`).
4. Implement `_lru_reference(capacity)`: a ~20-line `OrderedDict`-backed model exposing `get(key)`
   (returns value or a sentinel/`None`, and marks recently-used) and `put(key, value)` (inserts /
   updates, evicts least-recently-used at capacity). This is authored from the visible LRU contract
   only — no hidden-test knowledge.
5. Implement `_seeded_ops(cls, seed, n)` using `random.Random(seed)` (never the global RNG): generate
   an op sequence that stresses LRU boundaries — capacity eviction, re-access reordering, repeated
   keys, misses. Same seed → identical sequence (byte-replayable).
6. Implement `verify(root, entry, cls, *, seed=1234, timeout=20) -> AdtResult`: build the reference,
   generate ops, and for each op apply it to the reference AND drive the built CLI via
   `harness.system_suite._run_cli` (sandboxed). Compare the observable result; on the first mismatch
   return an `AdtResult` with `ok=False` and a populated `first_divergence`. If all ops agree return
   `ok=True`. Wrap the whole body so ANY exception returns `_inconclusive(...)` — `verify` never
   raises.
7. Add `tests/test_ext056_adt_oracle.py`: (a) `classify` returns `"lru"` for an LRU-shaped
   spec/module and `None` for a non-ADT (e.g. a notes CLI); (b) `_seeded_ops` is deterministic across
   two calls with the same seed; (c) `verify` PASSES against a correct `OrderedDict` LRU CLI fixture;
   (d) `verify` FAILS against a fixture with the classic `_move_to_head` / eviction pointer bug and
   the returned `first_divergence` names the diverging op. Use small offline fixtures written to a
   temp dir; skip nothing (no docker/network needed).
8. Run the test suite via `python -m harness.run_with_heartbeat -m pytest tests/test_ext056_adt_oracle.py -q`
   and confirm green; then a fast focused run of the existing `system_builder`/`system_suite` tests to
   confirm no import-time regression from the new module.

#### Implements
- [REQ-1] ADT Differential Oracle
