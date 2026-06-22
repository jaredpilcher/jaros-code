# Jaros release kit — Week 2, Thu Jul 2

**Framing rule:** Jaros is the *substrate*, not the headline. Two-plane / plan-then-
execute architectures are not new — and you should SAY so, honestly. What you're
offering is a clean, reproducible implementation of it, plus the point of view it
enables (the jig/genius thesis) and the harness coming next (jaros-code). Don't oversell
the framework; let the ideas and the upcoming evidence carry the weight.

**Order of operations on release day (Thu Jul 2):**
1. ~8:45am ET — flip the repo public. Double-check the README renders and the LICENSE is
   present.
2. ~9:00am ET — post to `r/LocalLLaMA` (copy below). This is your best-fit audience.
3. ~9:15am ET — X announce thread (copy below).
4. ~9:30am ET — LinkedIn announce (copy below).
5. Optional, ~8–9am ET — Show HN (copy below). HN is high-variance and harsh on hype;
   the honest, technical framing below is built for it. If it doesn't take off, that's
   normal — it's a coin flip even for good projects.
6. All day — reply to every comment. This matters more than the posts.

---

## LICENSE
Use **Apache-2.0**. Money isn't your goal; reach is. Permissive licensing maximizes
adoption (and adoption is influence), and Apache-2.0 adds a patent grant that makes
companies comfortable using it. Add a `LICENSE` file with the standard Apache-2.0 text
(GitHub: "Add file" → it offers license templates → choose Apache License 2.0).

---

## REPO README — intro section (paste at the TOP of the Jaros README)

> # Jaros
>
> **A two-plane substrate for agentic systems: the model only ever emits inert decision
> data; a deterministic, test-gated execution plane performs every side effect.**
>
> The reasoning plane (a model — and Jaros is built to run on *small, local* ones)
> proposes actions as plain data. It never touches your files, your shell, or the
> network. A deterministic clerk validates each proposed action and a custom tool
> executes it. Every run is hash-chain logged and replayable to byte-identical state
> with zero model calls.
>
> This separation isn't a new idea — "plan-then-execute" and capability-safe agent
> architectures are well-explored. What Jaros gives you is a clean, reproducible
> implementation of it, designed from the ground up for the case everyone else treats as
> an afterthought: **a tiny local model doing real work, safely.**
>
> ## Why this exists
>
> I believe most agentic coding is "jig work" — running stable, reusable procedures that
> don't need a frontier-scale model — and that the future of the field is small local
> models filling the blanks inside deterministic harnesses, with expensive models
> reserved for authoring new procedures. Jaros is the substrate I'm building that bet on.
> The coding harness built on top (jaros-code) and the honest benchmarks come next.
>
> Full reasoning: [BLOG_URL]  ·  Series: [BLOG_HOME]
>
> ## Status & honesty
>
> This is an active research project, built largely by an AI agent under my direction —
> which is itself a small data point about where agentic engineering is going. I report
> results, including failures, honestly. Expect rough edges. Issues and pushback welcome.

*(Keep the rest of your existing README — install, quickstart, architecture — below
this intro.)*

---

## r/LocalLLaMA post (Thu Jul 2 ~9am ET)

**Title:**
> I built a two-plane harness for running real coding work on a tiny LOCAL model (2B-class, on a Jetson) — substrate is now open source

**Body:**
> I've been building toward a specific bet: that most everyday coding is "jig work" —
> stable, reusable procedures — and doesn't actually need a frontier-scale model. A tiny
> local model can fill the blanks inside a deterministic, test-gated harness, and you
> reserve the big expensive model for the genuinely novel stuff.
>
> Today I'm open-sourcing the substrate it's built on, **Jaros**: a two-plane
> architecture where the model only emits inert decision data, and a deterministic
> execution plane does everything that touches your files/shell (every effect is a
> test-gated tool). Every run is hash-chain logged and byte-identically replayable with
> zero model calls.
>
> To be upfront: two-plane / plan-then-execute isn't a new idea. What I'm trying to do
> well is the small-local-model case specifically — running this on ~2B-class models
> (Gemma-class) on a single Jetson, at zero marginal cost.
>
> One thing I've found that actually moves the needle for small models: **move the
> control flow off the model.** Don't ask a 2B "what steps should I take?" (it's
> unreliable at that and will skip steps it's perfectly capable of executing). Make the
> workflow a deterministic program and let the model only fill bounded blanks. Early,
> small-sample signal: same 2B, deterministic flow 3/3 vs free-form planning 2/3.
>
> I'm also honest about where it breaks — e.g. list-aggregation logic that the harness
> genuinely *can't* paper over, no matter how I route it. Mapping that line (mechanizable
> vs the model's real ceiling) is the actual point of the project.
>
> Repo: [REPO_URL]
> Write-up of the thinking: [BLOG_URL]
>
> Coding harness on top (jaros-code) and benchmarks on real repo histories are coming.
> Would genuinely love feedback from people who run local models daily — what's worked
> for you on the small end?

