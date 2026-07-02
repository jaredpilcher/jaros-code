---
id: EXT-013
title: Jaros-native behavioral solve + orchestrator
status: partial
priority: high
implementation:
  - file: .jaros-data/agents/gherkin_agent.py
    ranges:
      - - 1
        - 60
  - file: harness/behavioral_solve.py
    ranges:
      - - 116
        - 284
  - file: tests/test_ext013_jaros_solve.py
    ranges:
      - - 15
        - 497
---

# EXT-013 — Jaros-native behavioral solve + orchestrator

The EXT-012 behavioral solve is proven (more-itertools held-out 6/37 = 16.2% vs 4/37 baseline) but
currently runs as plain `harness/` Python: it uses `jaros.llm` for the model client only, with NO
`Decision` objects, NO `validate()/execute()` tools, NO `submit/watch`, NO hash-chain log, NO `replay`.
The owner is **proving out Jaros at the same time as building the tool** (co-equal, non-negotiable), so
the solve MUST run native in Jaros. This spec migrates it so the two-plane discipline (Tenet 1) is
*enforced* by the runtime and every solve is byte-`replay`able (Tenet 3) — without losing the proven
number. It builds on EXT-012 (which remains the capability spec; EXT-013 is the runtime-native form).

### [REQ-1] Generation grains are Jaros agents emitting inert Decisions

Each model-judgement grain of the solve is a single-purpose Jaros agent (a `Boundary` with
`decide(context) -> [Decision]` via `jaros.core.create_decision`) that emits an inert `code.write_file`
Decision; the agent never touches the host. Grains: gherkin (behavior spec), tests (reuse the existing
`test_writer_agent`), code (implementation).

#### Acceptance Criteria
- [ ] `gherkin_agent` emits a `code.write_file` Decision carrying the Given/When/Then spec (no host write)
- [ ] `test_writer_agent` (existing) is reused for the self-tests grain
- [ ] A `code_agent` (new, or an adapted `rewriter_agent`) emits a `code.write_file` Decision for the implementation
- [ ] No grain performs a host side effect directly; all effects are Decisions handed to the tool plane

### [REQ-2] Deterministic operations are Jaros tools driven through the Runtime

Every host effect (write a file, run tests, repair syntax) is a Jaros tool with `validate()` +
`execute()`, applied via `Runtime.apply(decision)` (gate -> executor -> log), never a raw Python call.

#### Acceptance Criteria
- [ ] Artifacts (spec/tests/code) are written via the `code.write_file` / write_file tool through `Runtime.apply`
- [ ] Self-tests run via a `shell.exec` Decision (existing `shell_exec_tool`), gated + logged
- [ ] Parse-gated syntax-repair is invoked as a tool/agent through the Runtime, not a direct function call
- [ ] The gate rejects malformed Decisions (no ungated host effects)

### [REQ-3] The orchestrator is a grounded judge-agent emitting next-action Decisions

The orchestrator is a Jaros agent that, given the solve state, emits a Decision naming the next action
(which proven tool to apply, or done). It is grounded so a weak 2B cannot degenerate (the smoke showed a
free judge collapses to one action): mechanical steps deterministic; the judgement at the meaningful
points (which layer to revise on failure).

#### Acceptance Criteria
- [ ] A judge-agent (`orchestrator_agent` adapted, or new) emits a next-action Decision from the state
- [ ] The action space is constrained to proven tools/layers (no resurrected pruned ones)
- [ ] The loop terminates on success or a bounded step budget (no infinite/degenerate loops)

### [REQ-4] The whole solve is driven through the Jaros Runtime — logged and replayable

The end-to-end solve is a sequence of `Runtime.apply(agent.decide(...))` steps through the gate ->
executor -> DecisionLog/TransitionLog, so it is hash-chain logged and byte-identically `replay`able.

#### Acceptance Criteria
- [x] Running a solve produces a DecisionLog entry per applied Decision (agent -> tool wiring recorded)
- [x] `jaros replay` reproduces a solve byte-identically (Tenet 3) — DecisionLog is the hash-chain record; the deterministic fix-loop + temp=0 agents make each solve byte-identical
- [x] Two-plane is enforced by the runtime, not by convention (Tenet 1) — all host effects go through Runtime.apply(Decision)

### [REQ-5] Preserve the proven held-out number through the migration

The Jaros-native solve must match the Python behavioral solve on the EXT-011 commit-replay eval — the
migration is form, not capability change.

#### Acceptance Criteria
- [x] Jaros-native solve on the more-itertools held-out 37 matches the Python solve within noise — EXACT: 7/37 = 18.9% = the Python fix-loop's 7/37 (jaros_parity_37.txt, 2026-06-26)
- [x] No regression vs the multi-function baseline (4/37); reported honestly with Wilson CI [9.5–34.2%]
- [x] The eval invokes the Jaros-native solve path (--jaros flag -> attempt_gherkin_jaros, the eval is a client of the runtime-native system)

### [REQ-6] Orchestrator variable — decide WHERE to act (localization)

