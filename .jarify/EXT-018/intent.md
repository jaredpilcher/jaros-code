# Intent

This spec exists to add *gated* reasoning to the repo-code solve grain: rather than always
paying the cost of a slow `<think>` generation, the harness first tries a fast direct code
generation, checks it against the target function's VISIBLE docstring examples, and only
spends a single deliberate reasoning pass when that cheap check fails. This targets the
common case where the direct answer is already correct (no reason to think) while reserving
extra effort for the functions that genuinely need it — a deterministic, self-gated use of
the model's limited reasoning budget. It is wired as an opt-in `--think` flag so its lift is
measurable against an unchanged default path.

It converges toward the Prime Directive by exercising the L0/L1 rungs of the escalation ladder
(prompt-shape and self-gated deliberation) as a cheap harness lever before heavier moves, and
by honoring the ladder's cost-order discipline. Crucially it protects Tenet 3: only the
visible docstring examples decide *when* to think — the hidden red→green oracle is never read
during the solve and scores only at the end — so no expected output ever leaks into the
generation loop.
