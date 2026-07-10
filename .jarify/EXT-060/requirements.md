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

### [REQ-4] INI-section config-query CLI task graded by the existing cli-exact oracle

A third held-out real-systems task -- an INI-section config-query CLI -- graded by the EXISTING
cli-exact exact-stdout oracle (`grade_real_system_task` `oracle_kind="cli-exact"`, reused from
`harness/system_suite.py`'s `exact_stdout` check variant, no new oracle). Leaves-OFF enforced
identically to the other two tasks; added to `REAL_SYSTEMS_TASKS`.

#### Acceptance Criteria
- [x] The task's sentence fully specifies the CLI contract (INI section/key parsing rules, exactly
      two argv args: section then key, exact stdout value + trailing newline, nonzero exit + no
      output when absent) with oracle-chosen argv/stdin/expected_stdout values echoed by the
      contract (no hidden key).
- [x] Graded by the existing cli-exact oracle (`grade_real_system_task` `oracle_kind="cli-exact"`):
      a correct INI-parsing CLI's exact stdout is verified; a wrong value/extra output is caught.
- [x] Leaves-OFF enforced (same two checks as REQ-1/REQ-2/REQ-3: static `leaf_for_spec` + post-build
      `build_path` check); no oracle leak into the build prompt.

### [REQ-5] Memoize/cache decorator library task graded by the existing import_driver oracle

A 4th held-out real-systems task -- a memoize/cache decorator library -- graded by the EXISTING
`import_driver` oracle (no new oracle code, mirrors REQ-3's `"import"` dispatch). A single-file
`memoize.py` module exports exactly one public function `memoize(maxsize=128)` that returns a
decorator; the decorated callable caches its return value keyed by its positional-argument tuple --
a repeated call with the SAME arguments returns the cached value WITHOUT re-invoking the wrapped
callable, while a call with NEW arguments does invoke it. Because `maxsize` is entirely defaulted,
`@memoize()` with zero arguments must work -- this ALSO exercises the EXT-036 REQ-45 deterministic
signature-contract-default repair on a SECOND reusable-library class (a generalization data point
beyond REQ-3's `retry.py`).

#### Acceptance Criteria
- [x] The task's sentence is contract-exact (filename `memoize.py`, the public function name +
      signature `memoize(maxsize=128)`, decorator/caching semantics, keying by the positional-
      argument tuple) with oracle-chosen call values echoed by the contract (no hidden key).
- [x] Graded by the existing `import_driver` oracle (`grade_real_system_task` `oracle_kind="import"`):
      a decorated spy invoked with the same argument twice then a different argument once must
      record exactly 2 underlying calls (the repeated call served from cache, never re-invoking the
      spy); a stub that never caches (always calls through) is caught.
- [x] Leaves-OFF enforced identically to REQ-2/REQ-3/REQ-4 (static `leaf_for_spec` + post-build
      `build_path` check); no oracle leak; added to `REAL_SYSTEMS_TASKS`.

### [REQ-6] File-organizer-by-extension CLI task graded by the existing fs oracle

A 5th held-out real-systems task, in a NEW domain -- a file-organizer CLI -- graded by the EXISTING
`fs_oracle` (no new oracle code, mirrors REQ-2's `"fs"` dispatch). A single-file `main.py` program
takes one command-line argument (a directory path) and moves every regular file directly inside
that directory (never recursing into subdirectories) into a subdirectory of that same directory
named after the file's lowercased extension with no leading dot (e.g. `report.TXT` -> `txt/
report.TXT`, preserving the file's own name and case); a file with no extension is moved into a
subdirectory named `noext`. It prints nothing on success and exits 0.

#### Acceptance Criteria
- [x] The task's sentence fully specifies the CLI contract (single directory argv, non-recursive
      immediate-children-only scope, lowercased-extension-without-dot subdirectory naming, the
      `noext` fallback for extensionless files, filename preserved unchanged, silent/exit-0 on
      success) with every oracle-checked path derivable from that same visible contract (no hidden
      key) and no leaf-library name-drop.
- [x] Graded by the existing `fs_oracle` (`grade_real_system_task` `oracle_kind="fs"`): a seeded
      directory with mixed-extension files (including an uppercase-extension file and a file with
      no extension) is correctly reorganized into per-lowercased-extension subdirectories plus
      `noext`, independently re-verified against the resulting tree; a build that fails to
      lowercase the extension, recurses into subdirectories, or leaves the originals in place is
      caught.
- [x] Leaves-OFF enforced identically to REQ-2/REQ-3/REQ-4/REQ-5 (static `leaf_for_spec` +
      post-build `build_path` check); no oracle leak; added to `REAL_SYSTEMS_TASKS`.
