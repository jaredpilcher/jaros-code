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
- [x] Add `harness/adt_oracle.py` exposing `classify(spec, mods) -> str | None`, a reference-model
      builder per supported ADT, a seeded sequence generator, and
      `verify(root, entry, cls, *, seed) -> AdtResult`. (TASK-1 built the module + all four stages;
      TASK-4/5/6/7 added the priority-queue/ttl-store/ring-buffer/fifo reference models — all 5
      `SUPPORTED_CLASSES` now have a reference-model builder.)
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
- [x] TASK-8 (MEASURED 2026-07-07): `classify_confident` recognizes the split-phrase phrasing
      "priority `<word>` queue" (e.g. the creation-suite `priority-jobqueue-cli` spec "an in-memory
      priority JOB queue") via a per-class spec regex, but ONLY for a class `classify` already
      evidenced on method tokens — so it broadens RECOGNITION without inventing a class. Closes a
      measured FALSE-DONE: the build self-accepted (done=True) with a wrong priority ordering the
      oracle never ran because the contiguous keyword "priority queue" missed the split phrase. Guards
      hold (fifo/stack specs unaffected; no fire without method evidence). `tests/test_ext056_adt_oracle.py::test_classify_confident_returns_priority_queue_for_split_phrase_priority_job_queue`.
- [x] TASK-9 (MEASURED 2026-07-07): the emitted drive is VOCABULARY-AWARE — `acceptance_check(entry,
      cls, *, spec=None)` (threaded from `_minimum_acceptance`, which already has `spec`) resolves,
      per canonical driving verb, the SYNONYM the VISIBLE spec text actually declares (e.g.
      `enqueue`/`dequeue` instead of the hard-coded `push`/`pop`) via `_resolve_verbs` +
      `_ADT_VERB_SYNONYMS`, and bakes those words into the drive instead of always the canonical
      ones. SAFETY: an absent/ambiguous spec falls back to the exact pre-fix canonical vocabulary
      (proved byte-identical by
      `test_acceptance_check_falls_back_to_canonical_vocabulary_without_a_spec`) — purely additive,
      never a behavior change for a build whose spec names no synonym. Closes one genuine class of
      false-not-done (a correct synonym-vocabulary CLI driven with the wrong hard-coded verbs is now
      driven correctly; a wrong one using the same synonyms is still caught —
      `test_acceptance_check_is_vocabulary_aware_enqueue_dequeue_synonym`). **KNOWN OPEN GAP,
      MEASURED same session:** `tests/test_ext036_property_check.py`'s 6 `priority-queue` tests
      (fixtures `WRONG_PQ_CLI`/`CORRECT_PQ_CLI`) remain red — root-caused NOT to vocabulary
      (confirmed: with the fix, `_resolve_verbs` correctly resolves `push→enqueue`/`pop→dequeue` for
      that spec) but to a DIFFERENT, deeper mismatch: those fixtures use the ARGV-per-command,
      disk-persisted-state CLI convention (`python main.py enqueue 2 low`, one subprocess per
      command — the SAME convention `_no_crash_subprocess_check`/`_roundtrip_acceptance_check` drive
      elsewhere in `_minimum_acceptance`), while `acceptance_check`'s drive always spawns ONE process
      with `argv=[]` and feeds the WHOLE op sequence as stdin lines (the single-process stdin-REPL
      convention TASK-1's LRU beachhead used). A CLI following the argv-per-command convention never
      reads stdin at all, so it fails at op[0] regardless of verb. This is a genuine, separate
      Tenet-3 false-not-done class (an oracle-assumed CLI invocation convention that is not the only
      legitimate one this codebase's own builds use) — tracked as a follow-up requirement, NOT forced
      green here per explicit instruction to stop rather than paper over a different-cause failure.
- [x] TASK-10 (REQ-1, MEASURED 2026-07-08): the `ttl-store` branch of `acceptance_check` was
      unconditionally driving a virtual-clock `tick` convention (TASK-5), but the `kv-store-ttl-cli`
      spec (`harness/system_suite.py`) is REAL-SECONDS TTL (`set <key> <value> <ttl_seconds>`, no
      `tick` command at all) — so even a CORRECT real-seconds ttl-store CLI was false-rejected
      (`done=False`). Fix: `_ttl_convention(spec)` reads ONLY the visible spec text to tell a
      `tick`-worded spec from a `second`/`seconds`/`ttl_seconds`-worded one, defaulting to `"tick"`
      (byte-identical to before) for an absent/empty/ambiguous spec. Only when the convention
      resolves to `"real"` does `acceptance_check` route to a NEW, separate drive
      (`_ttl_store_real_seconds_check`) that spawns the built CLI as one persistent, unbuffered
      subprocess and probes REAL wall-clock expiry (a short-real-ttl key expires after an actual
      `time.sleep` just past it; a long-real-ttl key set at the same time does not) — the
      pre-existing virtual-clock `tick` drive, and every other ADT class, are unchanged. Proven with
      offline fixtures: a correct real-seconds ttl-store CLI now PASSES
      (`test_acceptance_check_passes_correct_real_seconds_ttl_fixture`); a buggy real-seconds
      ttl-store that never enforces its ttl STILL FAILS
      (`test_acceptance_check_fails_buggy_never_expires_real_seconds_ttl_fixture` — the critical
      anti-false-done proof); the tick convention (`verify()` and `acceptance_check` with no spec or
      a tick-worded spec) is byte-identical to before
      (`test_acceptance_check_ttl_store_tick_convention_unchanged_by_real_seconds_fix`,
      `test_verify_ttl_store_unaffected_by_real_seconds_fix`); and the other 4 ADT classes are
      untouched (`test_acceptance_check_other_adt_classes_unaffected_by_ttl_convention_fix`).
      **GAP CLOSED by TASK-11 (2026-07-08):** `_resolve_verbs` (TASK-9) previously picked the first
      synonym found ANYWHERE in the spec text for each canonical verb without checking whether the
      canonical word was ALSO literally present, so the LITERAL, unmodified `kv-store-ttl-cli`
      sentence (which explicitly names `set`/`get`) resolved to `store`/`read` because the
      surrounding prose ("key-value store", "...the commands were read") incidentally contained
      those words too — a SEPARATE, pre-existing vocabulary-priority issue that also mis-resolved
      OTHER classes (e.g. `lru`'s `get`→`read` against this same spec), independent of this task's
      convention fix. TASK-11 gives the canonical word PRIORITY: if it is literally present in the
      spec, the verb resolves to itself; only an ABSENT canonical falls back to a declared synonym
      (TASK-9's fallback preserved unchanged). Proven with the LITERAL `kv-store-ttl-cli` spec now
      resolving `set`→`set`/`get`→`get`
      (`test_resolve_verbs_prefers_literal_canonical_over_incidental_synonym_on_kv_store_ttl_cli_spec`),
      the synonym fallback still firing when canonical is absent
      (`test_resolve_verbs_synonym_fallback_preserved_when_canonical_absent`), other ADT classes
      unaffected for non-colliding specs
      (`test_resolve_verbs_other_classes_unaffected_by_canonical_priority_fix`), and the critical
      anti-false-done proof: a correct real-seconds ttl-store CLI now PASSES `acceptance_check`
      driven by the literal `kv-store-ttl-cli` spec while a genuinely buggy one STILL FAILS
      (`test_acceptance_check_still_catches_buggy_build_with_literal_kv_store_ttl_cli_spec`).
- [x] TASK-12 (REQ-1, MEASURED during the TASK-158/EXT-036 diagnosis): the `priority-queue`
      reference model (TASK-4) hard-coded a MIN-heap comparison (a numerically SMALLER priority
      number wins), but a spec can legitimately declare the OPPOSITE convention ("highest number
      first" / "max-heap") — the always-on ADT floor then DEMOTED a genuinely correct max-heap
      build (`done=False`) because the reference model's assumed direction disagreed with the
      build's own declared direction, corrupting the grading of any legitimate max-heap
      priority-queue spec. Fix: `pq_convention(spec)` reads ONLY the visible spec text to tell an
      explicit `"max"`-worded spec (`"max-heap"`/`"descending priority"`/"the highest number goes
      first"/"a higher number means higher priority") from everything else, resolving to the
      pre-existing `"min"` default for an absent spec, a spec that explicitly states `"min"`, AND a
      spec that is simply SILENT about direction (mirrors `_ttl_convention`'s "silence resolves
      safely" precedent — silence was already the universal assumption before this task, so this
      is never a new guess), and resolving to `None` (AMBIGUOUS) ONLY when the spec states BOTH
      directions at once (self-contradictory) — the one case that genuinely cannot be resolved
      safely. `_PriorityQueueReferenceModel`/`_priority_queue_reference`/`_build_sequence` are
      parameterized by `convention` (default `"min"`, byte-identical to every pre-TASK-12 caller);
      `acceptance_check` resolves the convention from `spec` for the `priority-queue` class only,
      and SKIPS the differential check entirely (returns `None`, adding nothing to the checklist)
      when `pq_convention` resolves to `None` rather than guess — a skipped check is honest, a
      wrong-convention check is a false-negative that corrupts the acceptance signal (Tenet 3).
      Proven offline: a correct max-heap pq fixture now PASSES `acceptance_check` when the spec
      says max (`test_acceptance_check_passes_correct_max_heap_pq_fixture_when_spec_says_max` —
      closes the measured false-negative); a correct min-heap pq fixture still passes with an
      explicit min spec, a silent spec, and no spec at all
      (`test_acceptance_check_still_passes_correct_min_heap_pq_fixture_with_explicit_min_spec`,
      `test_acceptance_check_silent_spec_defaults_to_min_not_skipped`,
      `test_acceptance_check_no_spec_still_defaults_to_min_convention_byte_identical` — no
      regression, byte-identical reference behavior); a self-contradictory spec makes
      `acceptance_check` skip the check entirely
      (`test_acceptance_check_skips_pq_differential_check_for_ambiguous_spec` — the not-applicable
      path, no demotion); a genuinely WRONG pq (max spec, min behavior) is still caught
      (`test_acceptance_check_catches_wrong_convention_pq_max_spec_min_behavior` — the critical
      anti-false-done proof); and the other 4 ADT classes' `acceptance_check` emissions are
      unaffected (`test_acceptance_check_other_adt_classes_unaffected_by_pq_convention_fix`).
