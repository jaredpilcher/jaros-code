# Implementation Tasks

### [TASK-1] Build harness/dependency_structure.py

Implement the deterministic AST dependency analysis module.

#### Steps
1. Create `harness/dependency_structure.py` with module docstring and
   `__all__ = ["method_dependencies", "dependency_brief", "cross_file_callers"]`.
2. Implement private helper `_sig(node, src) -> str`: returns the `def …:` first
   line of a function using `ast.get_source_segment`; falls back to a synthetic
   `def name(...):` string.
3. Implement private helper `_module_state_names(tree) -> set[str]`: collects
   names assigned at module level (`ast.Assign`, `ast.AnnAssign`, `ast.AugAssign`
   at `tree.body` depth only, excluding `FunctionDef`/`ClassDef`).
4. Implement private helper `_param_names(func_node) -> set[str]`: returns all
   parameter names (args, posonlyargs, kwonlyargs, vararg, kwarg).
5. Implement private helper `_called_plain_names(node) -> set[str]`: walks `node`
   collecting `ast.Call` targets that are bare `ast.Name` (not attribute calls).
6. Implement private helper `_state_used(func_node, mod_state) -> set[str]`:
   unions explicit `global` declarations (filtered to `mod_state`) with bare
   `ast.Name` references in `mod_state` not covered by params.
7. Implement `method_dependencies(source, target_name) -> dict`:
   a. `try: ast.parse(source)` except `SyntaxError` → return `base` (all-empty dict).
   b. Build `mod_funcs` dict from `tree.body`.
   c. Look up `target_name` in `mod_funcs`; if absent → return `base`.
   d. Compute `callees` (sorted by name), `callers` (sorted), `module_state_used`
      (sorted), `siblings_sharing_state` (sorted).
   e. Wrap with `# #EXT-028-REQ-1 Start` / `# #EXT-028-REQ-1 End`.
8. Implement `dependency_brief(deps) -> dict`:
   a. Extract target, callee names, caller names, state, siblings.
   b. Render multi-line string with "To change `{target}`, you may need to
      coordinate:" section listing each group.
   c. Append "Suggested order:" section: helpers → target → callers → state-siblings.
   d. Wrap with `# #EXT-028-REQ-2 Start` / `# #EXT-028-REQ-2 End`.
9. Implement `cross_file_callers(repo_root, target_module, target_name) -> list[dict]`:
   scan `.py` files in `repo_root` (skipping standard skip dirs), pre-filter by
   string occurrence of `target_name`, confirm via `ast.parse`, return
   `[{"caller": func_name, "file": rel_path}, ...]`.

#### Implements
- [REQ-1] AST dependency map
- [REQ-2] Decomposition brief

### [TASK-2] Write tests/test_dependency_structure.py

Write offline pytest tests verifying the dependency structure module.

#### Steps
1. Create `tests/test_dependency_structure.py`.
2. Define `_MODULE` fixture source: module with `COUNTER = 0` (module state),
   `helper(x)` (callee of `f`), `f(n)` calling `helper` with `global COUNTER`,
   `g(n)` calling `f`, and `reset()` also using `global COUNTER`.
3. Class `TestMethodDependencies`:
   - `test_callees_contains_helper`: deps of `f` has `helper` in callees.
   - `test_callers_contains_g`: deps of `f` has `g` in callers.
   - `test_module_state_used_contains_counter`: COUNTER in module_state_used.
   - `test_callee_has_signature`: the helper callee dict has a `"def helper"` signature.
   - `test_helper_is_not_a_caller`: `helper` not in callers of `f`.
   - `test_target_not_in_callees`: `f` not in its own callees.
   - `test_siblings_sharing_state`: `reset` in siblings_sharing_state of `f`.
   - `test_parse_error_no_crash`: malformed source → empty callees/callers, no raise.
   - `test_target_not_found_partial`: missing target → empty lists, no raise.
   - `test_return_structure`: all five keys present in result.
   - `test_callers_of_helper`: from helper's perspective, `f` is in callers.
   - `test_no_module_state_for_pure_function`: pure function → empty state lists.
4. Class `TestDependencyBrief`:
   - `test_brief_contains_target`: target name in brief.
   - `test_brief_contains_caller_names`: caller names in brief.
   - `test_brief_contains_callee_names`: callee names in brief.
   - `test_brief_contains_state_names`: state names in brief.
   - `test_brief_mentions_suggested_order`: "order" in brief (case-insensitive).
   - `test_brief_is_string`: result is non-empty str.
   - `test_brief_empty_deps`: all-empty deps → no crash, target name in brief.

#### Implements
- [REQ-1] AST dependency map
- [REQ-2] Decomposition brief
