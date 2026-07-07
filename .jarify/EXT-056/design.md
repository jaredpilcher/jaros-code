# Design — Deterministic Verification Toolset

## The governing frame

A hard-class build failure is never conceded as a model ceiling. It is diagnosed as a **missing
deterministic tool** — the harness failed to (a) make the failure mode **visible**, (b) **localize**
it, and (c) **feed it back** to the model as a concrete sub-judgment. The 2B reliably fixes a bug it
can *see* (raw-probe proven); the job of this toolset is to surface, localize, and route bugs the
current acceptance signal is blind to.

The evidence that pins the first tool: `bestofk_oracle_lift.py` measured best-of-k as **net-negative
(-3/20)** on the creation suite because selection early-exits on a self-derived acceptance proxy that
is **blind to semantic-ordering** (dequeue order, TTL expiry). Selection on a blind proxy amplifies
the blind spot. The lever is NOT more sampling and NOT a bigger model — it is a deterministic tool
that makes the ordering/behavioral failure **visible**.

## REQ-1: The ADT differential oracle

New module `harness/adt_oracle.py` — a **sibling of `harness/datastore_oracle.py`**: pure stdlib,
**NEVER raises** (any internal error → an inconclusive `AdtResult`, never a build failure), and
makes **no model call**. Four deterministic stages:

```text
        built system (root, entry_path, spec text, module list)
                                │
     ┌──────────────────────────┴───────────────────────────┐
     │  STAGE 1  CLASSIFY                                     │
     │  fingerprint method names + spec keywords →            │
     │  at most ONE canonical ADT, or None (non-ADT → skip)  │
     │    lru | priority-queue | ttl-store | fifo | ring-buf │
     └──────────────────────────┬───────────────────────────┘
                                │ cls (or None → inconclusive, no-op)
     ┌──────────────────────────┴───────────────────────────┐
     │  STAGE 2  REFERENCE MODEL                             │
     │  ~15-30 line textbook stdlib impl for cls:            │
     │    lru → OrderedDict     priority → heapq+seq-counter │
     │    ttl → dict+virtual-clock   fifo → deque            │
     │  built from the VISIBLE spec's ops — NEVER hidden tests│
     └──────────────────────────┬───────────────────────────┘
                                │ reference model
     ┌──────────────────────────┴───────────────────────────┐
     │  STAGE 3  SEEDED SEQUENCE                             │
     │  fixed-PRNG (seed param) op sequence that STRESSES    │
     │  boundaries: capacity eviction, tie-break order,      │
     │  expiry edges, wrap-around. Replayable byte-for-byte. │
     └──────────────────────────┬───────────────────────────┘
                                │ ops = [(name, args), ...]
     ┌──────────────────────────┴───────────────────────────┐
     │  STAGE 4  DIFFERENTIAL DRIVE + FIRST-DIVERGENCE       │
     │  for each op: apply to reference AND to built CLI      │
     │  (via system_suite._run_cli, sandboxed);              │
     │  compare observable result. On first mismatch, STOP    │
     │  and report: op index, op name+args, expected, actual │
     │  → the localized witness.                             │
     └──────────────────────────┬───────────────────────────┘
                                │
                          AdtResult(applicable, cls, ok,
                                    first_divergence, detail)
```

### Seam into acceptance (union-only → sacred-safe)

```text
system_builder.build_system
      │
      ├─ _minimum_acceptance(...)            # harness/system_builder.py:1109
      │      ├─ usage / per-command / smoke  (REQ-26 deterministic floor)
      │      ├─ _roundtrip_acceptance_check  (line ~1149)  ── existing
      │      └─ adt_oracle.verify(...)       ── NEW (REQ-1), appended here
      │
      └─ _compose_acceptance_checklist(...)  # line 1154
             de-dup by (name, code) UNION    → strictly-stricter set
             (a new check can only ADD a way to FAIL → done can only go
              True→False; 0-false-done invariant preserved by construction)
```

The oracle contributes one extra acceptance check when (and only when) STAGE 1 classifies the build
as a known ADT. When it returns `applicable=False` (non-ADT, or inconclusive), it adds **nothing** —
a pure no-op, never a false failure. Feed-back needs **no new wiring**: a failing acceptance check
already flows through `_system_repair_loop` (the concrete divergence witness becomes the repair
prompt) and the REQ-34 replan path. This **supersedes REQ-37** (the model-authored property check,
measured default-off because the 2B can't write those checks) — the reference model is authored
deterministically by the harness, not by the model.

## The complete set (forward plan — future REQs)

REQ-1 is the enabler the rest depend on (the differential-drive + first-divergence spine). The ranked
remainder of the "complete set," to be added as future requirements + roadmap items:

```text
  rank  tool                              makes-visible / localizes
  ────  ────────────────────────────────  ──────────────────────────────────────
   1    adt-differential-oracle  (REQ-1)   semantic-ordering divergence, localized
   2    structural-invariant-harness       repOk/class-invariant violation point
   3    sbfl-ochiai-localizer               statement-level fault suspiciousness
   4    delta-debugging-minimizer (ddmin)   minimal failing op sequence
   5    runtime-trace-capturer              concrete state at the divergence
   6    stratified-symbol-localizer         narrow the culprit symbol/function
   7    dynamic-invariant-differ (Daikon)   inferred-invariant break between draws
   8    spec-command-grammar-extractor      declared-ops grammar for seq generation
   9    comprehension-fact-injector         hand the one missing fact, test the flip
  10    contract-decomposer                 pre/post-condition sub-judgments
```

Each is a two-plane tool (deterministic work in the tool, narrow judgment for the model) and each
must be proven on a **held-out** class before it is kept — never overfit a benchmark item (Tenet 3).
