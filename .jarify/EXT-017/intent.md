# Intent

This spec exists to give the harness a *precise* repo-context retriever so that when the
small model is asked to fix or rewrite a function inside a real repository, it sees exactly
the surrounding code that function actually depends on — its module preamble and the
signatures/small bodies of the sibling helpers it directly calls — and nothing irrelevant.
A whole-file dump drowns a 2B model in noise; a bare stub starves it of the contract it
needs. The enriched retriever, built purely deterministically from the module's own source
(no LLM, no test/oracle reads), supplies the right middle ground and is wired in as an
opt-in `--retrieve` flag so its effect can be measured honestly against a byte-identical
baseline.

It converges toward the Prime Directive by advancing the L3 "precise retrieval / single-fact
injection" rung of the escalation ladder — closing a repo-comprehension harness gap for the
current model rather than reaching for a bigger one. It respects Tenet 1 (a deterministic
tool computes the context; the model only reasons over it), Tenet 3 (the retriever reads only
the module source, never hidden tests, and its opt-in wiring keeps the default path
reproducible for honest attribution), and serves the directive's goal of comprehending and
modifying real, complex repositories.
