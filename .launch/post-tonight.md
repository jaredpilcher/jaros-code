# POST THIS TONIGHT — canonical post (dev.to)

Title (use this one):
> Can a 2B model on a $250 Jetson replace Claude Code? Ten days of honest numbers

Alt title if you like it better:
> I spent ten days forcing tiny local models to write real code. Here's what actually breaks.

---

I had a thought a few weeks ago that wouldn't leave me alone: I depend on Claude Code
every day. If it disappeared tomorrow — priced out, rate limited, whatever — I'd want a
fallback I actually own. Not a cheaper subscription. Something that runs on my own
hardware, forever, at zero marginal cost.

So I started an experiment. A coding harness where every reasoning call goes to a tiny
local model (Gemma's 2B, served by llama.cpp on a Jetson Orin Nano), and the harness does
everything it can to make up the difference. One hard rule: no cloud fallback, ever. If
the small model can't do something, decompose the work or move it into deterministic
code. Never escalate to a bigger model.

The bet isn't mine alone. Projects like little-coder and NVIDIA's small-model research
make the same wager: small models underperform agentic work because their harnesses are
thin, not because the models are incapable. I wanted to find out exactly how true that
is, with numbers I could trust. Ten days in, here's what I've learned.

## The harness was throwing away right answers

My biggest early win wasn't making the model smarter. It was noticing that about 60% of
my failures were the model producing correct logic with broken indentation. The module
wouldn't even import, so it scored as a fail. The right answer was sitting there and my
harness was discarding it over whitespace.

The fix: only when the output fails to parse, ask the model to re-indent its own code,
logic untouched. That one change took my bar from 64 to 76 out of 100 — and the gain
held on the 50 problems I'd never tuned against (31 to 38), which is the half I trust.

If you take one thing from this post: before you conclude a small model can't do
something, check whether your harness is throwing away the times it did.

## Never let a small model decide what to do. Only what to write.

I watched the 2B fail a multi-step task in a way that changed how I build. It wasn't
that it couldn't write the fix — it could. Its plan just never *included* the fix step.
It planned around the actual work.

For a small model, open-ended planning ("what steps should I take?") is close to the
least reliable thing you can ask. Filling a bounded blank ("make this stubbed function
pass this test") is close to the most reliable. So I stopped asking it to plan. The
control flow is now a deterministic program and the model only fills slots. On my
multi-step scenarios that took it from 2/3 to 3/3. Three scenarios, so I'm not calling
that statistics — but the failure mode was clear and reproducible.

Related rule that's now non-negotiable: the test exit code is the only judge. The model
saying "looks good" counts for nothing.

## Small models are decent writers and terrible judges

I tried adding a review step: the model checks its own passing solution against the
spec and revises if it finds a gap. Standard self-reflection stuff, everyone does it.

It made things worse. The 2B took a solution that passed its tests, declared there was
a gap, and rewrote it into one that failed. The same review-then-commit pattern works
fine when I run it with a large model. So "model as judge" isn't a pattern that's good
or bad — it has a capability threshold, and a 2B is below it. I haven't seen that
stated plainly anywhere, probably because almost nobody runs the review pattern on
models this small and measures what happens.

## Most of my good ideas were wrong

Things that did nothing or made it worse, on held-out problems: more context (flat),
few-shot examples (zero-shot beat it), retrieval-augmented examples (flat), best-of-N
sampling (pure noise). At one point run-to-run noise made a genuinely net-negative
prompt change look like a +6% win. That scared me into building a deterministic,
temp-0, held-out eval before touching anything else. Cheap insurance. Every claim in
this post survived it; most of my ideas didn't.

## Then I hit the real wall

HumanEval-style single functions are the easy tier — my harness now does well there
(and honestly, those benchmarks are probably in every model's training data anyway, so
I only trust the paired deltas, not the absolute scores).

Real repositories are a different sport. I built a commit-replay eval: take a real
project's git history, keep only commits where the repo's own tests go red-to-green,
and ask the harness to reproduce the change from the commit message alone. Test hidden,
no leakage, scored in Docker.

Mining one library's last 400 commits left 37 that were cleanly checkable this way
(most commits don't come with a test that pins the change — that filter ratio was a
finding in itself). One-shot result: 1 of 37, call it 3%. A second repo came in at 0
for 11, so it's not a quirk of one codebase. After a structural fix (apply every
function the commit changed, not just the first): 4 of 37, about 11%. Then a
structured spec-first flow — the model writes a behavior spec from the intent, then
its own tests from the spec, then code against those tests, with the real oracle
still hidden — took it to 6 of 37, about 16%. On seven of the hard cases I ran a
sampling probe — twenty samples each at fair temperature, zero correct. The right
answer isn't in the model's distribution at all. That's not a selection problem or a
prompting problem. It's a genuine generation wall.

That gap — 80%+ on single functions, ~10% on real commits — is the actual frontier for
small models, and I don't see anyone publishing it honestly. (If anything, benchmark
contamination inflates the first number, which makes the real gap wider.)

## So now it's a multi-model system

If one 2B has a wall, maybe several small models with different walls can cover for
each other. I added Qwen's 3B coder and profiled both per problem class. On standalone
function generation it genuinely beats Gemma — 65% vs 48% on MBPP (48% is Gemma's best
mode; 25% without its reasoning gate). I used MBPP for this specifically after checking
that the edge wasn't just HumanEval contamination. Routing that class to Qwen is the
first clean multi-model win.

But here's the finding that matters more: on the hard repo class, Qwen fails the exact
same problems Gemma does. Two similar models have correlated failures. Adding a second
similar model buys you nothing on the wall — you need models that are actually
*different*, not just more of them. I'm auditioning Phi-4 next for exactly that reason.

And selection is deterministic: the test gate picks the winner. Never a model judging
another model — see above.

## Why I'm doing this

Partly because budgets come due. We're all building on subsidized inference, and when
that ends, "cheapest model that clears the bar" becomes a real engineering discipline.
Partly sovereignty: a future where every small team rents cognition from three
companies isn't the future I want. Hardware you can buy for a few hundred dollars,
running models you own, is the alternative — if we can prove it's good enough.

But mostly because mapping the limit is the interesting part. Not "can a tiny model
match a frontier model" (it can't, in general) but: which parts of real development
collapse into work a tiny model can do inside the right harness, and which parts are
genuinely out of reach? I'm building that map, model by model, and I'll keep publishing
what I find — including the failures, which so far have taught me more than the wins.

The code isn't public yet — I want the first version of the model map done before I
open it up. If this is your kind of problem, follow along, or tell me what I'm getting
wrong. I'd genuinely like to know.
