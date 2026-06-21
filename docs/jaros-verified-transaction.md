# Proposed Jaros core primitive: Verified Transaction (gated transactional transform)

Origin: extracted from jaros-code (the coding application). The *commands* (rename, move,
multi-file fix, plan) are coding-specific, but they are all built on ONE domain-agnostic pattern
that belongs in Jaros core. This doc specifies that pattern for the Jaros runtime.

## Intent
Apply a change to some state and KEEP it only if a deterministic verification still holds
afterward; otherwise leave the state byte-identical to before. Atomic, logged, replayable.
It is a database-style transaction whose COMMIT CONDITION is an arbitrary deterministic gate.

## Why it belongs in Jaros (not an application)
It is the two-plane discipline applied to multi-step mutation:
- the proposer (a model agent OR a deterministic generator) only emits INERT Decisions
  describing the transform and which gate to run;
- the executor deterministically snapshots, applies, verifies, and commits-or-rolls-back.
No side effect escapes the executor; "did it work?" is GROUND TRUTH from a deterministic gate,
never a model's say-so; and the whole transaction lands in the hash-chained decision log, so it
replays byte-for-byte. Any application built on Jaros then gets safe, verifiable, reversible
mutation for free.

## The abstraction — three pluggable pieces (all deterministic except the proposer)
- scope:     a snapshot-able / restore-able handle to the mutable state the transform may touch
             (e.g. a set of files, a config tree, a DB schema). Must capture EVERYTHING the
             transform can change, so rollback is complete.
- transform: an ordered sequence of Tool Decisions that mutate the scope. Proposed by an agent
             or a deterministic generator; executed through the normal gate+executor so each
             edit is itself validated and logged. It need NOT be "correct" — the gate is the net.
- gate:      a deterministic verifier over the POST-transform scope returning a Verdict
             {ok: bool, metric?: number (lower=better), diagnostics?: str}. A pure function of
             state. Itself a Tool (e.g. run tests, validate schema, type-check, lint). NEVER a
             model judgment.

## Semantics (this is the new executor primitive)
1. (optional) PRECONDITION: the gate must pass on the STARTING state — a transform that
   preserves an invariant requires the invariant to already hold.
2. SNAPSHOT the scope -> Checkpoint               (a logged decision)
3. APPLY the transform                            (its tool decisions run normally -> logged)
4. EVALUATE the gate -> Verdict                   (logged)
5. if Verdict.ok: COMMIT  (drop checkpoint; result = applied)
   else:          ROLLBACK to the checkpoint      (a logged decision; result = reverted)
6. return {committed: bool, verdict: Verdict, decisions: [Decision]}
From the caller's view it is ATOMIC: either (transform applied AND gate green) or (no change).

## Guarantee
After the transaction the gate's invariant is NEVER left violated by it: either the transform
is in place with the gate passing, or the scope is byte-identical to before. The full
transaction (snapshot, transform decisions, gate, commit/rollback) is in the hash-chained log
and replays deterministically.

## Requirements
- gate: deterministic, reproducible, TOTAL (always returns pass/fail), function of scope only.
- snapshot/restore: complete + idempotent (a re-applied restore is a no-op).
- transform: any deterministic edits; correctness is not assumed.

## Combinators built ON the Verified Transaction (also worth being Jaros primitives)
1. SEARCH-WITH-VERIFY (localize-then-verify): given an ORDERED list of candidate transforms,
   run each as a Verified Transaction; return the FIRST that commits; all others auto-roll-back.
   => "find the change that satisfies the gate" (deterministic best-of-N with execution select).
2. PROGRESS-GATED CUMULATIVE (multi-unit faults): when the gate exposes a METRIC and no single
   transform makes it fully pass, KEEP a transform iff it STRICTLY reduces the metric, then
   propose the next ON TOP; stop when the gate fully passes or nothing improves. Resolves faults
   spanning several units that the single-shot version cannot. (Needs the gate's partial order.)
3. PLAN-THEN-EXECUTE: a proposer emits an INERT plan (ordered steps over a fixed action
   vocabulary); the executor runs each step deterministically, each step optionally a Verified
   Transaction. The plan is data; execution is two-plane.

## Generalization (the whole point)
Applies to ANY domain with deterministic transforms + a deterministic verifiable gate:
- code:                gate = test suite                (jaros-code, the coding app)
- config-as-code:      gate = schema / policy validator
- schema/data migration: gate = migration check + data invariants
- infrastructure-as-code: gate = plan-diff / policy check
- data pipelines:      gate = data-quality assertions
- structured docs/specs: gate = structural + link validator
Boundary: NOT applicable where "success" is subjective or non-deterministic (no gate exists).
The power is precisely that the GATE, not a model, decides commit.

## Minimal API sketch (adapt to Jaros's actual tool/executor API)
    result = verified_transaction(
        scope,                 # snapshot-able handle to mutable state
        transform_decisions,   # ordered [Decision] mutating scope (proposed; run via executor)
        gate,                  # Tool -> Verdict{ok, metric?, diagnostics?}
        require_green_first=True,
    )
    # result.committed: bool ; result.verdict: Verdict ; atomic + logged + replayable

    # combinators reduce a candidate list via verified_transaction:
    first_committed = search_with_verify(scope, [transform_a, transform_b, ...], gate)
    solved          = progress_gated(scope, candidate_stream, gate)   # needs verdict.metric
