# Syndication kit — LinkedIn, X, profiles, micro-posts

Publish the long-form on your blog first. Then paste these the *same day*. Always link
back to `[BLOG_URL]`. Fill the brackets.

---

## PROFILES (set up Day 1)

### X / Twitter bio (paste into your profile)
> Building agentic engineering in the open. The bet: most AI coding is "jig work" that
> runs on a tiny local model — and a frontier model's real job is authoring the jigs,
> not running them. Honest numbers, including the failures.

### LinkedIn headline (replace your current one)
> Agentic engineering, in the open · Architecting AI coding systems that run on small
> local models · Writing about where the frontier actually stops

### LinkedIn "About" section (optional, paste if you want)
> I build and write about agentic software engineering — specifically, systems where a
> small, local model does the everyday majority of coding work inside a deterministic,
> test-gated harness, and an expensive frontier model is reserved for the genuinely
> novel 20%. I care about honest measurement: what these systems can really do, and
> exactly where they break. Much of my current system is built by an AI agent under my
> direction, which is its own data point about where this field is heading. Follow for
> the architecture, the wins, and the failures.

---

## WEEK 1 — POST 1 SYNDICATION ("The Genius and the Jig")

### LinkedIn version (paste as a LinkedIn post; ~Tue 8–10am your time)
> We're paying a genius to do our filing — and that bill is going to come due.
>
> When you ask a frontier model to "add a function with tests," it works out the same
> procedure from scratch every single time: stub, test, implement, run, fix. Across a
> thousand repos, it re-derives that same stable workflow a thousand times — at full
> price. It's the compute equivalent of recompiling your whole toolchain on every
> keystroke.
>
> There are really two jobs hiding in every coding task:
> • discovering the procedure (hard, novel — worth a frontier model)
> • executing a known procedure (most of the work — NOT where intelligence is the
>   bottleneck)
>
> Call them the genius and the jig. Today we pay genius rates for jig work, because we
> haven't separated them. The whole opportunity is in separating them: capture the jig
> once as deterministic, test-gated code, let a tiny local model fill the blanks, and
> reserve the frontier model for authoring *new* jigs.
>
> The economics compound. Project #1, the big model is cheaper. Project #N, your jig
> library is shared infrastructure at ~zero marginal cost while the all-frontier
> approach pays full freight every time.
>
> I wrote up the full argument — including the honest part about what a tiny model
> genuinely *can't* do:
> [BLOG_URL]
>
> Curious what others building agentic systems think: where's your genius/jig line?

### X thread (paste as a thread; ~Tue 9am–12pm ET). Each numbered block = one tweet.

