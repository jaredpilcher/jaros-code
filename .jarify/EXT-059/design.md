# Design — Verification substrate for extensive Python breadth

## Overview

Five small, deterministic, model-free verifiers, each mirroring the proven independence discipline of
`harness/datastore_oracle.py` (clean state → drive the built system as a black box → verify with an
*independent* mechanism the built code never touches). They plug into the same `CreationTask` /
`_run_single_check` seam the existing suite uses, so a broadened-suite task can name whichever oracle
its class needs. No verifier calls the model. Every check runs the built system in a fresh sandbox and
inspects an independent observable (a file tree, exact bytes on stdout, a process exit code, an imported
symbol's return, or a real HTTP exchange). This spec deliberately builds **only** the verifiers — the
broadened-suite task definitions that consume them are a separate, follow-on spec.

## Component map

```text
                        harness/system_suite.py  (CreationTask + _run_single_check dispatch)
                                        |
     +----------------+-----------------+------------------+--------------------+
     |                |                 |                  |                    |
  fs_oracle       exact-eq/rc        import_driver     fixture_server      http_check growth
  (REQ-1)         is-empty (REQ-2)   (REQ-3)           (REQ-4)             (REQ-5, server_oracle)
     |                |                 |                  |                    |
  seed tmp tree   run built sys,     import built      oracle HOSTS a       request body + custom
  -> run built    capture stdout     module in FRESH   localhost fixture    headers + capture
  system sandbox  EXACTLY + exit     subprocess, call  server; built code   Set-Cookie/Location +
  -> independent  code; compare      pinned public     is the CLIENT that   ordered SEQUENCE runner
  byte-for-byte   exact / empty /    API, sentinel-    fetches it; reuse    that THREADS a captured
  tree inspect    rc-expected        grep the result   _free_port/_kill     token/cookie step->step
     |                |                 |                  |                    |
     +----------------+--------- all reuse the sandbox (secure_exec) + _free_port/_kill_tree --------+
                                        |
                            independent observable, NO model call

                                  agent_oracle (REQ-6) -- a DIFFERENT axis: grades ORCHESTRATION
                                        |
     oracle HOSTS a scripted OpenAI-compatible stub-model server (fixed "reasoning") + a
     controlled tool-sandbox endpoint; the built AGENT is the CLIENT/loop under test -- injected
     via the pinned OPENAI_BASE_URL/MODEL_URL + JAROS_TOOL_URL env-var seam (same seam a real
     build points at the Jetson llama.cpp endpoint); asserts the ORDERED tool-call sequence +
     clean termination, never the model's intelligence -- reuses secure_exec's sandboxed launch +
     server_oracle._kill_tree, same as every oracle above

                     state_machine_oracle (REQ-7) / conservation_oracle (REQ-8) /
                     double_entry_oracle (REQ-9) -- a THIRD axis: grades INVARIANT ENFORCEMENT
                                        |
     +----------------------+----------------------+-----------------------------+
     |                      |                      |                             |
  state_machine_oracle   conservation_oracle   double_entry_oracle               |
  (REQ-7)                (REQ-8)               (REQ-9)                          |
     |                      |                      |                             |
  illegal transitions    oversell/overdraw/    an unbalanced entry              |
  must be REJECTED        double-spend must     (debits != credits) must        |
  (e.g. ship-before-pay)  be REJECTED; a        be REJECTED; every accepted    |
  -- accept ops must       conserved quantity     entry's exact int-cents legs   |
  land on the modeled      (stock/points/wallet)  must land on the shadow-       |
  next state               must never drift       tracked account balances       |
     +----------------------+----------------------+-----------------------------+
                                        |
       each renders ONE `api_calls` + `checks` plan and hands it UNMODIFIED to
       `harness.import_driver.drive_import` (fresh sandboxed subprocess, sentinel
       protocol, conjunctive checks gate) -- no reimplementation of import_driver's
       machinery; each maintains its own Python-side "shadow" (state / quantities /
       account balances) to independently verify the built entity's own reads,
       so a build can never grade itself
```

## Key design decisions

- **Independence is the whole point.** The built system's own "Saved!"/"moved"/"200 OK" stdout is never
  trusted. Effects are proven by an independent sqlite/tree/import/HTTP mechanism in a separate process
  boundary — this is what closes the #86-class false-done/false-negative both ways.
- **Reuse the audited primitives.** `fs_oracle`, `fixture_server`, and the http-sequence runner reuse
  `server_oracle._free_port` / `_wait_for_port` / `_kill_tree` and the `secure_exec` sandbox rather than
  re-implementing lifecycle/teardown, so the instrument shares the reviewed code.
- **No oracle leak.** A verifier receives only oracle-chosen inputs and contract-derived expected values;
  the build prompt never sees the concrete check values. Assertions stay schema-agnostic where possible
  (e.g. `count_all_rows`, "a file named X exists with bytes Y") so the builder picks its own internals.
- **Determinism.** No wall-clock: time-dependent checks take an injected clock / logical tick / reference
  argument; ports are always ephemeral (`bind :0`); a timeout doubles as a deterministic deadlock signal.
- **Two-plane.** Every verifier is pure execution plane — deterministic Python, replayable, no Decision
  needed for read-only inspection; any file the verifier writes for seeding goes to a sandbox tmp tree.
- **Invariant enforcement, not just effect presence (REQ-7/8/9).** `state_machine_oracle`,
  `conservation_oracle`, and `double_entry_oracle` share a pinned contract — class-based, driven via
  `harness.import_driver.drive_import` — and a common honesty core: the ILLEGAL/invalid op (an illegal
  state transition, an oversell/overdraw, an unbalanced ledger entry) must be REFUSED, not silently
  allowed, while every LEGAL op must land exactly on a Python-side "shadow" (modeled state / conserved
  quantities / exact-int-cents account balances) that the oracle tracks independently of the built
  entity's own reads — so a build can never grade itself.
