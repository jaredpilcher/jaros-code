# IDEA PLAYBOOK — how to generate novel levers yourself (for the supervisor agent)

The IDEA-BANK will run dry. This playbook is the machine that refills it. It is
written for YOU, the supervising agent: idea generation is not inspiration, it is a
set of MECHANICAL OPERATORS applied to artifacts you already maintain. Every entry in
the current bank was produced by one of these operators — the derivations are shown so
you can reproduce the moves, not just admire the outputs.

## When to run a generation session

- The bank has <5 live (unprobed, unkilled) ideas, or
- A Gap-Map row has exhausted its named levers, or
- Two consecutive experiments on an axis failed held-out (the ADAPT rule fired), or
- A scheduled monthly session regardless (staleness insurance).

A session = pick 2-3 operators, run them mechanically over the inputs, emit idea
cards, file them into the bank ranked by (impact × tractability). One session should
produce 3-8 cards. Do not run all operators at once — depth beats coverage.

## The inputs (you already maintain all of these)

I1. The Gap Map (current states, especially `wall(dated)` and `lever-named` rows)
I2. The failure taxonomy (top failure classes with counts, per model)
I3. Telemetry (fire rates, latencies, swap counts, token spend per class)
I4. The asymmetry table (§O1 below — maintain it as a living list)
I5. The verified-solution store and eval logs (the data exhaust)
I6. The current arsenal list (PURSUIT §5) and the reduction library
I7. External notes from research raids (papers, competitor harnesses, new models)

## The operators

### O1. Asymmetry mining ("what can WE do that THEY can't?")
Maintain a two-column table: properties WE have that the incumbent (cloud CC) does
not — always-on, zero marginal inference cost, full privacy, persistent state across
sessions, owner's real workload visible, trainable weights, hardware control — and
properties THEY have that we don't (frontier reasoning, huge context, speed).
PROCEDURE: for each OUR-side property, ask "what becomes possible if we exploit this
to the maximum?" For each THEIR-side property, ask "what makes this matter less?"
DERIVATIONS: always-on + free inference → N1 overnight brain, N2 speculative drawer.
Owner's workload visible → N3 shadow logging. Trainable weights + privacy → N4
per-repo adapters. Huge-context asymmetry neutralized → N9 zoom protocol.
BEST WHEN: you feel outclassed; the answer is never to imitate the incumbent.

### O2. Failure-class inversion ("make it impossible, not less likely")
Take the top failure class from I2. Do not ask "how do we fix these failures?" — ask
**"what STRUCTURE would make this failure class IMPOSSIBLE to express?"** Repair is a
patch; prevention is a lever.
DERIVATIONS: broken-indentation failures → N5 grammar-constrained decoding (unparseable
output becomes unemittable). Spec-misreading failures → N7 execution-grounded examples
(there is no spec to misread, only concrete I/O).
BEST WHEN: a failure class survives repeated repair-side jigs.

### O3. Boundary shifting (the when × where matrix)
Every piece of work in the pipeline happens at some WHERE (model weights / decode
constraints / deterministic tools / offline precompute) and some WHEN (train time /
setup time / idle time / decode time / solve time / verify time). PROCEDURE: pick a
pipeline stage that costs solve-time inference; walk it through every other cell of
the matrix and ask "could it live here instead?" Work moved earlier or out of the
model is almost always cheaper and more reliable.
DERIVATIONS: API knowledge at solve time → setup time (N8 knowledge compiler).
Candidate rejection at verify time → static pre-gates before execution (N13).
Harness scaffolding at solve time → into the weights at train time (self-distillation,
PURSUIT §7). Indexing at solve time → idle time (N1).
BEST WHEN: latency or token budgets dominate a class's cost.

### O4. Exhaust mining ("what do we throw away?")
List every byproduct the system produces and discards: logprobs, failed candidates,
eval outcome tuples, latency traces, think-traces, diffs between attempts, router
decisions. For each: "who could LEARN from this? what tiny model or metric could this
train?" Data you already paid for is the cheapest possible fuel.
DERIVATIONS: eval outcomes → N14 calibration micro-model + router training. Failed
candidates per (class, model) → N10 failure museum. Verified think-traces → N16
process distillation. Serve-path telemetry → N17 amortization ratio.
BEST WHEN: you want new capability without new inference cost.

