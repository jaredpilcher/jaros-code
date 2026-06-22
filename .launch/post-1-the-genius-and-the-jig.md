# The Genius and the Jig: Why Most AI Coding Will Soon Run on Tiny Local Models

*Post 1 of an ongoing series on the economics of agentic engineering.*
*Publish on your blog first. Title above is the headline. The first line below is your subtitle/hook.*

---

**We are paying a genius to do our filing. That bill is going to come due, and when it
does, the architecture of AI software engineering is going to change.**

Here is something that sounds obvious once you say it out loud, and yet almost nobody
is building around it.

When you ask a frontier model to "add a function with tests," it works out the whole
procedure from scratch: stub the function, write a test, implement, run it, read the
failure, fix it. Ask it the same shape of task a thousand times across a thousand
repos and it re-derives that same procedure a thousand times — at full price, with
full nondeterminism, every single time.

But that procedure doesn't change. It's *stable*. It does not need to be rediscovered
on every call. Burning a 200-billion-parameter model to re-invent a workflow you
already know is the compute equivalent of recompiling your entire toolchain on every
keystroke. It works. It's also enormously wasteful — and right now we mostly don't
notice, because someone else is paying for the waste.

## Two jobs, not one

The mistake is treating "intelligence" as one indivisible thing you rent by the token.
In real engineering there are two very different jobs hiding inside every task:

- **Discovering the procedure.** Facing something genuinely new and figuring out *how*
  to approach it. This is hard, general, and irreducible. This is where a frontier
  model earns its cost.
- **Executing a known procedure.** Running a workflow you've already worked out, with
  the specifics filled in. This is most of the actual work, and it is *not* where
  raw intelligence is the bottleneck.

Call the first one the **genius** and the second one the **jig** — the fixed fixture a
machinist clamps a part into so the same cut comes out right every time, without
re-thinking the cut. The genius discovers the jig once. The jig runs forever.

Today we pay genius prices to do jig work, because we haven't separated the two. The
entire opportunity is in separating them.

## The architecture this implies

Once you see the split, a different system design falls out:

1. A **deterministic harness** holds the reusable jigs — the stable workflows, captured
   once as code, each gated by tests so it can't silently produce garbage.
2. A **small, local model** fills the bounded blanks inside those jigs: write *this*
   test, implement *this* function against it, classify *this* result. Narrow
   judgments a tiny model can actually make.
3. The **frontier model retires from the hot loop** and moves to the workbench. Its
   highest-value job isn't *doing* the tasks — it's *authoring new jigs* when a genuinely
   new class of problem shows up, then handing them to the cheap local model to run a
   million times.

The expensive reasoning becomes a *one-time capital cost per class of problem*, not a
recurring per-task cost. That is the whole game.

## Why this matters now: the bill is coming due

A lot of today's AI-coding spend is happening inside a land grab. Pricing is
aggressive, tiers are generous, and usage is being underwritten to win market share.
Per-token prices right now do not necessarily reflect what inference costs to serve at
scale, with margin, forever.

That phase ends. It always does. And when it does — or simply when a team's usage
10x's and the bill stops being a rounding error — someone in finance asks why the
coding workflow has a five-figure monthly inference line. At that moment, "use the
cheapest model that clears the bar" stops being a hobbyist's hygiene and becomes a
procurement requirement.

Notice the asymmetry that makes the jig approach compound. On project #1, the frontier
model is cheaper — you have no jigs yet, so you're paying to build them. By project #N,
your jig library is shared infrastructure and the local marginal cost is approximately
zero, while the all-frontier approach pays full freight *every time*. The local path
isn't "cheaper per project." It's **capital that compounds.** The break-even moves in
its favor with every project you run — which is exactly the regime real engineering
lives in.

## Is it actually possible? Honestly: partly, and the frontier is the interesting part

Let me be careful here, because this is where people oversell and lose me.

The harness is a *multiplier*, but it only multiplies the part of the work that's
offloadable — sequencing, counting, search, verification, structure. It cannot
manufacture reasoning the model doesn't have. So a small-model-plus-harness setup gets
huge gains on tasks that are mostly scaffolding around a small judgment, and roughly
nothing on tasks that are one big irreducible leap.

The multiplier is real, and it's been measured by others. The open-source `little-coder`
project moved a ~10B model from **19% to 45%** on the Aider Polyglot benchmark purely by
changing the *scaffold* around the model — same model, more than double the score.
Reports of "up to ~6x from better tooling" float around the local-LLM community. None
of that is the model getting smarter. It's the harness doing work the model used to be
asked to do badly.

So the honest question isn't "can a tiny model be as smart as a frontier model?" It
can't, and that's fine. The question is:

> **What fraction of real software engineering is so thoroughly mechanizable that the
> residual model task is small enough that a tiny local model and a frontier model
> produce indistinguishable results?**

For that fraction, you reach parity — not because your model is as smart, but because
the harness made the smartness nearly irrelevant. And that fraction *grows* every time
you capture a new jig.

Nobody has a confident, honest answer to how big that fraction is. I think measuring it
is one of the more important open questions in agentic engineering right now, and it's
the thing I'm building toward. I'll report what I find — including, especially, where
it stops. (I have an opinion on what it'll take to measure this honestly: replay real
repo commit histories, gate on tests, and never grade yourself on problems you tuned
to. More on that soon, with results.)

## What this means if you build software for a living

The scarce skill is shifting. It stops being *prompting the biggest model* and becomes
*knowing which 20% of the work actually needs it.* Routing by marginal value:
cheap-and-local for the mechanizable bulk, expensive-and-frontier only where it changes
the outcome or authors a new jig.

The engineer who can draw that line precisely is the one who looks brilliant when the
budget conversation arrives. And it will arrive.

## What I'm doing about it

I'm building this in the open: a deterministic, two-plane harness (a small model
proposes; deterministic, test-gated tools do everything that touches your files), aimed
at running the everyday majority of coding work on a tiny local model — small enough to
run on a single Jetson, at zero marginal cost, forever. A fair amount of the system
itself is being built by an AI agent under my direction, which is its own data point
about where this is all going.

I'll be sharing the architecture, the wins, and — just as much — the honest failures,
because the failures are where the real frontier is. If "how much of engineering
collapses into reusable jigs a tiny model can run for free" is a question you also find
interesting, follow along.

The genius is expensive and you'll always want one on call. But you shouldn't be paying
genius rates to do the filing. Soon, you won't have to.

---

*If this resonated, I'm writing a series on it — [subscribe / follow]. Next: the single
architectural change that lets a tiny model handle multi-step coding at all.*
