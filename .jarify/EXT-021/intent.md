# Intent

EXT-021 builds the **multi-model harness** the Prime Directive now demands (PRIME-001, owner
directive 2026-06-28): the system stops treating one model as universal and instead **routes each
problem to the Jetson-fitting model best able to handle its class**, rewiring the harness — tools,
agents, configuration, prompts — to that model before it solves.

This exists because measurement forced it. On the hardest repo-level tasks, sampling at scale
(pass@k), explicit decomposition, and non-deterministic orchestration all failed to extract a
solution from Gemma 4 2B — an honestly-recorded generation-capability ceiling for *that model* on
*that class*. The directive's response is not to deny the ceiling but to route around it: keep
Gemma 4 2B for the classes it handles well, and send the classes it cannot to a stronger
Jetson-fitting model adapted for them.

EXT-021 provides four things, all on-device and zero-cost (Tenet 2), all two-plane and honest
(Tenets 1 & 3):

1. a **model registry** — for each Jetson-fitting model, a *profile*: the problem classes it is
   *measured* to handle, plus the tools/agents/config/prompts that adapt the harness to it;
2. a **model-router judge** — classifies a problem's class and selects the model whose profile
   covers it, emitting an inert `Decision` (deterministic default when unsure → a capable model,
   never a failure);
3. a **rewire mechanism** — deterministically ensures the chosen model is the one served on the
   Jetson (swapping the llama.cpp model when needed) and activates that model's adaptation;
4. a **profiling/exploration loop** — grows the roster best-first (strongest-that-fits first) and
   earns each model's class profile by held-out measurement, never by assumption.

A model is only as good as its adaptation: a naive swap with no per-model adaptation regressed
(0/16 vs the co-adapted 4/16), so the adaptation — not just the weights — is what performs.
EXT-021 serves PRIME-001 and never overrides it; the router and the rewire are inert-Decision +
deterministic-clerk respectively, hash-chain logged and replayable, and every profile claim is
held to held-out, honest measurement.
