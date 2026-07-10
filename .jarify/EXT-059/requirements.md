---
id: EXT-059
title: Verification substrate for extensive Python breadth
status: partial
priority: high
implementation:
  - harness/fs_oracle.py
  - tests/test_ext059_fs_oracle.py
  - harness/system_suite.py
  - tests/test_ext059_check_variants.py
  - harness/import_driver.py
  - tests/test_ext059_import_driver.py
  - harness/agent_oracle.py
  - tests/test_ext059_agent_oracle.py
  - harness/state_machine_oracle.py
  - tests/test_ext059_state_machine_oracle.py
  - harness/conservation_oracle.py
  - tests/test_ext059_conservation_oracle.py
  - harness/double_entry_oracle.py
  - tests/test_ext059_double_entry_oracle.py
---

### [REQ-1] Filesystem oracle (`fs_oracle`)

A deterministic, model-free verifier that seeds a temporary file tree, runs the built system as a
black box in the sandbox, then inspects the resulting tree **independently and byte-for-byte** — never
trusting the built program's own stdout for the effect. It mirrors `datastore_oracle`'s
clean-state → drive → independently-verify discipline for filesystem effects.

#### Acceptance Criteria
- [x] `harness/fs_oracle.py` provides a callable that: (a) seeds a temp directory from a declarative
      spec (files with given relative paths + byte contents, optional subdirs), (b) runs the built
      entrypoint in that cwd via the existing sandbox with a timeout + process-tree teardown,
      (c) verifies a declarative set of post-conditions against the tree by reading it independently
      (a path exists / is absent; a file's exact bytes; a directory's exact sorted membership).
- [x] Path handling is OS-independent (forward-slash contract, sorted where a task's contract requires
      it) and never leaks host paths into the build prompt.
- [x] A wrong implementation is actually caught (a no-op build, or one that writes the wrong bytes/paths,
      fails), and a correct one passes — proven by tests over both a passing and a failing built stub.

### [REQ-2] Exact-stdout / exit-code / empty-output check variants

Extend the suite's check vocabulary beyond substring-contains to **exact-stdout-equality**,
**expected-exit-code**, and **empty-output** assertions, so error-paths, exact serialization forms, and
n<threshold empty cases are honestly scored.

#### Acceptance Criteria
- [x] New check kinds are dispatchable through the existing `_run_single_check` seam in
      `harness/system_suite.py` (or an imported helper) without breaking existing substring checks.
- [x] `exact_stdout` compares the built system's full stdout for byte/string equality; `expect_rc`
      asserts the process exit code; `empty_output` asserts stdout is empty — each with clear pass/fail.
- [x] Tests prove each variant discriminates: a stub emitting extra output fails `exact_stdout`, a stub
      exiting 0 fails `expect_rc:2`, a stub printing anything fails `empty_output`.

### [REQ-3] Import-driver oracle (`import_driver`)

A verifier that imports a built module/package in a **fresh sandboxed subprocess**, exercises a pinned
public API (call a named function/class with oracle-chosen arguments), and checks the returned value —
for the reusable-library task class that is import-and-call, not stdin→stdout.

#### Acceptance Criteria
- [x] `harness/import_driver.py` runs a driver snippet in a fresh subprocess that imports the built
      module by name, calls the contract-named API, and reports the result via a sentinel the oracle
      greps (never the module's own printing).
- [x] Supports injected dependencies where the contract needs determinism (e.g. an injected clock/sleep
      for retry/cache libraries) so no wall-clock is used.
- [x] Tests prove a correct library passes and a broken one (wrong return / wrong call-count) fails.

### [REQ-4] Fixture-server oracle (`fixture_server`)

The inverse of `server_oracle`: the oracle **hosts** a localhost fixture HTTP server with known
responses, and the built system is the **client** that must fetch/parse/follow it. Reuses the audited
`_free_port` / `_kill_tree` lifecycle primitives.

#### Acceptance Criteria
- [ ] `harness/fixture_server.py` starts a localhost-only fixture server on an ephemeral port serving a
      declared set of routes/bodies/status codes, tears it down cleanly in a `finally`, and exposes its
      base URL to the built client (via argv/env the task contract names).
- [ ] Verifies the built client's stdout/effect against the known fixture content (e.g. extracted title,
      followed next-link chain) with no oracle leak.
- [ ] Tests prove a correct client passes and a non-fetching/mis-parsing stub fails; all egress stays
      loopback-only.

### [REQ-5] HTTP check growth + ordered sequence runner

Grow `server_oracle`'s `http_check` to support **request bodies** (`body`/`json_body`), **custom request
headers** (Authorization/Cookie), **response-header capture** (Set-Cookie/Location), a **no-follow-redirect**
mode, and an **ordered sequence runner** that threads a captured token/code/cookie from one step into the
next — so auth/session/shortener web tasks are gradeable.

#### Acceptance Criteria
- [ ] `http_check` dicts accept a request body and custom request headers, and can capture a named
      response header for reuse.