**1/**
We're paying a genius to do our filing.

When you ask a frontier model to "add a function with tests," it re-derives the same
procedure from scratch — every call, every repo, at full price.

That procedure never changes. We're recompiling the toolchain on every keystroke. 🧵

**2/**
Two jobs hide in every coding task:

• discovering the procedure (hard, novel)
• executing a known one (most of the work)

The first is worth a frontier model. The second isn't. We pay the same rate for both
because we haven't separated them.

**3/**
Call them the genius and the jig.

A jig is the fixture a machinist clamps a part into so the same cut comes out right
every time — no re-thinking the cut.

The genius discovers the jig once. The jig runs forever.

**4/**
The architecture this implies:

1. deterministic harness holds the jigs (test-gated)
2. a tiny LOCAL model fills the bounded blanks
3. the frontier model retires from the hot loop → its job is *authoring new jigs*, not
   running old ones

Expensive reasoning becomes one-time capital, not per-task cost.

**5/**
Why now: today's AI-coding prices are a land grab — subsidized to win share. That phase
ends. When the bill comes due, "cheapest model that clears the bar" goes from hobbyist
hygiene to procurement requirement.

**6/**
And it compounds. Project #1 the big model is cheaper (no jigs yet). Project #N your jig
library is shared infra at ~zero marginal cost — while all-frontier pays full freight
every time.

The local path isn't cheaper per project. It's capital that compounds.

**7/**
Honest part: a harness is a multiplier, not magic. It only multiplies the *offloadable*
work. `little-coder` moved a ~10B model 19%→45% on Aider Polyglot just by changing the
scaffold. That's not a smarter model — it's the harness doing work the model did badly.

**8/**
So the real question isn't "can a tiny model be as smart as a frontier one?" (no.)

It's: how much of real engineering is so mechanizable that a tiny model + harness and a
frontier model produce *the same result*?

Nobody has an honest answer. I'm building to measure it.

**9/**
Full write-up — including where a tiny model genuinely hits a wall:
[BLOG_URL]

I'm building this in the open (a fair bit of it built by an AI agent under my
direction). Follow for the architecture, the wins, and the failures. The failures are
where the frontier is.

---

## WEEK 1 — FRIDAY MICRO-POST ("build in public" — seeds Post 2)

### X (and LinkedIn, lightly edited) — Fri Jun 26
> Most honest moment of my week building a small-local-model coding harness:
>
> The system built a `largest(xs)` function. The 2B wrote `def largest(*args): return
> max(args)`. Called as largest([1,5,2]) it returns the *list*, not 5. Test correctly
> failed it.
>
> I fixed the mechanizable part (parameter handling) in deterministic code. And the
> list-aggregation logic STILL defeated the 2B. The harness couldn't paper over it — and
> I'm not going to pretend it did.
>
> That line — what the harness can absorb vs the model's real ceiling — is the whole
> game. Writing it up next week.

---

## WEEK 2 — POST 2 SYNDICATION ("Why Small Models Fail at Agentic Coding")

### LinkedIn version (paste; ~Mon Jun 29 8–10am)
> A small model failing at agentic coding usually isn't a coding failure. It's a
> *sequencing* failure — and that distinction changes how you build the whole system.
>
> I watched a 2B model fail a multi-step task not because it couldn't write the fix — it
> could — but because its plan simply never INCLUDED the fix step. The capability was
> there. The judgment about what to do wasn't.
>
> For a small model, open-ended planning ("what should I do?") is one of the least
> reliable things you can ask. Filling a bounded blank ("implement this stub so this
> test passes") is one of the most.
>
> So the fix is: stop asking it to plan. Make the control flow a deterministic program;
> let the model only fill constrained blanks; gate every step on the test exit code.
>
> Early signal: same 2B, deterministic flow completed 3/3 vs 2/3 for free-form planning
> (it failed the one where it skipped the fix step). Small sample — I'm reporting it as a
> signal, not a trophy.
>
> Full post, including a failure I'm genuinely proud of and what it reveals about the
> real frontier:
> [BLOG_URL]

### X thread (paste; ~Mon Jun 29). Each block = one tweet.

**1/**
A small model failing at agentic coding usually isn't a coding failure.

It's a *sequencing* failure. And that one distinction changes how you build the whole
system. 🧵

**2/**
I watched a 2B model fail a multi-step task — not because it couldn't write the fix (it
could), but because its plan never *included* the fix step.

It planned around the actual work. Capability: there. Sequencing judgment: not there.

**3/**
For a small model:
• open-ended planning ("what steps?") → least reliable thing you can ask
• filling a bounded blank ("implement this stub so this test passes") → most reliable

So stop asking it to plan.

**4/**
The fix: make the control flow a DETERMINISTIC program. The model never chooses steps.

• flow decided by a fact (is there a failing test?) not a judgment
• model only fills constrained blanks
• every step gated on the test exit code — never the model's "looks good"

**5/**
Early signal (same 2B): deterministic flow 3/3 vs free-form planning 2/3 — it failed
the exact case where it skipped the fix step.

n=3, my own tasks. A signal pointing the right way, not a trophy. Harder external
numbers to come, flattering or not.

**6/**
The part I'm proudest of is a failure.

System built a list fn. 2B wrote `def largest(*args): return max(args)`. largest([1,5,2])
→ returns the list, not 5.

I fixed the mechanizable bit (params) in code. The aggregation logic STILL beat the 2B.
Harness couldn't paper over it.

**7/**
That's the thesis in one example:

harness ABSORBS the mechanizable grain (param routing) ✅
harness CAN'T manufacture the reasoning ❌ ← the model's real ceiling

Mapping the line between those two is the frontier I care about.

**8/**
The elegant bit: decompose the *workflow*, not just the task. The same move that lets a
small model write one correct function (spec → fill → verify), applied one level up to
the plan itself.

Full write-up: [BLOG_URL]