---

## X announce thread (Thu Jul 2 ~9:15am ET)

**1/**
Open-sourcing Jaros today.

It's the substrate behind a bet I've been writing about: most coding is "jig work" that
runs fine on a TINY local model — and the frontier model's real job is authoring the
jigs, not running them. 🧵

**2/**
Jaros is a two-plane harness:
• the model emits only inert decision data (never touches your files)
• a deterministic, test-gated execution plane does every side effect
• every run is hash-chain logged + byte-identically replayable, zero model calls

**3/**
Honest framing: two-plane / plan-then-execute isn't new. What I'm doing is the part
everyone treats as an afterthought — making it work for a ~2B local model on a single
Jetson, at zero marginal cost.

**4/**
The thing that actually helps small models: move the control flow OFF the model.

Don't ask a 2B "what steps?" — it'll skip steps it can perfectly well execute. Make the
flow deterministic; let the model fill bounded blanks.

Early signal: 3/3 vs 2/3, same model.

**5/**
And I report where it breaks. A 2B will write `def largest(*args): return max(args)` and
hand you the list instead of the max. The harness can fix the routing; it can't
manufacture the reasoning. That line is the whole project.

**6/**
Repo: [REPO_URL]
The thinking: [BLOG_URL]

Built largely by an AI agent under my direction. Coding harness + real-repo benchmarks
next. Feedback very welcome — especially the critical kind.

---

## LinkedIn announce (Thu Jul 2 ~9:30am)

> Today I'm open-sourcing Jaros.
>
> It's the substrate behind something I've been writing about: the bet that most everyday
> coding is "jig work" — stable, reusable procedures that don't need a frontier-scale
> model — and that the future is small local models filling the blanks inside
> deterministic harnesses, with expensive models reserved for the genuinely novel.
>
> Jaros is a two-plane architecture: the model only ever emits inert decision data, and a
> deterministic, test-gated execution plane performs every side effect. Every run is
> hash-chain logged and byte-identically replayable with zero model calls. I'm honest
> that two-plane design isn't new — what I'm focused on is making it work for a tiny local
> model (2B-class, on a single Jetson) at zero marginal cost.
>
> It's an active research project, built largely by an AI agent under my direction — which
> is its own small signal about where this field is going. I'll keep sharing the wins and
> the failures; the failures are where the real frontier is.
>
> Repo: [REPO_URL]
> Why I'm building it: [BLOG_URL]
>
> The coding harness on top, and honest benchmarks on real repo histories, come next.

---

## Show HN (optional, Thu Jul 2 ~8–9am ET)

**Title:**
> Show HN: Jaros – a two-plane harness for running coding work on a tiny local model

**Text (the first comment you post on your own submission):**
> Author here. Jaros is a substrate for agentic systems where the model emits only inert
> decision data and a deterministic, test-gated execution plane performs every side
> effect. Runs are hash-chain logged and byte-identically replayable with zero model
> calls.
>
> I'll be direct that the two-plane / plan-then-execute pattern isn't novel. My interest
> is a specific, under-served case: running real coding work on a ~2B-class local model
> (Gemma-class, on a single Jetson) at zero marginal cost, by moving as much of the work
> as possible onto deterministic, test-gated tools and leaving the model only the narrow
> judgments it can actually make reliably.
>
> One finding that's held up so far: small models fail agentic tasks mostly at
> *sequencing*, not at the individual steps. Making the control flow deterministic
> (rather than letting the model plan) turned a 2/3 into 3/3 on a small multi-step eval
> with the same model. Small sample — I'm treating it as a signal, not proof, and I'm
> equally interested in where it breaks (e.g. list-aggregation logic the harness can't
> compensate for).
>
> Repo: [REPO_URL]. Write-up: [BLOG_URL]. A coding harness on top and benchmarks on real
> repo commit histories are next. Happy to answer anything, and I'd genuinely value
> hard critique.
