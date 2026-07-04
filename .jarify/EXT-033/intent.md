# Intent

This spec exists to answer, honestly and end-to-end, the one question the multi-model pivot
raises but does not itself settle: does routing each problem to its measured-best model actually
BEAT running everything on the single default model? It builds the capstone evaluation that runs
the deterministic router + coverage tally over a real benchmark slice, solves each task with the
routed model's adaptation, and compares the routed pass-rate against a fixed single-model baseline
on the SAME task list — with Wilson95 confidence intervals and a per-task table showing exactly
which model each task went to, so the number is transparent rather than a black box.

It converges toward the Prime Directive's honesty commitment (Tenet 3) as sharpened by the
external review: the system-level "no ceiling" is a *reachability* claim, never a performance
claim, so the roster only earns its cost when routed performance is measured against the best
single model — and "significant lift" is reported ONLY when the confidence intervals genuinely
separate, with CI overlap plainly called "no lift." It is the instrument that keeps the
multi-model bet accountable to evidence, and its deterministic default-model restore keeps the
Jetson serving state honest between runs.
