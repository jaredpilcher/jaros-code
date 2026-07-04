# Intent

This spec exists to answer a specific diagnostic question honestly: on the hard repo tasks the
model fails greedily, is the bottleneck REASONING (it can't plan the fix) or CODING (it can't
emit correct code even given a plan)? The decomposition probe tests the two-phase
decompose-then-implement hypothesis — first prompt the model for a granular numbered
implementation plan, then prompt it to implement following that plan as scaffolding — and
scores it head-to-head against the monolithic greedy baseline via the hidden red→green oracle.
The verdict it produces steers where harness effort should go next: if planning helps, the wall
is reasoning and decomposition scaffolds are worth building; if both score zero, the wall is
raw generation and the class must be routed elsewhere.

It converges toward the Prime Directive by embodying the "probe before build / diagnose, don't
guess" velocity doctrine and the escalation ladder's L1 decomposition rung — buying information
per Jetson-hour rather than assuming a cause. It upholds Tenet 3 rigorously: the oracle is
invoked only after both plan and implementation are generated, never shown to the model, and
the result is reported with a Wilson CI and an explicit HELPS/NO-GAIN verdict, so a negative is
a valid, informative finding rather than a hidden failure.
