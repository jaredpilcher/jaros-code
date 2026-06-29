# Intent

**EXT-027** adds a **verified-solution memory** scaffold -- a persistent store of
(problem, code) pairs where the code is known to have PASSED the deterministic test
gate.  When a new problem arrives, the harness looks up the most structurally similar
past verified solution and can inject it as a WORKED EXAMPLE into the solve prompt.

This is a **memory form**, not a search engine.  The retrieval is DETERMINISTIC --
signature overlap score, no embeddings -- so the retrieval-negative caution from the
prior RAG experiment (behavior-keyed RAG few-shot was a MEASURED NEGATIVE on the 2B,
bottleneck was reasoning not examples) applies here too.  The hypothesis is that a
VERIFIED (not just similar) worked example carries more signal than a behavioral
few-shot; but this is a HYPOTHESIS, not an assumption.

**The whole spec is subordinate to the KILL-TEST (REQ-2):**

> Build the scaffold, then KILL-TEST whether recalling a verified solution actually
> helps the SOLVE -- compare solve WITH vs WITHOUT injected verified examples on the
> honest bar (HumanEval/MBPP slice or the 101-bar); ONLY adopt into the default solve
> path if it shows a real, reproducible lift.  A NON-RESULT is the honest expected
> default; record it faithfully.  It must change the SOLVE, not just pad context.

Until the kill-test is run and shows a confirmed lift, the module is a scaffold only
(record and recall are wired; the inject path is NOT in the default solve).
