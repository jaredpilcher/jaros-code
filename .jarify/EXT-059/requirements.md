---
id: EXT-059
title: Verification substrate for extensive Python breadth
status: partial
priority: high
implementation:
  - harness/fs_oracle.py
  - tests/test_ext059_fs_oracle.py
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
- [ ] New check kinds are dispatchable through the existing `_run_single_check` seam in
      `harness/system_suite.py` (or an imported helper) without breaking existing substring checks.
- [ ] `exact_stdout` compares the built system's full stdout for byte/string equality; `expect_rc`
      asserts the process exit code; `empty_output` asserts stdout is empty — each with clear pass/fail.
- [ ] Tests prove each variant discriminates: a stub emitting extra output fails `exact_stdout`, a stub
      exiting 0 fails `expect_rc:2`, a stub printing anything fails `empty_output`.

### [REQ-3] Import-driver oracle (`import_driver`)

A verifier that imports a built module/package in a **fresh sandboxed subprocess**, exercises a pinned
public API (call a named function/class with oracle-chosen arguments), and checks the returned value —
for the reusable-library task class that is import-and-call, not stdin→stdout.

#### Acceptance Criteria
- [ ] `harness/import_driver.py` runs a driver snippet in a fresh subprocess that imports the built
      module by name, calls the contract-named API, and reports the result via a sentinel the oracle
      greps (never the module's own printing).
- [ ] Supports injected dependencies where the contract needs determinism (e.g. an injected clock/sleep
      for retry/cache libraries) so no wall-clock is used.
- [ ] Tests prove a correct library passes and a broken one (wrong return / wrong call-count) fails.

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
