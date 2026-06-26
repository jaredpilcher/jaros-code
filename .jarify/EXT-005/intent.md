# Intent

This spec exists to be the proof, not the assertion, of PRIME-001's central promise: that
the harness becomes good enough to overcome Gemma 4 2B (`e2b`)'s limits and reach
Claude-Code-on-Opus-4.8 quality. We do not get to claim we are near the bar; the
evaluation harness must measure convergence honestly, run over run, on self-contained
coding tasks and — crucially — on real, recognized public benchmarks (HumanEval first, then
beyond) so the bar is external rather than one we drew ourselves. The metric is the trend,
not a feeling: a pass rate carried with a Wilson confidence interval that tightens as the
suite grows, per-tier scores with a hardening ratchet that escalates difficulty the moment
a tier is mastered (an eval the harness can ace is too easy and MUST be made harder), and a
distinct generative intent-fidelity metric scored against a hidden oracle so we measure
building-from-intent and never just repair. It also surfaces the system's growth census
(agents, tools, evals, specs increasing toward the swarm) and its wiring health (which
agent→tool edges actually fire, which are orphans, whether any change was net-negative) so
the supervisor can run the MEASURE→DIAGNOSE→DISCOVER→PLACE→WIRE→RE-MEASURE→PRUNE loop with
honest signals. Everything it reports must be true (Tenet 3): a failing test is failing, a
tiny suite is flagged as misleading, stagnation is flagged — never a flattering number. It
runs continuously and unattended, on local inference and temp-dir tests only, so
convergence is exercised and proven without pause.
