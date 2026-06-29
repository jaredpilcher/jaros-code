# Design: EXT-028 Method Dependency Structure for Decomposition

## Motivation

The hard multi-step-repo class fails partly because a change must RIPPLE through
related methods and the solve doesn't see the structure.  A deterministic
method-dependency map shows WHERE a change must propagate and in what order,
turning a hard whole-task into a dependency-ordered decomposition.

Research anchor: the "Agentless" family of papers and the SWE-bench literature show
that localisation + dependency ordering is the key bottleneck before generation; this
tool is the localisation half for single-module changes.

## Architecture

```text
Caller (solve prompt builder / decomposition step)
        │
        ▼
method_dependencies(source: str, target_name: str) -> dict
        │   harness/dependency_structure.py
        │   Pure Python stdlib ast — deterministic, offline, Tenet-1 compliant
        │
        ├── ast.parse(source)           [SyntaxError → partial/empty, no crash]
        │
        ├── [module scan]
        │     ├── module_funcs  : {name → FunctionDef}   (from tree.body)
        │     └── mod_state     : {name}                  (Assign/AnnAssign at top level)
        │
        ├── [callees]  walk target FunctionDef for ast.Call + ast.Name nodes
        │               → intersection with module_funcs, excluding self
        │               → return [{name, signature}, ...]
        │
        ├── [callers]  walk each OTHER module func for calls to target_name
        │               → return [name, ...]
        │
        ├── [module_state_used]
        │     walk target for ast.Global names + bare ast.Name refs in mod_state
        │     → return [name, ...]
        │
        └── [siblings_sharing_state]
              for each other func: _state_used(fn, mod_state) ∩ target_state ≠ ∅
              → return [name, ...]

        ▼
dependency_brief(deps: dict) -> str
        │   Pure string rendering — no I/O, no model
        │
        └── "To change `{target}`, you may need to coordinate: …
             Suggested order: helpers → target → callers → state-siblings"

        ▼  (optional, bounded)
cross_file_callers(repo_root, target_module, target_name) -> list[dict]
        │   Scans repo .py files; pre-filters by target_name string occurrence;
        │   confirms via ast.parse; bounded to repo root (skips .git, __pycache__, etc.)
        └── [{"caller": func_name, "file": rel_path}, ...]
```

## Key Design Decisions

1. **Deterministic only**: stdlib `ast` walk — no LLM, no I/O, no network.
   Fits Tenet 1 (execution plane).
2. **Never crashes**: `try/except SyntaxError` around `ast.parse`; partial result
   returned when target is not found.  Callers may always use the result dict.
3. **Sorted outputs**: All list outputs are alphabetically sorted so results are
   deterministic across Python runs.
4. **Heuristic for state detection**: `global` statements are authoritative;
   bare `Name` references to module-level vars are included conservatively.
   Over-reporting (false dependency) is safer than under-reporting (missed one).
5. **Feeds decomposition consumers**: `dependency_brief` is the artefact that the
   solve step consumes — its format is stable and machine-readable-friendly
   (named sections, consistent wording, "Suggested order" always present).
6. **Cross-file callers optional + bounded**: `cross_file_callers` is a bounded
   search over the repo root; the pre-filter (name string scan) avoids full
   re-parsing of every file.

## Relation to Other Specs

- **EXT-017** (enriched repo-context): provides per-function dependency context
  for the GENERATOR; EXT-028 provides STRUCTURAL dependency maps for DECOMPOSITION.
  Complementary, not overlapping.
- **EXT-003** (multi-file fix): uses import-graph for file localization; EXT-028
  uses AST dependency graph for change-order reasoning.  Share the `multi_file`
  import helpers for `cross_file_callers`.
- Feeds: hard multi-step-repo class decomposition, collaboration, and
  experiment-to-understand flows.
