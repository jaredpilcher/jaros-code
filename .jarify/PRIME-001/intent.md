# Intent

**jaros-code** is a software-development harness built on Jaros whose purpose is to
match or exceed Claude Code at real coding work **while every reasoning call is
served by a single small local model — Ollama `gemma2:2b` — at zero inference cost.**

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

4. **Spec-first, the jarify way.**
   Behavior is governed by `.jarify` specifications. Code traces back to
   requirements through `index.json`. When specified behavior changes, the spec
   and the code change in the same commit. Stale specs are defects. This Prime
   Directive is the north star every other spec must serve and must never contradict.

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
