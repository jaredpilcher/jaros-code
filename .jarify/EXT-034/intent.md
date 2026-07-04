# Intent

This spec exists to give the pursuit its external, recognized hard bar: an adapter for
SWE-bench-Lite, the public benchmark of real GitHub issue-fixing on real repositories. The
authored suites can be aced and hardened, but only an external benchmark proves parity on
genuinely hard problems we did not design. This spec builds the offline scaffold to load
instances, form an inert solve-input a model can act on, produce a candidate unified-diff patch
(locate → read → model-edits-the-file-body → deterministically form the diff via difflib, because
a small model cannot reliably emit raw diff syntax), and deterministically score whether a patch
resolves the instance by the FAIL_TO_PASS / PASS_TO_PASS test oracle.

It converges toward the Prime Directive on two axes. First, the honest-measurement commitment
(Tenet 3) is load-bearing here as an absolute invariant: the gold patch and hidden test_patch are
oracle-only and NEVER enter the solve input — one leaked answer would corrupt the only signal we
have. Second, it maps the small-model reasoning frontier honestly rather than flattering it:
SWE-bench-Lite is a hard multi-step-repo class expected to route/escalate to a stronger
Jetson-fitting model, and its resolved-rate is recorded as measured, wall or lift alike.