- [ ] A sequence runner executes an ordered list of checks against one running server, threading a
      captured value (token/cookie/location) from an earlier step into a later step's request.
- [ ] Redirects can be asserted (status + `Location`) without being auto-followed.
- [ ] Tests prove a cookie/token round-trip sequence passes for a correct server and fails when the
      server ignores the credential; existing FastAPI/Flask serve-and-check remains green.

### [REQ-6] Agent-loop oracle (`agent_oracle`)

A deterministic, model-free verifier that grades a built AGENT's ORCHESTRATION, not its reasoning:
agent systems (multi-step tool-calling loops -- jaros-code itself is one) are now a high-priority
real-system class, and today's black-box CLI/import/HTTP oracles have no way to grade one honestly.
An agent's REASONING is non-deterministic, but its CONTROL FLOW is deterministic given a FIXED
model -- so this oracle injects a SCRIPTED stub model server + a controlled tool sandbox, drives a
goal through the built agent's real loop, and asserts the resulting ordered tool-call sequence and
termination.

#### Acceptance Criteria
- [x] `harness/agent_oracle.py` hosts a local, scripted, OpenAI-compatible chat-completions stub
      server (stdlib `http.server`) that serves canned assistant turns (tool-call or final-answer)
      in sequence, plus a controlled tool-sandbox endpoint that records every tool invocation the
      built agent makes (name + args, in order) and returns a canned observation.
- [x] `drive_agent(root, entry, *, script, tools, goal, env=None, max_steps=..., startup_timeout=...,
      python_exe=...)` points the built agent at the stub via the pinned `OPENAI_BASE_URL`/
      `MODEL_URL` env-var contract (the cloud-standard OpenAI-compatible convention -- the SAME
      seam a real build points at the local Jetson llama.cpp endpoint), runs it as a real
      subprocess, and returns the ordered captured tool-calls, the agent's final answer, the step
      count, and whether the loop terminated cleanly -- NEVER raises, ALWAYS tears the stub server
      down in a `finally` block, and leaves no orphaned process or listening port.
- [x] `check_agent(result, *, expect_tool_calls, expect_final_contains=None, expect_terminated=True)`
      is a pure, never-raise grader asserting the captured tool-call sequence (name + args) matches
      expectations, the loop terminated (didn't hit `max_steps`), and the final answer contains the
      expected text.
- [x] Tests prove a correct hand-written agent fixture passes (a multi-step tool-call-then-final
      loop, with the tool's observation threaded back into the loop) and a broken fixture (wrong
      tool call, or one that never terminates) is caught by `check_agent`; `drive_agent` never
      raises on a crashing or hanging agent and leaves the stub port free afterward.

**Follow-up (not built here):** a Jaros-flavor extension that additionally asserts two-plane
Decision-emission and `jaros replay` byte-identical determinism for built agents.

### [REQ-7] State-machine / lifecycle oracle (`state_machine_oracle`)

A deterministic, model-free verifier that grades whether a built system enforces a legal STATE
MACHINE — the highest-leverage substrate gap across every lifecycle-shaped vertical (order,
shipment, fulfillment, RMA, prescription, claim, dispute, moderation, appointment, subscription).
The honesty core: illegal transitions (ship an unpaid order, cancel a delivered one) MUST be
REJECTED, not silently allowed — a system that permits an illegal transition FAILS the check even
if every legal transition also works.

#### Acceptance Criteria
- [x] `harness/state_machine_oracle.py` accepts a declarative state-machine spec (`states`,
      `initial`, `transitions` mapping `from_state + action -> to_state` — anything unlisted is
      illegal) and an ordered `drive` script of ops (`action` + `args` + `expect: "accept" |
      "reject"`), then drives a built class-based entity (reusing `harness.import_driver.drive_import`)
      through the script.
- [x] Each `expect:"accept"` op must succeed AND move the modeled state to the spec's next state;
      each `expect:"reject"` op must be REFUSED (raise, or a documented failure return with no state
      change) — an illegal transition that is silently allowed is a FAILURE, not a pass.
- [x] The final state after the whole script must match `expect_final`.
- [x] Never raises: a missing/uncallable entity, a crashing fixture, or a malformed spec is an honest
      `ok=False` with a diagnostic note.
- [x] Tests prove a correct order-lifecycle fixture passes, a fixture that ALLOWS an illegal
      transition (e.g. ship-before-pay) is CAUGHT (`accepted=False`), a fixture reaching the wrong
      final state fails, and the oracle never raises on a crashing/garbage fixture.

**Follow-up (not built here):** a service-based variant driving transitions over HTTP via
`harness/server_oracle.py`'s launch/request lifecycle instead of `import_driver`.

### [REQ-8] Conservation / no-oversell invariant oracle (`conservation_oracle`)

A deterministic, model-free verifier that grades whether a built system preserves a CONSERVED
quantity (inventory stock, WMS bin counts, refund/return balances, loyalty points, escrow, wallet
balances) under a driven operation sequence -- unblocks ~17 classes across verticals. The honesty
core: operations that would VIOLATE conservation (oversell more units than available, overdraw a
balance, double-spend) must be REJECTED, not silently allowed.

#### Acceptance Criteria
- [x] `harness/conservation_oracle.py` accepts a declarative spec (`quantities` -- named zero-arg
      entity reader methods; `initial` -- a dict of quantity name -> starting value; a `drive`
      script of ops (`action` + `args`/`kwargs` + `expect: "accept"|"reject"`, each `accept` op
      declaring `deltas` per quantity that must sum to zero -- the conservation law encoded
      structurally in the spec); `expect_final` -- the modeled quantities at the end), then drives a
      built class-based entity (reusing `harness.import_driver.drive_import`, import-only, no
      reimplementation) through the script.
- [x] Each `expect:"accept"` op must succeed AND every quantity reader must read back the
      shadow-tracked value after applying that op's deltas (so the conserved total never silently
      drifts); each `expect:"reject"` op (would oversell/overdraw/double-spend) must be REFUSED
      (raise) with every quantity reader UNCHANGED -- an operation that would violate conservation
      but is silently allowed is a FAILURE, not a pass.
