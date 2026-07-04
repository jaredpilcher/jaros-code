# Intent

This spec exists to test a sharper hypothesis than "does this strategy crack the hard class":
does a solve strategy that shows no lift on hard repo tasks still help on EASIER,
from-the-spec tasks — or does it not help there either? It builds an honest A/B harness that
runs the bare baseline against the decomposition (EXT-020) and experiment-to-understand
(EXT-030) strategies over the same HumanEval/MBPP tasks, scored pass@1 with the identical
honest gate `pass1_eval` uses. Its non-negotiable rule is the CI-overlap test: a delta counts
as a real lift only when the strategy's Wilson95 CI does not overlap the baseline's, and an
overlap must be reported explicitly as "no significant lift" — a valid, informative outcome,
echoing the prior retrieval-fewshot negative (EXT-009).

It converges toward the Prime Directive by measuring levers honestly before adopting them —
the "probe before build, kill fast and log the negative" velocity doctrine — and by delegating
to the existing EXT-020/EXT-030 modules rather than reimplementing (no divergent second copy of
a strategy). It embodies Tenet 3: the oracle is score-only and never shown during generation,
every strategy is measured on the same held-out tasks, and statistical honesty (CI overlap) is
enforced so a non-result cannot be dressed up as a win.
