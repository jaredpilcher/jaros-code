---
id: EXT-011
title: Commit-Replay Evaluation
status: covered
priority: high
implementation:
  - file: harness/commit_replay_eval.py
    ranges:
      - - 1
        - 1
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
