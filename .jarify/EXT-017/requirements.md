---
id: EXT-017
title: Enriched Precise Repo-Context Retrieval
status: covered
priority: high
implementation:
  - file: harness/repo_context.py
    ranges:
      - - 1
        - 120
  - file: harness/commit_replay.py
    ranges:
      - - 224
        - 234
      - - 548
        - 682
  - file: tests/test_repo_context.py
    ranges:
      - - 1
        - 120
---

### [REQ-1] Enriched context retriever — direct-dependency signatures + module API

`harness/repo_context.py` provides a `enriched_file_context(src, name, max_chars)` function
that returns a richer context string than the current `_file_context` baseline.

The enriched context MUST include:
1. Module preamble: imports + module-level constants/__all__/sentinels (same as `_file_context`).
2. SIBLING/HELPER functions the target function `name` DIRECTLY depends on — i.e. any
   function whose name appears as a called name in the target's AST body. Included as:
   - Full signature line (`def helper(...):`), always.
   - Short body (up to 8 lines) ONLY when the total function is <= 10 lines; otherwise
     signature only (to bound context size).
3. PRECISION constraint: ONLY direct-dependency functions (names called in the target's body).
   Unrelated sibling functions whose names do NOT appear in the body are EXCLUDED.
4. BOUNDS: total output is capped at `max_chars` (default 1500). If adding a helper would
   exceed the cap, it is omitted (most important helpers first — called most times).
5. The function MUST be purely deterministic — no LLM call, no network, no file I/O.
6. If `name` is not found in `src` or the source cannot be parsed, falls back to
   `_file_context`-equivalent (preamble only, same max_chars cap).

HONESTY: the function reads ONLY the module's own source (`src` parameter). It NEVER
reads test files, oracle outputs, or hidden test sources.

#### Acceptance Criteria
- [ ] `harness/repo_context.py` exists and is importable without any network/LLM
- [ ] `enriched_file_context(src, name, max_chars=1500)` is callable
- [ ] For a module where target `A` calls helper `B` (and unrelated `C` exists), context includes B's signature and excludes C
- [ ] Total context length <= max_chars
- [ ] Falls back gracefully when target name is not found
- [ ] `ast.parse(src)` succeeds on any well-formed module passed in — no import side-effects
- [ ] `python -m pytest tests/test_repo_context.py -q` passes offline

### [REQ-2] Wire --retrieve opt-in flag into commit_replay __main__ and attempt_gherkin_jaros

When `--retrieve` is passed on the CLI:
1. In `attempt_gherkin_jaros` (and `run_gherkin_jaros_multi` via the same call), the
   per-file context is built with `enriched_file_context(orig[cf], name, max_chars=1500)`
   instead of `_file_context(orig[cf])`. Each function in the target list gets its own
   enriched context (the target name varies per function).
2. When `--retrieve` is NOT passed (default), behavior is BYTE-IDENTICAL to the current
   code — `_file_context` is called exactly as before. No regression.
3. The `--bar big` path also respects `--retrieve` when combined with
   `--gherkin-loop --jaros`.
4. The result label printed by `run_gherkin_jaros` / `run_gherkin_jaros_multi` includes
   `+retrieve` when the flag is active, for honest result attribution.

#### Acceptance Criteria
- [ ] `python -m harness.commit_replay --bar big --gherkin-loop --jaros --retrieve` is a valid invocation
- [ ] Without `--retrieve`, all existing code paths are byte-identical to before (no regression)
- [ ] With `--retrieve`, `attempt_gherkin_jaros` uses `enriched_file_context` per target function
- [ ] Result label includes `+retrieve` when active
- [ ] `python -m pytest -q` passes (no regressions in full suite)
