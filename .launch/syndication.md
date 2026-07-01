# Syndication — current copy (updated 2026-07-01)

## LinkedIn — tomorrow morning (8–9am). Paste as-is, fill [POST_URL].

> I've spent the last ten days on a side experiment: can a 2B model running on a $250
> Jetson cover most of what I use Claude Code for?
>
> Short answer: not yet. But the numbers surprised me in both directions.
>
> A few things I measured along the way:
>
> The harness was throwing away right answers. ~60% of my failures were correct logic
> with broken indentation. Fixing that (deterministically, only when the code fails to
> parse) was worth +12% on a held-out set. The model was better than my scaffolding.
>
> Small models are decent writers and terrible judges. Letting the 2B review its own
> passing solution against the spec made results *worse* — it rewrote working code into
> broken code. The same review pattern works fine with a large model. Model-as-judge
> has a capability threshold.
>
> The real frontier isn't benchmarks. On single functions the harness scores 80%+. On
> real commits from real repo histories, scored by the repo's own tests: about 10%.
> That gap is the honest state of small-model coding, and it's the thing I'm mapping.
>
> Full write-up with all the numbers (including the failed ideas, which taught me
> more): [POST_URL]
>
> Curious whether others running local models are seeing the same walls.

(No hashtags needed; maybe #AI #LocalLLM if you want reach. Keep it at two.)

## X — optional, only if you have an account set up. Single post, not a thread:

> Spent 10 days trying to replace Claude Code with a 2B model on a $250 Jetson.
>
> Learned: small models are decent writers and terrible judges. And my harness was
> throwing away 60% of its correct answers over indentation.
>
> Honest numbers, including the wall: [POST_URL]

## Profiles (unchanged — set these whenever)

X bio:
> Building agentic engineering in the open. Mapping what tiny local models can actually
> do with the right harness — honest numbers, including the failures.

LinkedIn headline:
> Agentic engineering, in the open · Mapping the small-model frontier · Honest numbers,
> including the failures
