# Implementation Tasks

### [TASK-1] Build harness/repo_context.py — enriched_file_context

Implement the deterministic enriched-context retriever as a new standalone module.

#### Steps
1. Create `harness/repo_context.py`.
2. Implement `enriched_file_context(src: str, name: str, max_chars: int = 1500) -> str`:
   a. Extract preamble (lines before first `def`/`class`/`@`) — same logic as `_file_context`.
   b. Parse `src` with `ast.parse`; find the `FunctionDef`/`AsyncFunctionDef` named `name`.
      If parse fails or name not found, return `preamble[:max_chars]`.
   c. Walk the target's body AST to collect all called names: traverse `ast.Call` nodes,
      collecting `node.func.id` (plain calls) and `node.func.attr` where `node.func` is
      an `ast.Attribute` (method calls — skip, only collect plain function calls that could
      refer to module-level siblings).
   d. Count call-frequency per name. Build a `{name -> source_text}` map of module-level
      functions (from `tree.body`) excluding the target itself.
   e. Sort called names by frequency DESC. For each, if its source is in the module map:
      - If the function is <= 10 lines: include full source.
      - Else: include signature line only.
      Accumulate into a `helpers` list until adding the next would exceed `max_chars - len(preamble) - overhead`.
   f. Return `preamble + "\n\n# Direct dependencies:\n" + "\n\n".join(helpers)`, truncated
      to `max_chars`.
3. Add a module-level `__all__ = ["enriched_file_context"]`.

#### Implements
- [REQ-1] Enriched context retriever — direct-dependency signatures + module API

### [TASK-2] Write tests/test_repo_context.py — offline unit tests

Write offline pytest tests that verify the enriched retriever's behavior precisely.

#### Steps
1. Create `tests/test_repo_context.py`.
2. Define a fixture module source string where:
   - Target function `target_fn` calls `helper_a` and `helper_b` (small, <= 10 lines each).
   - Unrelated function `unrelated_c` exists but is never called by `target_fn`.
   - Module has an import (`import os`) and a constant (`CONST = 42`).
3. Write `test_includes_direct_dependency`: call `enriched_file_context(src, "target_fn")`,
   assert `"def helper_a"` in result and `"def helper_b"` in result.
4. Write `test_excludes_unrelated`: assert `"def unrelated_c"` not in result.
5. Write `test_includes_preamble`: assert `"import os"` in result and `"CONST = 42"` in result.
6. Write `test_bounded_by_max_chars`: call with `max_chars=50`, assert `len(result) <= 50`.
7. Write `test_fallback_unknown_name`: call with name `"nonexistent"`, assert result is
   non-empty (preamble returned) and does not raise.
8. Write `test_fallback_bad_src`: call with `src="not valid python :::"`, assert no exception.
9. Write `test_large_helper_signature_only`: add a large helper (> 10 lines) called by target;
   assert only the `def large_helper(...):` line appears in context, not the full body.
10. Ensure `ast.parse` and import work: `import harness.repo_context` at top of test file.

#### Implements
- [REQ-1] Enriched context retriever — direct-dependency signatures + module API

### [TASK-3] Wire --retrieve flag into commit_replay.py

Wire the enriched retriever into `attempt_gherkin_jaros` and `run_gherkin_jaros_multi`
via an opt-in `--retrieve` CLI flag. Default behavior is byte-identical to now.

#### Steps
1. In `attempt_gherkin_jaros(repo, task, branch, timeout, max_fix)`: add a `retrieve: bool = False`
   parameter. When `retrieve=True`, replace the `ctx = {cf: _file_context(orig[cf]) for cf in files}`
   line with per-function enriched context built inside the per-function loop:
   `from harness.repo_context import enriched_file_context` (lazy import at top of function);
   for each `(cf, name, parent_src)`, compute `context = enriched_file_context(orig[cf], name)`.
   Pass this per-function `context` to `g_gherkin`, `g_code`, and `behavioral_solve_jaros` calls.
   When `retrieve=False` (default), keep `ctx = {cf: _file_context(orig[cf]) ...}` exactly as now.
2. In `run_gherkin_jaros(repo, branch, tasks)`: add `retrieve: bool = False` param; pass it
   through to each `attempt_gherkin_jaros` call. Update the result label to include `+retrieve`
   when `retrieve=True`.
3. In `run_gherkin_jaros_multi(repos_dir, tasks, agentic)`: add `retrieve: bool = False` param;
   pass to `attempt_gherkin_jaros`. Update its result label similarly.
4. In `__main__` (single-repo `--gherkin-loop --jaros` path): parse `retrieve = "--retrieve" in sys.argv`;
   pass to `run_gherkin_jaros(repo, branch, tasks, retrieve=retrieve)`.
5. In `__main__` (big-bar `--bar` path): parse `retrieve = "--retrieve" in sys.argv`; pass to
   `run_gherkin_jaros_multi(repos_dir, corpus, agentic=use_agentic, retrieve=retrieve)`.
6. Wrap added/modified lines in `# #EXT-017-REQ-2 Start` / `# #EXT-017-REQ-2 End` anchors.

#### Implements
- [REQ-2] Wire --retrieve opt-in flag into commit_replay __main__ and attempt_gherkin_jaros
