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

### [TASK-2] Wire the ADT oracle into build acceptance (union-safe, conservative, no false-not-done)

Make the oracle actually gate builds by contributing ONE acceptance check into the deterministic
minimum, composed by UNION so it can only flip `done` True→False (0-false-done preserved by
construction). The check must be a SELF-CONTAINED script (the checklist runner `_run_check` writes a
check's `code` to `root/_s2s_acceptance_check.py` and runs it standalone in the built system's dir —
no harness import is available there). The drift-free design: compute the seeded op sequence +
expected outputs ONCE in-process (reusing the tested `_seeded_ops` + `_lru_reference`), then bake the
fixed command-lines + expected values into the emitted script — the reference logic lives once in
`adt_oracle.py`, the script only drives + compares. Expected values come from the reference model, NOT
from any hidden test (no leak). Be CONSERVATIVE: emit the check ONLY when the spec EXPLICITLY names the
ADT (a keyword hit), never on method-token coincidence alone — under-assert rather than risk a
false-not-done on a non-eviction key-value store that merely has get/put commands.

#### Steps
1. In `harness/adt_oracle.py`, refactor the sequence-building block inside `verify` into a shared
   helper `_build_sequence(cls, seed, n, capacity) -> tuple[list[str], list[str]]` returning
   `(cmd_lines, expected_lines)`; have `verify` call it (keep all 12 existing tests green).
2. Add `classify_confident(spec, mods) -> str | None` (or a `require_keyword=True` flag on `classify`)
   that returns a class ONLY when that class got at least one KEYWORD hit (the ×2 signal) — i.e. the
   spec explicitly names the ADT — so a plain bounded-dict with get/put is NOT classified as `lru`.
3. Add `acceptance_check(entry, cls, *, seed=1234, capacity=_LRU_CAPACITY) -> dict | None` to
   `adt_oracle.py`: returns `None` if `cls not in _IMPLEMENTED_CLASSES`; else builds
   `(cmd_lines, expected_lines)` via `_build_sequence`, and emits a `{"name", "code"}` dict whose
   `code` is a standalone script that runs `subprocess.run([sys.executable, entry, str(capacity)],
   input="\n".join(cmd_lines)+"\n", capture_output=True, text=True, timeout=20)`, splits stdout, and
   `assert`s each line equals the baked-in expected value, reporting the FIRST divergence in the assert
   message (`f"ADT {cls} divergence at op[{i}]: expected {exp!r}, got {act!r}"`). Name:
   `f"minimum: {cls} differential-oracle (seeded ops vs textbook reference)"`. Never raises.
4. In `harness/system_builder.py::_minimum_acceptance`, immediately AFTER the `# #EXT-036-REQ-27`
   round-trip block (after line ~1150, still inside `if entry:`), add inside `# #EXT-056-REQ-1`
   markers: classify the build conservatively from `spec` + extracted command tokens + module names
   (`_extract_command_tokens(spec)` plus `[m.get("name","") for m in mods]`), and if a confident class
   is returned, append `adt_oracle.acceptance_check(entry, cls)` when non-None. Wrap in try/except so a
   classification/emit failure NEVER breaks checklist derivation (append nothing on error). Import
   `adt_oracle` (top-level `from harness import adt_oracle`, or a function-local import if any cycle
   appears — the regression import check must stay green).
5. Add `tests/test_ext056_acceptance_wiring.py`: (a) `_minimum_acceptance` for an explicit LRU spec
   (mentions "LRU"/"least recently used") INCLUDES the adt check; (b) for a non-ADT spec (notes CLI)
   and for a plain get/put store with NO "lru" keyword, it does NOT (conservative no-op); (c) the
   emitted `code`, run against a correct OrderedDict LRU fixture, passes; against the `_move_to_head`
   pointer-bug fixture, fails; (d) UNION-SAFETY: the composed checklist from
   `_compose_acceptance_checklist` for a non-ADT spec is byte-identical to before (the oracle added
   nothing) — i.e. the minimum is never made SPARSER, only ever stricter.
6. Run ONLY the focused files via `timeout 240 python -m pytest tests/test_ext056_adt_oracle.py
   tests/test_ext056_acceptance_wiring.py -q`, then a fast import-regression check
   `python -c "import harness.adt_oracle, harness.system_builder, harness.system_suite"`. Do NOT run
   the full suite. Update `index.json` (jarify-manage-links) to map the new system_builder.py range.

#### Implements
- [REQ-1] ADT Differential Oracle

### [TASK-4] Priority-queue reference model — extend the ADT oracle to a 2nd ADT (unblock held-out proof)

