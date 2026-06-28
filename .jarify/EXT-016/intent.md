# EXT-016 — Tool-Use-Judgment Eval (Diagnosis: where does the 2B judge err?)

## Why

Task #20 showed that the non-deterministic 2B ORCHESTRATOR is at parity with the deterministic
fix-loop (~17 vs 19/18 on the honest 101-bar). The lever (PRIME intent) is GROUNDING the judge,
not trusting it. To ground it we must first DIAGNOSE where the 2B judge errs.

This spec builds a small HELD-OUT eval that scores the orchestrator's JUDGMENT directly — not
end-to-end pass rate. The 2B judge is `_judge_revision` in `harness/behavioral_solve.py`: given
a FAILED-solve state (intent + failure feedback), it picks the next revision action from the
real action space: `{code, gherkin, repair, done}`.

## The eval design

A scenario = a realistic FAILED-solve state (intent + feedback string describing the failure)
paired with the DETERMINISTICALLY-CORRECT next action (the expected-action oracle). The runner
loads the scenarios, calls the real 2B judge, parses the returned action, and scores chosen-vs-expected.
Output: per-scenario table (scenario / expected / got / ok) + accuracy % + per-class breakdown.

## What it feeds

The per-class breakdown from this eval directly feeds the grounding work (#12 — task after #21):
which failure classes the judge gets right/wrong becomes the ranked list of interventions to try
(e.g. "judge never picks `repair` — ground it with a deterministic syntax-check first").

## Honest / held-out

Scenarios are GENERIC plausible failures, NOT fitted to any benchmark item or to make the 2B
look good or bad. They must remain held out from any tuning of the judge prompt — the eval is
a diagnostic, not a training target.
