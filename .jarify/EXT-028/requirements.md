---
id: EXT-028
title: Method Dependency Structure for Decomposition
status: covered
priority: high
implementation:
  - file: harness/dependency_structure.py
    ranges:
      - - 1
        - 150
  - file: tests/test_dependency_structure.py
    ranges:
      - - 1
        - 120
---

Deterministic AST analysis that maps a target function's dependencies to GUIDE
decomposition of hard multi-step-repo changes.  This tool answers: "if I change
`f`, what else must change, and in what order?"  It feeds EXT-028 consumers
(decomposition / collaboration / experiment-to-understand, tracking hard
multi-step-repo class).  Two-plane: the tool is purely deterministic (Tenet 1);
the model uses its output to decompose.

### [REQ-1] AST dependency map

`harness/dependency_structure.py` exposes `method_dependencies(source, target_name) -> dict`
— a deterministic analysis of a Python MODULE source for the target function.

The returned structure:
```
{
  "target":                  str,
  "callees":                 [{"name": str, "signature": str}, ...],
  "callers":                 [str, ...],
  "module_state_used":       [str, ...],
  "siblings_sharing_state":  [str, ...],
}
```

Where:
- **callees**: module-level functions the target CALLS (with their `def` signatures).
- **callers**: other module-level functions that CALL the target.
- **module_state_used**: module-level variable names the target reads or writes
  (including via `global` statements).
- **siblings_sharing_state**: other functions that touch at least one of the same
  module-level state names — likely to need coordinated change.

Uses `ast` (walk `FunctionDef` bodies for `Call`/`Name`/`Global` nodes; resolve
names against module-level defs).  Must be purely deterministic, no LLM, no I/O.

#### Acceptance Criteria
- [ ] `harness/dependency_structure.py` importable with no network/LLM/I/O
- [ ] `method_dependencies(source, target_name)` callable; returns the five-key dict
- [ ] For a module with `f()` calling `helper()`, `g()` calling `f()`, and shared
      module state: callees contains `helper`, callers contains `g`, and
      `module_state_used` includes the shared name
- [ ] Parse errors return a partial result (empty lists) — never raises
- [ ] Target not found returns a partial result (empty lists) — never raises
- [ ] Results are sorted for determinism (alphabetical within each list)

### [REQ-2] Decomposition brief

`dependency_brief(deps: dict) -> str` renders the `method_dependencies` result as
a concise, decomposition-oriented brief for a solve prompt.

Format: "To change `{target}`, you may need to coordinate: callers [...] that
depend on its behavior; helpers it uses [...]; shared state [...].  Suggested
order: ..."

This is the artifact the decomposition / solve step consumes.

#### Acceptance Criteria
- [ ] `dependency_brief(deps)` returns a non-empty string
- [ ] The brief contains the target name, all caller names, all callee names, and
      all shared state names from `deps`
- [ ] The brief includes a "Suggested order" section listing the change sequence
- [ ] Handles empty `deps` (all lists empty) without crashing
- [ ] Pure function — no LLM, no I/O, no network