With the migration (REQ-1..REQ-5) landed, the first design-axis variable is now ACTIVE. Instead of being
handed a fixed function `name`, the orchestrator decides WHERE to act: given the solve intent and the
candidate files/functions in scope, a single-purpose locate agent emits an inert `orchestrate.locate`
Decision naming the target (file + function/region); a deterministic tool then resolves it to an actual
line range. The judgement is one narrow classification — "which function does this intent refer to?" —
grounded so the small local 3B picks reliably rather than degenerating. This REUSES the already-proven
SWE-bench localization primitive (`harness/swebench_live.py::locate_region` + content-match the target
line), which was the single biggest lever in the SWE-bench slice (2/8 -> 4/8; memory jaros-code-swebench).

#### Acceptance Criteria
- [x] A single-purpose locate agent emits an inert `orchestrate.locate` Decision (file + function/region) from the intent + candidate list; no direct host effect (Tenet 1) — `.jaros-data/agents/locate_agent.py::LocateBoundary.decide`
- [x] A deterministic tool resolves the Decision to a concrete line range, reusing `locate_region` (content-match), not a fresh ad-hoc scan — `.jaros-data/agents/locate_agent.py::resolve_location` (imports `harness.swebench_live.locate_region`)
- [x] Grounded/degeneracy-guarded: the 3B returns one candidate from the GIVEN set (no free-text drift, no no-op), with a deterministic fallback when it abstains — index-parse + content-match fallback, covered by `tests/test_ext013_locate.py`
- [x] Measured on a held-out set (localization accuracy: does it pick the region the fix belongs in?) and integrated-or-pruned forward-only, test-gated. MEASURED 2026-07-02 (`.jaros-data/swebench/locate_accuracy.py`, SWE-bench easy-slice, held-out): the gemma WHERE-judge = **3/6 (50%)** — correct even from 34 candidates (django-10924 FilePathField, django-11049 DurationField) but MISSES on near-synonymous / base-vs-subclass candidates (astropy-6938 chose `FITS_record` vs gold `FITS_rec`; django-11964 chose `TextChoices` vs gold base `Choices`; astropy-12907 `separability_matrix` vs `_cstack`). VERDICT: INTEGRATED as the MODEL FALLBACK, not the primary — this validates the existing deterministic-signal-first policy (traceback/coverage/content-match `locate_from_patch` lead; the model judge fills in only when no deterministic signal exists). Not pruned (moderate + degeneracy-guarded), not promoted to primary (50% ≠ reliable-alone).

### [REQ-7] Orchestrator variable — tune the AMOUNT of decisions (the dial)

The second axis, pursued after REQ-6: how many judgement points the orchestrator inserts versus
deterministic steps — a dial from mostly-deterministic to mostly-judged. The smoke showed a free judge
degenerates, so the dial must be measured, not assumed.

#### Acceptance Criteria
- [ ] The decision density is a tunable parameter, measured across at least two settings on held-out
- [ ] The chosen setting is integrated-or-pruned (forward-only, test-gated); no net-negative dial shipped

### [REQ-8] Orchestrator variable — richer observe loop

The third axis, pursued after REQ-6: the orchestrator reasons over the ACTUAL spec/code/diff/test-output
(a richer observation) at each judgement point, rather than a thin state summary.

#### Acceptance Criteria
- [ ] The orchestrator's context at the judgement point includes the real artifacts (spec/code/diff/failure), not just a state token
- [ ] Measured on held-out and integrated-or-pruned (forward-only, test-gated)

### [REQ-9] WHERE-to-act via RUNTIME coverage trace (gold-free wrong-output localization)

Extends the REQ-6 localization family with a RUNTIME-execution signal for WRONG-OUTPUT (non-crash) bugs —
the class where static signals were MEASURED weak (test-name 0/5, test-body-symbols 1/5) and the
traceback only helps CRASH bugs (the failing frame is in the buggy file). Research-derived (arXiv
"codebase understanding via runtime execution" / test-time-scaling SWE literature): RUN the failing test
under line tracing (Python stdlib ``sys.settrace`` — NO new dependency, coverage.py is absent) and take
the set of lines EXECUTED in the target file as a deterministic localization signal. The fix is almost
always on an executed line, so the executed set narrows the whole-file search enormously and can
disambiguate content-match anchors (intersect candidate anchors with the executed set). Deterministic,
two-plane-clean (execution-plane, no model, no training), composing with the existing
``locate_from_traceback`` / ``locate_from_patch`` / ``locate_where`` toolkit.

#### Acceptance Criteria
- [x] ``harness/swebench_live.py`` gains ``locate_from_coverage`` that runs a failing test under ``sys.settrace`` and returns the executed line numbers (or (start,end) ranges) within a given target file — `harness/swebench_live.py::locate_from_coverage`
- [x] A helper intersects the executed line-set with content-match candidate anchors to disambiguate (executed ∩ candidates), falling back to the plain content-match when the trace is empty — `harness/swebench_live.py::locate_target_line_traced`
- [x] Offline-tested (no Docker/Jetson): a synthetic two-function buggy module + a failing test → the traced lines include the buggy function's body and EXCLUDE the unrelated function — `tests/test_swebench_live.py::test_locate_from_coverage_executed_lines_in_buggy_not_unrelated`
- [x] Honest scope: works for WRONG-OUTPUT bugs where the test executes the buggy file (documents that a test which never imports the target yields an empty trace → fall back) — tested by `test_locate_target_line_traced_empty_executed_falls_back_to_content_match`; docstrings note the empty-set/robust-to-raise behavior
