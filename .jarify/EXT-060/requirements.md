---
id: EXT-060
title: Real-systems capability suite (leaves-OFF North-Star instrument)
status: covered
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

A real reusable library: a single-file `retry.py` module exporting a `retry(times, exceptions=Exception)`
decorator that re-invokes a wrapped callable up to `times` attempts on the given exception(s), sleeping
between attempts, and returns the first success (re-raising if all attempts fail). Graded by
`harness/import_driver.py`: import the built module in a fresh subprocess, apply the decorator to a
fail-then-succeed callable with an INJECTED sleep, and assert the call-count and eventual return value
with NO real wall-clock sleep.

#### Acceptance Criteria
- [x] The task's sentence is contract-exact: names the module filename (`retry.py`), the public decorator
      name + signature/semantics (attempts, which exceptions, return-first-success, re-raise-on-exhaust),
      with oracle-chosen call parameters echoed by the contract (no hidden key).
- [x] Graded by `import_driver` with an injected clock/sleep: a fail-twice-then-succeed callable wrapped
      by `retry(times=3)` returns the success and is called exactly 3 times, using no real sleep; a broken
      retry (wrong count, or gives up early) FAILS. Leaves-OFF (no leaf may count as a pass); no oracle leak.
