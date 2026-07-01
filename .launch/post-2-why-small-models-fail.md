# Why Small Models Fail at Agentic Coding — and the One Change That Fixes It

*Post 2 of an ongoing series on the economics of agentic engineering.*
*Publish on your blog first, then syndicate. Assumes readers may not have read Post 1.*

---

**A small model failing at an agentic coding task usually isn't a coding failure. It's
a *sequencing* failure — and that distinction changes how you build the whole system.**

In my last post I argued that most AI coding is "jig work": running stable, reusable
procedures, not re-discovering them every time — and that this work doesn't need a
frontier-scale model. This post is the concrete mechanism. It's the change that, in my
own experiments, is the difference between a tiny local model that flails on multi-step
work and one that completes it reliably.

## The standard agent loop, and how it breaks on a small model

The conventional agentic loop looks like this: the model is handed a task, it plans a
list of steps ("a TODO"), it executes each step with tools, observes the result, and
re-plans when something fails. Plan → act → observe → re-plan. Every serious harness
uses some version of this.

It works beautifully with a frontier model. With a small local model, it has a quiet,
maddening failure mode: **the model is perfectly capable of doing each individual step,
but unreliable at deciding which steps to take.**

I watched a ~2B model, running locally, fail a multi-step task not because it couldn't
write the fix — it could — but because, in its plan, it simply *never included the fix
step*. It planned around the actual work. The capability was there. The sequencing
judgment wasn't.

That's the key insight: for a small model, open-ended planning ("what should I do?") is
one of the *least* reliable things you can ask of it, while filling a bounded,
well-specified blank ("write the implementation for this stubbed function so this test
passes") is one of the *most* reliable.

So stop asking it to plan.

## The fix: move the control flow off the model

Instead of asking the model "what steps?", make the control flow a **deterministic
program** and let the model only fill the constrained blanks inside it.

Concretely, the loop becomes a fixed pipeline the model never chooses:

1. **Decide the flow from a fact, not a judgment.** Is there already a failing test? Then
   the requirement is "make it pass" — run the structured repair pipeline. No test yet?
   Then the requirement is the intent — turn it into checkable tests first. The model
   doesn't decide which branch; the *presence of a test* does.
2. **The model only fills bounded sub-tasks.** Write a test for this one behavior.
   Implement this one stubbed function. List the functions this request needs. Each is a
   narrow judgment a small model can actually make.
3. **Deterministic tools do everything that touches the filesystem,** and every step is
   gated by running the tests. Ground truth is the test exit code, never the model's
   say-so. A hallucinated "looks good to me" can't count.

The "what to do next" — the part the small model is worst at — is removed entirely. The
reliability of the *workflow* no longer depends on the model. Only the *content* does.

## Does it actually help? An honest, small signal

Here's where I have to be careful, because the honest answer is "early evidence, small
sample, promising."

On a head-to-head over the same multi-step coding scenarios, with the *same* 2B model:
the deterministic-flow version completed **3 of 3**; the free-form plan-it-yourself
version completed **2 of 3** — it failed the one where it skipped the fix step, exactly
the failure mode above. That's a clean, directionally clear result. It is also n=3, on
tasks I wrote, so I'm not going to wave it around as proof of anything cosmic. It's a
signal pointing the right way, and it matches the mechanism. I'll report bigger,
harder, external numbers as I get them — and I'll report them whether they're flattering
or not.

## The part I'm proudest of is a failure

The credibility of any benchmark claim lives or dies on what you do with the cases that
*don't* work. So here's one in full.

I had the system build a small module of list functions. One requirement was a
`largest(xs)`-style function. The harness decomposed the build, wrote a test, and the
2B implemented it — and it failed. When I dug in: an earlier step had thrown away the
function's parameters, so the stub took `*args`, and the model wrote something like
`def largest(*args): return max(args)`. Called as `largest([1, 5, 2])`, that returns
the *list* `[1, 5, 2]`, not `5`. The oracle correctly failed it.

I fixed the parameter-handling deterministically — and that fix *caused a regression*
elsewhere, because the change broke how the repair step routed its work. I caught it,
recovered, and landed in a better place than before. But here's the honest punchline:
even after the harness correctly handled the mechanizable part (the parameters), the
list-aggregation logic *remained a genuine limit of the 2B*. The harness could not
paper over it, and I'm not going to pretend it did.

That's the whole thesis playing out in one example. The harness **absorbed** the
mechanizable grain (parameter routing — fixed in deterministic code). And then it hit
the part it *can't* manufacture (the actual reasoning), which is the model's real
ceiling. The line between those two — what's mechanizable and what isn't — is the
frontier I actually care about mapping. A passing test tells you the system works. A
failure like this tells you *where the frontier is*, which is more valuable.

## The deeper pattern: decompose the workflow, not just the task

There's a recursion here that I find genuinely elegant. The reason a small model can
write a single correct function at all is decomposition: break the problem into a
checkable spec, fill it, verify it. What this change does is apply *that same move one
level up* — to the workflow itself. The plan stops being something the model improvises
and becomes a deterministic decomposition: verify the requirement, implement it, verify
again, with the model only filling slots.

Same principle that makes one function tractable, applied to make a multi-step,
multi-file build tractable. That's why it unlocks work a small model otherwise can't
touch — not because the model got better, but because we stopped asking it to be the
thing it's worst at.

## Where this is going

This is one jig. The bet from Post 1 is that a large and growing share of real
engineering collapses into a finite library of jigs like this one — deterministic,
test-gated, with a tiny local model filling the blanks — and that a frontier model's
best use is *authoring* new jigs, not executing old ones.

How big is that share? That's the number I'm working to measure honestly, on real repo
histories rather than tasks I wrote myself. When I have it, you'll get it — including
where it stops.

---

*This is part of an open, build-in-public project. Next up: the substrate it's built on
goes public, and then the experiment that actually measures the frontier. Follow along.*
