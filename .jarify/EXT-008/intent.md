# Intent

This spec exists to add the generative spine that the repair loop alone cannot provide,
serving Tenets 1, 3, 4 and 5 of PRIME-001. EXT-003 only exercises the regime where the spec
is already handed to us as a failing test — fixing existing code — but that is not "tell the
harness what you want and get a working system." This spec turns a natural-language intent
into a working implementation with NO test given to us, decomposing the judgement Claude
Code makes when it writes a test before code into a grain a 2B can attempt: a single-purpose
test-writer that only defines "correct" and never implements, handing its tests to the tool
plane, after which the implementation is built against them and scored. Its non-negotiable
purpose is to measure intent comprehension honestly: a system that writes both its own tests
and its own code could write a trivially-passing test and declare victory, so we defeat that
with a hidden oracle — a held-out test the harness never shows any agent, used only to score
— and treat the gap between "passes its own tests" and "passes the oracle" as the real,
un-gameable measure of whether the model understood the intent. The oracle is never written
into a build dir or shown to any agent; that honesty (Tenet 3) is the whole point. This is
the first generative grain of a planned family of grain types, each proven by from-intent
evals whose oracle pass-rate must climb over time.
