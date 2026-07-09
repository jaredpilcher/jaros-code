---
id: EXT-060
title: Real-systems capability suite (leaves-OFF North-Star instrument)
status: partial
priority: high
implementation: []
---

### [REQ-1] Suite scaffold + leaves-OFF pass@1 runner

A `harness/real_systems_suite.py` module with a `RealSystemTask` structure and a runner that builds each
task via `build_system` with the LEAF path disabled and grades ONLY by the task's independent oracle,
reporting pass@1 per class.

#### Acceptance Criteria
- [x] `RealSystemTask` carries name, cls, sentence, oracle_kind, and an oracle spec (declarative).
- [x] The runner builds each task with `build_system` and asserts NO leaf fingerprint fires for the spec
      (leaves-OFF); grades only by the task's own black-box oracle; reports per-class pass@1.
- [x] Honest/leak-free: expected values derive from the visible sentence; no reference implementation or
      suite-internal oracle leaks into the build prompt. A leaf-produced green is treated as a failure.

### [REQ-2] CSV→JSON group-by ETL task graded by fs_oracle

A real ETL system: read an input CSV, group by a named column, sum a numeric column, write the grouped
result to a JSON output file. Graded by `fs_oracle` (seed the input tree, run, inspect the output file
independently).

#### Acceptance Criteria
- [x] The task's sentence fully specifies the CLI contract (input path, group/sum columns, output path,
      JSON shape) with oracle-chosen values echoed by the contract (no hidden key).
- [x] Graded by `fs_oracle`: seed a CSV, run the built entrypoint, verify the output JSON file's exact
      content independently; a wrong grouping/sum is caught.

### [REQ-3] Retry/backoff decorator library task graded by import_driver

A real reusable library: a `retry(times, ...)` decorator that re-invokes a failing callable up to N
times with an injected sleep. Graded by `import_driver` (import the built module, drive with an injected
clock + a fail-then-succeed function; assert call-count and no real wall-clock sleep).

#### Acceptance Criteria
- [ ] The sentence specifies the importable public API (module + decorator signature/semantics).
- [ ] Graded by `import_driver` with an injected clock; asserts the decorator retries the right number of
      times and returns the eventual success, using no real sleep; a broken retry (wrong count) fails.