### O5. Analogy transplant (raid other fields, mechanically)
Pick ONE field per session from: compilers, databases, operating systems, distributed
systems, manufacturing, biology/evolution, HCI, finance. List that field's 5 most
famous tricks. For each trick, force the mapping: "what is the analogue in a
two-plane, test-gated, small-model coding harness?" Most mappings are duds; one in
ten is a lever. The forcing is the method — do not skip mappings that feel silly.
DERIVATIONS: CPU speculative execution → N2 speculative solving. JIT compilation →
N4 per-repo adapters (specialize hot paths). Mutation testing (SE) → N12 task factory.
Cache hierarchies → memory tiers (exact → semantic → distilled). Assembly lines →
the reduction pipeline itself.
BEST WHEN: a plateau; internal iteration is circling.

### O6. Recombination (pairwise-collide proven levers)
Take the arsenal list (I6). Form pairs. For each pair ask "what does A × B enable
that neither does alone?" Most pairs are nothing; some are new levers.
DERIVATIONS: reductions × grammar constraints → N6 skeleton-constrained fills.
Embeddings × solution store → semantic recall. Mutation factory × auditions → instant
per-model curricula for any new roster candidate.
BEST WHEN: after adopting any new lever — immediately collide it with every old one.

### O7. Extremization ("what does 100× of this look like?")
Take a lever that produced a small measured win. Ask what its 100× version is — not
10% better, but categorically scaled. Then ask what breaks at 100× (that breakage is
usually the real engineering problem, and solving it is the idea).
DERIVATIONS: one repo map → compile ALL dependency knowledge (N8). One solved-task
memo → "second time is always free" as a system invariant (N17). A few authored evals
→ infinite generated curriculum (N12).
BEST WHEN: a lever works but its impact ceiling looks low.

### O8. Constraint tightening (invent by subtraction)
Deliberately imagine a HARSHER constraint than reality: "what if context were 512
tokens? what if we had 10 minutes of GPU per day? what if the model were 100M
params?" Design for the harsher world; port the design back. Scarcity forces
structural inventions that abundance never finds — this whole project is proof.
DERIVATIONS: the two-plane architecture itself (assume the model can do almost
nothing → everything important becomes deterministic). N9 zoom protocol (assume the
window is tiny forever).
BEST WHEN: you catch yourself waiting for a better model to solve a gap.

### O9. Research raid (standing, now with a filter)
Read papers/harnesses/releases (existing mandate). For each candidate idea, apply the
CONSTRAINT TRANSLATION test before import: does it survive (a) small-model-only, (b)
two-plane, (c) test-gated, (d) Jetson-tier? An idea that needs a frontier model is
not rejected — it is TRANSFORMED: "what is the small-model, deterministic, verified
version of this?" (Aider's repo map survived translation; MoA's LLM-aggregator did
not — its translated form is the test-gate picking winners.)
BEST WHEN: always; schedule it, don't wait for despair.

## The filter (every card passes ALL of these before entering the bank)

1. **Jaros-native placement** (PURSUIT §5H): which agents (inert judgments) and which
   deterministic tools implement it? If it can't be placed, extend Jaros, don't bypass.
2. **Sovereignty check** (PURSUIT §4): Jetson-tier inference, owned-hardware training,
   no data egress.
3. **Cheapest probe named**: the ≤1-day experiment that would falsify it.
4. **Kill criterion pre-registered**: the number that means "dead," written before
   the probe runs.
5. **Honesty check**: could this lever inflate a number without real capability?
   (e.g. anything touching eval selection, oracles, or memorization). If yes, name
   the safeguard in the card.

## The card format (uniform, so the bank stays rankable)

```
N<id>. <name> — <one-line concept>
WHY-HERE: <which measured finding / asymmetry / gap it exploits>
OPERATOR: <O1-O9 that produced it>   PLACEMENT: <agents/tools it lands as>
PROBE: <cheapest falsifier, ≤1 day>  KILL: <pre-registered threshold>
```

## Session hygiene

- Log every session's operator choices and yield in the bank's changelog — the
  playbook itself is measured (ideas generated → probed → adopted rate per operator).
  If an operator's adoption rate is persistently zero after ~10 uses, demote it and
  say so; if a new operator emerges from practice, ADD IT HERE with its derivation.
  This document is self-improving under the same rules as everything else.
- Never let generation replace building. One session, then back to the highest-ranked
  probe. An overfull bank of unprobed ideas is inventory waste, not progress.