Add the `priority-queue` reference model + seeded ops to `harness/adt_oracle.py`, mirroring the LRU
implementation, so the oracle checks a 2nd ADT and REQ-1's held-out validation can develop on
`{lru, priority-queue}` and HOLD OUT `{ttl-store, ring-buffer}`. Single-file, off-Jetson.

#### Steps
1. In `harness/adt_oracle.py` (inside the existing `# #EXT-056-REQ-1` region), add `priority-queue` to
   `_IMPLEMENTED_CLASSES` and implement `_priority_queue_reference(...)` using `heapq` + an insertion
   counter for stable tie-break ordering (a textbook min-heap PQ, authored ONLY from the visible PQ
   contract — push/pop-min/peek — never from a hidden test; Tenet 3, no leak).
2. Extend `_build_sequence`/`_seeded_ops` to generate a boundary-stressing PQ op sequence (pushes with
   varied priorities incl. ties, pops, peeks, empty-pop) under the fixed-PRNG seed (byte-replayable).
3. Extend `acceptance_check`/`verify` to drive the PQ CLI convention (mirror the LRU stdin/line
   protocol; pick the convention already used by any PQ task in `system_suite.py` if present, else the
   natural `push <priority> <item>` / `pop` / `peek` line protocol) and compare lockstep to the
   reference, reporting first-divergence. `verify` still NEVER raises; non-PQ builds unaffected.
4. Add tests to `tests/test_ext056_adt_oracle.py` (or a new `tests/test_ext056_priority_queue.py`):
   classify returns `"priority-queue"` for a PQ-shaped spec; `_priority_queue_reference` pops in
   priority-then-insertion order (incl. ties); `verify` PASSES a correct heapq PQ fixture and FAILS a
   fixture with a tie-break/ordering bug, naming the first divergence.
5. Run ONLY the focused adt-oracle test files via `timeout 240 python -m pytest tests/test_ext056_adt_oracle.py -q`
   (+ the new PQ test file if separate), then `python -c "import harness.adt_oracle, harness.system_builder"`.
   Do NOT run the full suite. Update `.jarify/EXT-056/index.json` for the extended REQ-1 range.

#### Implements
- [REQ-1] ADT Differential Oracle

### [TASK-5] TTL-store reference model — extend the ADT oracle to a 3rd ADT

Add the `ttl-store` reference model + seeded ops to `harness/adt_oracle.py`, mirroring the LRU/PQ
implementations, so the oracle covers a 3rd ADT toward REQ-1's held-out proof. Single-file, off-Jetson.
Uses a VIRTUAL clock (a deterministic tick counter passed as an op arg) — NEVER wall-clock — so runs
are byte-replayable (mirrors the creation-suite TTL convention: ttl=0 = immediate expiry, no real sleep).

#### Steps
1. In `harness/adt_oracle.py` (inside `# #EXT-056-REQ-1`), add `"ttl-store"` to `_IMPLEMENTED_CLASSES`
   + the classify keyword/method tables (keywords: "ttl","time-to-live","expire"; methods: set/get/expire/ttl).
2. Implement `_ttl_store_reference(...)`: a dict + per-key expiry-tick; `set <key> <value> <ttl>` stores
   with expiry = now+ttl; `get <key>` returns the value if not expired (now < expiry) else `none`; a
   virtual `now` advances by an explicit `tick`/step op (NOT wall-clock). Authored from the visible
   set/get/ttl contract only (no leak).
3. Extend `_build_sequence`/`_seeded_ops` for `ttl-store`: sets with varied ttls incl. ttl=0
   (immediate-expiry boundary), gets before/after expiry ticks, overwrite-resets-ttl. Seeded/replayable.
4. Extend `verify`/`acceptance_check` to drive the ttl-store CLI convention lockstep vs the reference
   (match any ttl CreationTask convention in system_suite.py if present, else the natural line protocol);
   report first-divergence; still NEVER raises; non-ttl builds unaffected.
5. Tests in `tests/test_ext056_adt_oracle.py`: classify→ttl-store for a ttl-shaped spec (+ conservative
   negative); reference expires at the right virtual tick incl. ttl=0; verify PASSES a correct ttl fixture
   and FAILS an off-by-one-expiry-bug fixture with a localized first-divergence.
6. Run ONLY `timeout 240 python -m pytest tests/test_ext056_adt_oracle.py -q`, then
   `python -c "import harness.adt_oracle, harness.system_builder"`. Do NOT run the full suite. Update index.json.

#### Implements
- [REQ-1] ADT Differential Oracle
