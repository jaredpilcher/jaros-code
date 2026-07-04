# Intent

This spec exists to change the SOLVE PROCESS rather than the model or the prompt: strong coding
agents (Claude Code, SWE-agent) crack hard repo tasks by EXPLORING and OBSERVING before writing
a fix, and this spec brings that pattern to jaros-code as a principled experiment → observe →
understand → solve loop. Where collaborative-solve (EXT-029) changed WHO writes the code and
still returned 0/6 on the hard class, this changes whether the solver UNDERSTANDS the problem
first. The model proposes a next experiment from a bounded, safe menu — run the failing test and
capture the real traceback, call the target with literal inputs and observe the result, or read
a related function's source — and an accumulating understanding scratchpad (lightweight working
memory) informs the final fix.

It converges toward the Prime Directive by realizing the directive's first-class
investigation loop (intent point (e): investigate by observing a system before acting) while
holding the two planes strictly apart (Tenet 1): `propose_fn` emits only inert Decisions and the
deterministic execution plane runs the bounded experiments — no arbitrary code execution. It
upholds Tenet 3: the hidden oracle is the sole arbiter of `solved`, never shown to the proposer
or solver, and results are reported honestly against the 0/6 collaborative-solve baseline.