- [x] The final quantities after the whole script must match `expect_final`.
- [x] Never raises: a missing/uncallable entity, a crashing fixture, or a malformed spec (including
      an internally inconsistent spec whose declared deltas do not sum to zero) is an honest
      `ok=False`/`accepted=False` with a diagnostic note.
- [x] Tests prove a correct inventory-reservation fixture passes, a fixture that ALLOWS overselling
      beyond available stock is CAUGHT (`accepted=False`) -- the flagship honesty test, a fixture
      that silently loses/creates units on a legal op fails, a fixture reaching the wrong final
      quantities fails, and the oracle never raises on a crashing/garbage fixture.

**Follow-up (not built here):** a concurrent/interleaved-ops variant and an HTTP-service-driven
variant.

### [REQ-9] Double-entry-balance invariant oracle (`double_entry_oracle`)

A deterministic, model-free verifier that grades whether a built accounting system preserves the
DOUBLE-ENTRY invariant (ledgers, journals, general-ledger accounts, wallets, escrow accounts,
statements -- unblocks ~16 fintech/accounting classes, the #4 and last of the atlas's top-four
highest-leverage oracles). The honesty core: an entry whose debit legs and credit legs do not sum
to the same total (an UNBALANCED entry) must be REJECTED, not silently posted, and total debits
must always equal total credits.

#### Acceptance Criteria
- [x] `harness/double_entry_oracle.py` accepts a declarative spec (`accounts` -- named zero-arg
      entity reader methods each returning an exact integer-cents signed balance; `initial` -- a
      dict of account name -> starting integer-cents balance; `post_method` -- the posting method
      name; a `drive` script of journal-entry ops (`legs` -- each a `{"account", "debit"|"credit"}`
      dict in integer cents -- plus `expect: "accept"|"reject"`, where every `accept` op's legs
      must sum to zero once translated to signed per-account deltas -- Sigma(debits)==Sigma(credits)
      encoded structurally in the spec -- and every `reject` op's legs must NOT sum to zero);
      `expect_final` -- the modeled account balances at the end), then drives a built class-based
      entity (reusing `harness.import_driver.drive_import`, import-only, no reimplementation)
      through the script.
- [x] Each `expect:"accept"` op must post without raising AND every account reader must read back
      the shadow-tracked exact-cents balance after applying that entry's signed leg deltas; each
      `expect:"reject"` op (a genuinely UNBALANCED entry) must be REFUSED (raise) with every account
      reader UNCHANGED -- an unbalanced entry that is silently posted is a FAILURE, not a pass.
- [x] Money is exact: every spec value (`initial`/leg amounts/`expect_final`) must be a plain
      integer number of cents, never `float`/`bool` -- so a built entity that drifts into float
      arithmetic internally is caught by the resulting exact-equality mismatch.
- [x] The final account balances after the whole script must match `expect_final`; because every
      accepted entry's legs balance, the ledger-wide invariant (Sigma of all debit legs across the
      whole script equals Sigma of all credit legs) holds structurally and is verified dynamically
      via the same per-account balance checks.
- [x] Never raises: a missing/uncallable entity, a crashing fixture, or a malformed spec (including
      an `accept` op whose legs don't balance, or a `reject` op whose legs DO balance) is an honest
      `ok=False`/`accepted=False` with a diagnostic note.
- [x] Tests prove a correct two-account ledger fixture passes, a fixture that ACCEPTS an unbalanced
      entry is CAUGHT (`accepted=False`) -- the flagship honesty test, a fixture with wrong balance
      math (double-applies a leg) fails, a fixture that violates the ledger-wide debits==credits
      invariant (silently drops credit legs) fails, and the oracle never raises on a crashing/
      garbage fixture.

**Follow-up (not built here):** a running `total_debits()`/`total_credits()` reader-pair variant, a
multi-currency variant, and an HTTP-service-driven variant.
