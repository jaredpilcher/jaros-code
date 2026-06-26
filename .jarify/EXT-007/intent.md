# Intent

This spec exists to govern HOW jaros-code improves itself toward Claude-Code-on-Opus-4.8 —
by the same jarify way it builds anything, serving Tenet 4 of PRIME-001. Improvement is not
ad hoc: it is a living backlog of scoped tasks, implemented one at a time, traced to the
spec, validated, kept green, and committed, with new frontier failures and ideas appended as
new tasks. It encodes the owner's success criteria: agents, tools, and evals must keep
*increasing and improving in quality* over time toward the swarm goal, with the metric trend
(pass rate up, Wilson CI narrowing) as the only proof of progress, and whatever does not help
pruned with the reason recorded. The path to parity runs through MANY specialized
single-purpose agents split by language and domain — never broad catch-alls — each wired by a
router so it actually fires and never becomes an orphan, with wiring telemetry making the
firing visible. And because the system must not be able to lie to itself, every cycle runs a
mechanical honesty audit that flags zero-model-call runs, misleadingly tiny suites, flat-trend
stagnation, and orphan inflation — flags the supervisor must act on, never paper over. Effort
is always aimed at the measured frontier so each change moves the metric most.
