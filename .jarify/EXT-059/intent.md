# Intent

This spec exists to build the **verification substrate** the harness is missing to honestly measure —
and therefore to improve — the model's ability to build the *breadth* of common Python systems. The
2026-07-08 taxonomy of ~90% of everyday Python (a ~66-task suite across 13 domains) surfaced one
decisive finding: the blocker to covering that breadth is **not the model — it is that most of those
task classes cannot even be *scored honestly* today.** The existing suite oracle only checks
substring-in-stdout; it cannot verify file-tree effects, exact output, exit codes, importable library
APIs, or HTTP request/response bodies with header/cookie threading. Without independent behavioral
oracles for those classes, a "green" would either be unmeasurable or fakeable — a Tenet-3 violation.

This spec builds small, deterministic, **model-free** verifiers that close that gap: a filesystem
oracle (seed a tree → run the built system sandboxed → inspect the tree independently, byte-for-byte),
exact-stdout / exit-code / empty-output check variants, an import-driver (exercise a built module's
pinned public API in a fresh subprocess), a fixture-server oracle (the oracle hosts the server, the
built code is the client), and richer HTTP checks (request bodies, custom headers, response-header
capture, and an ordered sequence runner that threads a captured token/cookie step-to-step).

It converges toward the Prime Directive by making the breadth of real Python systems **honestly
measurable** — the precondition for driving the model+harness (Tenet 2, small-local-only) to genuinely
build them (not green them via hand-written leaves), verified reproducibly and without oracle leak
(Tenet 3). Every verifier is pure execution plane (Tenet 1): no model call, deterministic, replayable.
