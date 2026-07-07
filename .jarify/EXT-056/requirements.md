---
id: EXT-056
title: Deterministic Verification Toolset
status: partial
priority: high
implementation:
  - file: harness/adt_oracle.py
    ranges:
      - - 63
        - 419
  - file: tests/test_ext056_adt_oracle.py
    ranges:
      - - 15
        - 272
  - file: harness/system_builder.py
    ranges:
      - - 224
        - 228
      - - 1164
        - 1183
  - file: tests/test_ext056_acceptance_wiring.py
    ranges:
      - - 34
        - 310
---

### [REQ-1] ADT Differential Oracle

A deterministic, two-plane verification tool that makes the semantic-ordering failure mode of a
built system **visible and localized**, so the acceptance signal is no longer blind to it and the
model can reason on a concrete divergence witness. It lives in a new module `harness/adt_oracle.py`
(a sibling of `harness/datastore_oracle.py`): pure stdlib, makes **no model call**, and **never
raises** — any internal error yields an inconclusive result, never a build failure.

It operates in four deterministic stages: (1) **classify** the built system against at most one
canonical abstract data type (`lru`, `priority-queue`, `ttl-store`, `fifo`, `ring-buffer`) by
fingerprinting method names + spec keywords, or `None` for a non-ADT; (2) construct a short
**reference model** (a textbook stdlib implementation authored from the *visible* spec's declared
operations, never from any hidden test); (3) generate a **seeded**, boundary-stressing operation
sequence with a fixed PRNG so the run is byte-replayable; (4) **drive** the sequence through the
reference and the built CLI in lockstep (via `system_suite._run_cli`), and on the **first
divergence** stop and report the op index, op name + args, expected value, and actual value as the
localized witness.

It wires into acceptance by contributing **one additional check** to `_minimum_acceptance`, composed
by **union** in `_compose_acceptance_checklist`. Because composition is union-only, the oracle can
only ever ADD a way for a build to fail — it can flip `done` from `True`→`False` but never
`False`→`True` — so the 0-false-done invariant (Tenet 3) is preserved by construction. When the
build is not a classifiable ADT (or the oracle is inconclusive), it contributes nothing (a no-op).
This supersedes REQ-37 (the model-authored property check, measured default-off because the 2B
cannot reliably write those checks): the reference model is authored deterministically by the
harness.

#### Acceptance Criteria
- [ ] Add `harness/adt_oracle.py` exposing `classify(spec, mods) -> str | None`, a reference-model
      builder per supported ADT, a seeded sequence generator, and
      `verify(root, entry, cls, *, seed) -> AdtResult`. (TASK-1 built the module + all four stages,
      but only the `lru` reference model — the other four ADTs' reference-model builders are future
      tasks, so this criterion stays open until every supported ADT has one.)
- [x] `classify` returns at most one canonical ADT id or `None`; a non-ADT build yields `None` and
      the oracle is a pure no-op (adds no acceptance check).
- [x] Reference models are built ONLY from the visible spec's declared operations — never from the
      eval's hidden tests (Tenet 3, no leak).
- [x] The sequence generator is seeded by a parameter and byte-for-byte replayable; the same seed
      produces the same op sequence.
- [x] `verify` drives the reference and the built CLI in lockstep and, on the first divergence,
      returns the op index, op name + args, expected value, and actual value.
- [x] `verify` NEVER raises: any internal error (missing CLI, parse failure, timeout) yields an
      inconclusive `AdtResult` that is treated as a no-op, never a build failure.
- [x] The oracle contributes one acceptance check into `_minimum_acceptance`, composed by union in
      `_compose_acceptance_checklist`, so it can only flip `done` True→False (0-false-done preserved).
      (TASK-2: wired via `adt_oracle.classify_confident` + `adt_oracle.acceptance_check`, union-only,
      never removes/replaces an existing check — see `tests/test_ext056_acceptance_wiring.py`.)
- [x] An offline test PASSES a correct `OrderedDict`-based LRU fixture and FAILS a fixture with the
      classic `_move_to_head` pointer bug, reporting the localized first divergence.
- [ ] Held-out validation: develop the classifier + references on `{lru, priority-queue}`, HOLD OUT
      `{ttl-store, ring-buffer}`, and grade with an independent hidden suite (a different impl than
      the reference); report pass@1 (temp=0) oracle-in-loop vs baseline honestly. (Deferred to
      TASK-3 — needs the priority-queue reference model first.)
