# Syndication — current copy (updated 2026-07-02)

## LINKEDIN — TONIGHT. Self-contained (no external link needed). Paste as-is.
All figures ledgered in PUBLISHED.md (64→76 #1, 1/37→6/37 #2, MBPP 65-vs-48, judge
regression). If the dev.to long-form (post-tonight.md) is live, add its URL as the
FIRST COMMENT, not in the post (LinkedIn suppresses posts with external links).

> Two weeks ago I started an experiment I couldn't get out of my head: if Claude Code
> disappeared tomorrow — priced out, rate-limited, whatever — what would I actually own?
>
> So I put tiny local models (2–3B) on a $250 Jetson and started building a harness
> around them, with one hard rule: no cloud fallback, ever. If the small model can't do
> something, restructure the work. Never rent a bigger brain.
>
> What I've measured so far, honest numbers first:
>
> My harness was throwing away right answers. About 60% of failures were correct logic
> with broken indentation — code that wouldn't even import. Fixing that
> deterministically (only when parsing fails) took a 100-problem bar from 64 to 76, and
> the gain held on the half I'd never tuned against. The model was better than my
> scaffolding.
>
> Small models are decent writers and terrible judges. Letting a 2B review its own
> passing solution against the spec made results worse — it rewrote working code into
> broken code. The same review pattern works fine with a large model. Model-as-judge
> has a capability threshold, and 2B is below it.
>
> Never let a small model decide WHAT to do. Open-ended planning is the least reliable
> thing you can ask of it; filling a bounded blank is the most. Deterministic control
> flow, the model fills the slots, and the test exit code is the only judge.
>
> The real frontier isn't benchmarks. On single functions the system scores 80%+ (a
> number I only half trust — those benchmarks leak into training data). On real commits
> from real repo histories, scored by the repo's own tests with the oracle hidden, it
> started at 1 out of 37. Structured decomposition — behavior spec, then tests from the
> spec, then code against the tests — has it at 6 of 37 today. That gap is the honest
> state of small-model coding, and mapping it is the whole point.
>
> And one model isn't enough — but two similar models isn't either. Qwen's 3B coder
> genuinely beats Gemma on standalone functions (65% vs 48% on MBPP). On the hard
> class? It fails the exact same problems. Correlated failures. Diversity only pays
> when models fail differently, so the roster grows by what each new model covers that
> the others can't.
>
> Why bother? Partly because the budgets are coming due — most of us are building on
> subsidized inference. Partly sovereignty: a future where every small team rents
> cognition from three companies isn't one I want to live in. Mostly because the
> question is genuinely open: how much of real software development can collapse into
> work a tiny, owned, always-on device does for free? Nobody has published an honest
> answer.
>
> I'm mapping it — the wins and the walls both. If you're running local models and
> hitting the same edges, I'd like to compare notes. And if you think I'm wrong
> somewhere, even better.

(Hashtags: none, or at most #LocalLLM #AIEngineering. The hook line must survive the
"...see more" fold — it does.)

## X — optional, same night or next day:

> Put tiny local models (2-3B) on a $250 Jetson with one rule: no cloud fallback, ever.
>
> Learned so far: small models are decent writers and terrible judges. My own harness
> was throwing away 60% of its correct answers. And real repos are 5x harder than
> benchmarks admit: 6/37 vs 80%+.
>
> Mapping the gap honestly — wins and walls both.

## Profiles (unchanged)

X bio:
> Building agentic engineering in the open. Mapping what tiny local models can actually
> do with the right harness — honest numbers, including the failures.

LinkedIn headline:
> Agentic engineering, in the open · Mapping the small-model frontier · Honest numbers,
> including the failures
