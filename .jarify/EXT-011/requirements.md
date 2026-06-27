---
id: EXT-011
title: Commit-Replay Evaluation
status: partial
priority: high
implementation:
  - file: harness/commit_replay.py
    ranges:
      - - 114
        - 144
      - - 284
        - 311
      - - 405
        - 447
  - file: tests/test_ext011_container_lifecycle.py
    ranges:
      - - 1
        - 173
---

### [REQ-1] Reproducible environment (the hard part)

ONE repo (`more-itertools`), tests run **deterministically** in a pinned env (Docker image; pinned
Python + test deps). The SAME test command yields the SAME result across runs. No host-Python drift.

#### Acceptance Criteria
- [ ] Run tests inside a pinned Docker image with pinned Python and test dependencies
- [ ] Verify the same test command yields the same result across repeated runs
- [ ] Eliminate host-Python drift from the evaluation environment

### [REQ-2] Commit mining + BRUTAL filter

Walk history. Keep a commit ONLY if: (a) it touches code (`more_itertools/*.py`), AND (b) its touched
tests **fail at the parent** and **pass at the commit** (validated, not assumed). DROP and **log with
reason** (no silent truncation): merges; dependency bumps; pure formatting/whitespace; renames;
generated code; data/doc-only; commits whose **message under-specifies** the change (diff carries info
the message lacks → unsolvable-in-principle from the message). Emit a drop ledger: `{reason: count}`.

#### Acceptance Criteria
- [ ] Walk repository history and select commits that touch `more_itertools/*.py`
- [ ] Keep a commit only when its touched tests fail at the parent and pass at the commit (validated)
- [ ] Drop merges, dependency bumps, formatting/whitespace, renames, generated/data/doc-only commits
- [ ] Drop commits whose message under-specifies the change (unsolvable from the message alone)
- [ ] Emit a drop ledger of `{reason: count}` with no silent truncation

### [REQ-3] Oracle = red→green, never diff-match

Solved iff: at parent the touched test(s) FAIL, and after the harness's change the SAME test(s) PASS
(and no previously-passing test in the touched file regresses). NEVER compare against the original diff.

#### Acceptance Criteria
- [ ] Mark a commit solved only when the touched test(s) fail at parent and pass after the change
- [ ] Verify no previously-passing test in the touched file regresses
- [ ] Never compare the harness output against the original commit diff

### [REQ-4] Honest baseline + Wilson CI

Report the raw real-repo pass@1 (no new jigs) with a **Wilson 95% CI**. Reproducible — never report a
number that can't be re-derived. Report the drop ledger alongside (denominator transparency).

#### Acceptance Criteria
- [ ] Report raw real-repo pass@1 with no new jigs applied
- [ ] Report a Wilson 95% confidence interval for the pass rate
- [ ] Ensure every reported number is reproducible / re-derivable
- [ ] Report the drop ledger alongside the pass rate for denominator transparency

### [REQ-5] Convergence loop + generalization gate

Each failure → DISCOVER (probe raw output, name the failed grain) → supervisor authors a deterministic,
test-gated jig. **Generalization gate:** a new jig must lift pass rate on **held-out commits of the
same class it never saw**, else revert (memorization). Never net-negative on held-out.

#### Acceptance Criteria
- [ ] On each failure, probe the raw model output and name the failed grain
- [ ] Author a deterministic, test-gated jig for the diagnosed failure class
- [ ] Gate each new jig on held-out commits of the same class it never saw
- [ ] Revert any jig that does not lift the held-out pass rate (memorization) or is net-negative

### [REQ-6] Easy→hard ordering

Order surviving commits by difficulty (e.g. lines/files touched, hunks) so primitives precede hard
cases; split into dev (jig-building) and **held-out** (generalization-gating) sets by commit, never
leaking.

#### Acceptance Criteria
- [ ] Order surviving commits by a difficulty proxy (lines/files touched, hunks) so primitives come first
- [ ] Split commits into a dev (jig-building) set and a held-out (generalization-gating) set
- [ ] Partition by commit so no commit leaks between the dev and held-out sets

### [REQ-7] Robust self-test execution — per-test timeout + guaranteed container cleanup

The self-test runner (`_run_selftests`) that executes the 2B's Gherkin-derived scaffolding tests
in Docker MUST guarantee container cleanup under all exit conditions — normal exit, subprocess
timeout, and any unhandled exception. Orphaned containers (burning CPU for hours, blocking the
whole eval) are a defect.

#### Acceptance Criteria
- [x] Each `_run_selftests` invocation launches its container with an explicit unique `--name`
      (derived from `uuid4`) so it can be targeted for cleanup regardless of host-process state
- [x] On `subprocess.TimeoutExpired`, explicitly call `docker kill <name>` then `docker rm -f <name>`
      BEFORE returning `(False, "timeout")` — do not rely on `--rm` alone (which does not fire when
      the host `docker run` process is killed mid-run)
- [x] A `finally` block unconditionally calls `docker rm -f <name>` for belt-and-suspenders cleanup
      on every exit path (normal, timeout, exception)
- [x] The helper never raises: `_docker_force_remove` swallows all errors (container already gone
      is a no-op)
- [x] `--stop-timeout 5` is passed to Docker so the container's stop grace period is bounded
- [x] Wall-clock timeout (~25–120 s) is maintained on every call-site; a timed-out self-test
      = fail, eval continues (behavior unchanged)
- [x] Isolation test verifies: a deliberately-hanging container (`sleep 600`) started with the
      same image is killed and fully removed by `_docker_force_remove` within 10 s; `docker ps -a`
      shows no trace of it afterwards
- [x] Isolation test verifies: `_run_selftests` with a 3 s timeout against a hanging test returns
      `(False, "timeout")` and leaves zero `jaros_selftest_*` containers in `docker ps -a`

### [REQ-8] Robust oracle red-green execution — per-test timeout + guaranteed container cleanup

The oracle runner (`_run_nodes` and `_run_nodes_fb`) that scores the 2B's candidate code by
running the repo's ACTUAL tests (the red→green hidden oracle) MUST guarantee container cleanup
under all exit conditions. An infinite-loop candidate (e.g. `exactly_n`) that reaches the oracle
previously orphaned a container at 100% CPU and stalled the entire eval (bug #15, observed live
2026-06-26: orphaned container 'infallible_newton' had to be killed manually).

#### Acceptance Criteria
- [x] Each `_run_nodes` / `_run_nodes_fb` invocation launches its Docker container with an
      explicit unique `--name jaros_oracle_<uuid4-hex[:12]>` so it can be targeted for cleanup
      regardless of host-process state
- [x] `--stop-timeout 5` is passed to Docker so the container's stop grace period is bounded
- [x] On `subprocess.TimeoutExpired`, `_docker_force_remove(cname)` is called before returning
      (the timed-out candidate = all nodes red; eval proceeds normally — scoring logic unchanged)
- [x] A `finally` block unconditionally calls `_docker_force_remove(cname)` for
      belt-and-suspenders cleanup on every exit path (normal, timeout, exception)
- [x] Wall-clock timeout (default 180 s, caller-overridable) is enforced on every invocation
- [x] Isolation test (`test_run_nodes_timeout_leaves_no_orphan`): `_run_nodes` against a
      deliberately-hanging test (sleep 600) with a 3 s timeout returns the node as red (timed-out
      candidate fails) AND leaves zero `jaros_oracle_*` containers in `docker ps -a` within 10 s
