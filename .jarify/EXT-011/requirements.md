# EXT-011 Requirements — Commit-Replay Evaluation

## REQ-1 — Reproducible environment (the hard part)
ONE repo (`more-itertools`), tests run **deterministically** in a pinned env (Docker image; pinned
Python + test deps). The SAME test command yields the SAME result across runs. No host-Python drift.

## REQ-2 — Commit mining + BRUTAL filter
Walk history. Keep a commit ONLY if: (a) it touches code (`more_itertools/*.py`), AND (b) its touched
tests **fail at the parent** and **pass at the commit** (validated, not assumed). DROP and **log with
reason** (no silent truncation): merges; dependency bumps; pure formatting/whitespace; renames;
generated code; data/doc-only; commits whose **message under-specifies** the change (diff carries info
the message lacks → unsolvable-in-principle from the message). Emit a drop ledger: `{reason: count}`.

## REQ-3 — Oracle = red→green, never diff-match
Solved iff: at parent the touched test(s) FAIL, and after the harness's change the SAME test(s) PASS
(and no previously-passing test in the touched file regresses). NEVER compare against the original diff.

## REQ-4 — Honest baseline + Wilson CI
Report the raw real-repo pass@1 (no new jigs) with a **Wilson 95% CI**. Reproducible — never report a
number that can't be re-derived. Report the drop ledger alongside (denominator transparency).

## REQ-5 — Convergence loop + generalization gate
Each failure → DISCOVER (probe raw output, name the failed grain) → supervisor authors a deterministic,
test-gated jig. **Generalization gate:** a new jig must lift pass rate on **held-out commits of the
same class it never saw**, else revert (memorization). Never net-negative on held-out.

## REQ-6 — Easy→hard ordering
Order surviving commits by difficulty (e.g. lines/files touched, hunks) so primitives precede hard
cases; split into dev (jig-building) and **held-out** (generalization-gating) sets by commit, never
leaking.
