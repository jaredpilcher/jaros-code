# Intent

This spec exists to build the product's headline capability: turning a one-sentence (or a
paragraph, or a conversational) prompt into a complete, working Python SYSTEM — and modifying an
existing one from a sentence. The Prime Directive names the prompt→system build-and-modify CLI as
"not one feature among many; it is the point," and this spec is the PLANNER layer and end-to-end
orchestration on top of the Foundry executor (EXT-035/EXT-008): spec-expansion, architecture,
interface design, ordered leaves-first implementation, per-module and system-level executable
acceptance, cross-level repair, and scale — plus the surrounding agentic substrate Claude Code has
and the product's users need (conversational multi-turn session with resume, short-term context
condensation, per-repo long-term memory, episodic action+rationale memory, a JAROS.md always-
injected instructions file, user-facing tasks and experiments, ask-the-user on ambiguity). It also
carries the parity INSTRUMENTS — held-out, diverse creation and modification suites, a
long-horizon multi-requirement coherence suite, and difficulty-tier escalation — that measure
whether the product is genuinely good at this.

It converges toward the Prime Directive on every axis: it IS the product the whole system exists to
make excellent, it honors two-plane discipline (the model judges the decomposition; a deterministic
plane guarantees structural coherence, runs every acceptance check, and gates every ship), and it
is governed spec-first (Tenet 4) so a long build stays aligned via decompose → build → independent
verify → re-ground. Honesty (Tenet 3) is enforced throughout — executable acceptance never
eyeballed, regression-gated modification, best-of-k/governed floors that guarantee never shipping
worse than a plain build, and honest recording of the measured break-points rather than flattered
scores.
