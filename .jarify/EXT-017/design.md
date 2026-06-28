# Design: EXT-017 Enriched Precise Repo-Context Retrieval

## Motivation

The current `_file_context` baseline gives the 2B only the module preamble (imports +
module-level constants). When the target function calls helpers defined elsewhere in the
same module, the 2B is blind to their signatures and cannot use them correctly. This is
the GENERATION bottleneck identified after orchestration was confirmed to be near-maxed
(judgment ~80%).

Research anchor: arxiv 2503.20589 and the prior retrieval-fewshot negative
(`jaros-code-retrieval-fewshot-negative` memory) both confirm that PRECISE
direct-dependency context HELPS, while a naive whole-file/similar-code blob HURTS (up to
-15%). The design therefore retrieves ONLY names the target actually calls.

## Architecture

```text
commit_replay.py  (attempt_gherkin_jaros)
        │
        ├── --retrieve OFF (default)
        │       └── _file_context(orig[cf])          ← unchanged baseline
        │
        └── --retrieve ON
                └── enriched_file_context(orig[cf], name, max_chars=1500)
                        │   (harness/repo_context.py)
                        │
                        ├── [1] preamble: lines before first def/class/@
                        │
                        ├── [2] AST parse src → find FunctionDef named `name`
                        │         walk body → collect all called names (ast.Call)
                        │
                        └── [3] For each called name that IS a module-level function
                                (excluding `name` itself):
                                  - include signature always
                                  - include body only if func <= 10 lines
                                  - accumulate until max_chars cap
                                  - sort by call-count DESC (most-called first)
```

## Key Design Decisions

1. **Deterministic only**: AST walk — no LLM, no I/O, no network. Fits Tenet 1 (execution plane).
2. **Per-function context**: Each target function in the task loop gets its own enriched context
   (its own direct dependencies differ). The `ctx` dict in `attempt_gherkin_jaros` is built
   per `(cf, name)` when `--retrieve` is active.
3. **Additive, opt-in**: `--retrieve` flag. Default path is byte-identical to current code.
4. **Bounded**: `max_chars=1500` cap prevents the blob-hurts failure mode.
5. **Graceful fallback**: If parse fails or name not found, returns preamble-only (same as baseline).

## Call-count prioritization

When multiple helpers qualify, they are sorted by how many times their name appears in
the target's body (most-called first). This ensures the most-used helpers fit under the
cap before less-used ones are added.

## VERDICT: #18 enriched repo-context retrieval — PRUNED (2026-06-28)
At 44/101 the --retrieve arm had 6 pass vs the deterministic baseline's 8 on the SAME tasks — tracking ~parity-or-below, NO lift. Stopped early to pursue the drastic pivot (#23 pass@k probe). Honest non-win: precise direct-dependency repo-context did NOT lift the 2B's generation on the held-out repo bar (consistent with the prior retrieval-negative [[jaros-code-retrieval-fewshot-negative]]). --retrieve kept OPT-IN, never default. This is the last same-frame (single-shot generator-tweak) bet — the capability stayed ~18%. Pivoting to sample-at-scale + strong verifier (#23).
