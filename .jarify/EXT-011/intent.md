# EXT-011 — Commit-Replay Evaluation (the real frontier)

## Why

Single-function pass@1 (HumanEval 82.3%, MBPP) is high **NOT because the 2B is maxed out — THERE IS NO
MODEL CEILING** (PRIME-001 / the founding assumption). It's high because the harness is already *mature*
on that one narrow shape. **"Saturated" and "ceiling" remain forbidden conclusions** — the residual
single-function failures are still harness gaps, and the much larger headroom is simply elsewhere: on
**real repository commit histories**, where the harness is *thin*. Every failure there, as everywhere,
is a harness issue to be engineered away — never a statement about the model.

The unmeasured, high-value, **publishable** number is: given a real codebase at a parent commit and the
intent of a real change, can the local 2B harness make a change that turns the touched tests
**red→green**? This is measured across **MULTIPLE real repos, and we keep adding more indefinitely** —
the frontier widens as we go, and every repo we can't yet solve is a harness gap to close.

This number will be **published**, so it must be **true**: honest baseline, reproducible env, brutal
filtering with a logged drop count, Wilson CI, and revert-anything-net-negative-on-held-out.

## What

A commit-replay eval, built incrementally on **ONE** fully reproducible real repo first
(`more-itertools` — important on PyPI, pure-Python, focused functions+tests = clean red→green commits).
Not general yet — environment reproduction is the hard part, so nail it for one repo.

- **Oracle = the repo's own tests going red→green**, NEVER exact-diff-match (many correct
  implementations differ from the original). Solved iff the touched tests FAIL at the parent commit
  and PASS after the harness's change.
- **Filter brutally** to commits that (a) touch code AND (b) have tests fail-before/pass-after. Drop
  merges, dep bumps, formatting, renames, generated code, data files, and commits whose message
  under-specifies the change (the diff carries information the message doesn't — unsolvable in
  principle from the message, not a harness failure). **Log every drop (count + reason). No silent
  truncation.**
- Run surviving commits **easy→hard** (primitives before hard cases).
- **First deliverable:** the filtered harness running on one repo with an **honest baseline pass rate
  (no new jigs yet)** — so we know what fraction of real history is even cleanly checkable.

Then the convergence loop: the local 2B + existing jigs attempt each commit; each failure is a DISCOVER
step (probe the raw output, diagnose the failed grain); the supervisor (build-time, me) authors the
missing **deterministic, test-gated** tool/agent. Runtime stays **local-only**.

**Generalization gate (non-negotiable):** any new jig must lift the pass rate on **held-out commits of
the same class it never saw** — not just the one commit it was built for. If it only fixes its target,
that's memorization → revert. This is capability vs. a lookup table.

## Honesty constraints before any number goes public (a skeptic will hit both)

1. **No visible-test leakage.** The HEADLINE number is **intent-only**: the model gets the commit
   message + parent code, NOT the test it is scored on (true SWE-bench style — not gameable, the 2B
   cannot hardcode assertions it never sees). A `test-as-spec` number (failing test shown + iterated
   against) may be reported ONLY as a clearly-labeled **TDD upper bound**, never as the headline; and
   any test-shown solution's overfitting must be measured (does it still pass when the visible asserts
   are held out / does it regress the rest of the file). Do not publish until this is satisfied.
2. **Honest scope.** This is the **single-function-localizable** subset only — the localizer targets a
   changed top-level function, so multi-function / cross-file / class-method commits are out of reach
   BY CONSTRUCTION and counted as failures (not hidden). Always state n and the Wilson CI (n is small,
   CI wide). The number is per-repo until the **multi-repo expansion lands** — never generalize from
   one repo. Framing must literally say "single-function-localizable commits, one repo, n=…".
