# Intent

**jaros-code** is a software-development harness built on Jaros whose purpose is to
match or exceed Claude Code at real coding work **while every reasoning call is
served by a single small local model — Ollama `gemma2:2b` — at zero inference cost.**

**The bar is explicit and high: the system must become so good that it overcomes
the model limitations of `gemma2:2b` and reaches the quality of Claude Code running
on Claude Opus 4.8.** The harness — not the model — closes that gap. We do not get
to claim we are near the bar; we have to *prove* it. So this system is built
together with a growing suite of **tests and evaluations** that measure, run over
run, whether we are getting closer to Claude-Code-on-Opus-4.8 parity on real coding
tasks. We both author our own task evals *and* run existing public coding
benchmarks where they exist (e.g. SWE-bench / SWE-bench-Verified, HumanEval/MBPP,
Aider's edit benchmark) so the bar is an external, recognized one — not a yardstick
we drew ourselves. Progress is the benchmark trend, not a feeling.

The wager behind this system: *small models have not been useful for development
because their harnesses are thin, not because the models are incapable.* A
deterministic, reproducible, capability-safe harness that decomposes development
into many small, single-purpose, well-scoped agent decisions — each backed by a
deterministic tool — can close the gap that a single large prompt to a single
large model cannot.

These commitments are ordered. A lower-numbered commitment is never weakened to
satisfy a higher-numbered one. When any specification, agent, tool, or change
would violate one, **STOP and flag the conflict** rather than silently resolving it.

1. **Two-plane discipline (inherited from the Jaros prime directive).**
   The model only ever writes recommendations on slips of paper: inert,
   JSON-serializable `Decision` data. A deterministic execution plane (the
   "clerk") decides whether and how each decision actually runs. The reasoning
   plane never performs a side effect directly — no file write, no shell command,
   no network call originates from a model output. Everything the harness *does*
   is a deterministic tool the clerk runs.

2. **Small-model-only, zero paid inference.**
   Every reasoning call goes to local `gemma2:2b` via Ollama. No cloud model, no
   paid API, ever — not as a fallback, not "just for the hard parts." If a
   capability appears to require a larger model, that is a signal to **decompose
   the work into smaller agent steps and stronger deterministic tools**, never to
   escalate the model.

3. **Reproducible & honest.**
   Every run is hash-chain logged and replayable to byte-identical state with zero
   model calls. The harness never hides, rounds away, or fabricates a result. A
   failing test is reported as failing; a skipped step is reported as skipped. The
   decision log is the auditable truth of what the system did and why.

4. **Spec-first, the jarify way — all the way down.**
   Behavior is governed by `.jarify` specifications. Code traces back to
   requirements through `index.json`. When specified behavior changes, the spec
   and the code change in the same commit. Stale specs are defects. This Prime
   Directive is the north star every other spec must serve and must never contradict.

   This is reflexive, and it is the product itself: **`jaros-code` is a code-building
   tool, and the way it builds a user's system IS the way jarify is used.** When it
   takes on a user's project it first captures *the user's* intent as a prime
   directive for that project, decomposes that intent into requirements / design /
   tasks, implements one scoped task at a time with single-purpose agents, validates
   each task against its requirement, and traces the resulting code back to the spec —
   the identical loop that produced `jaros-code` itself.

   **Jarify is the mechanism of convergence on the user's intent.** Because a 2B
   model left to free-form prompting drifts, jarify pins every actor — the operator,
   each single-purpose agent, every deterministic tool — to one explicit, written
   statement of what the *user* asked for. The spec is the shared north star that
   keeps the whole fleet pulling toward the user's actual goal instead of wandering.
   We build the harness the way we want the harness to build; the harness builds the
   user's software the jarify way so the result converges on what the user meant.

5. **Claude-Code-like experience.**
   The operator-facing experience should feel familiar and transparent: a terminal
   harness that shows what it is doing, what each agent decided, and what each tool
   ran — with the same kind of look and feel as Claude Code. But UX is the last
   tier: it never overrides correctness, reproducibility, or the model-only
   constraint above it.

**The method, stated once:** capability comes from *composition* — many small,
single-purpose agents each making one narrow judgement, wired together by
deterministic tools and a durable state machine — not from one big agent, one big
prompt, or a bigger model. Build the fleet wide and the tools sharp.

**The scale is the strategy.** We are explicitly aiming for a *swarm* — hundreds,
then thousands, then tens of thousands of agents — to reach Claude-Code-on-Opus-4.8
quality. Every agent is expected to be **single-purpose and tiny**: one narrow
judgement, a minimal prompt, a minimal output contract — never a generalist. The
intelligence is in the multitude and the wiring, not in any one agent. This swarm is
matched by an equally **extensive library of deterministic tools** (the verbs the
agents compose) and an **extensive suite of evaluations** (the proof we are
converging on the bar). More capability is always answered by *more, smaller* agents,
*sharper* tools, and *more* evals — never by a bigger model.
