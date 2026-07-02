---
id: EXT-035
title: The Foundry — build & ship real software (long-horizon instrument)
status: covered
priority: medium
implementation:
  - file: harness/cli_wrapper.py
    ranges:
      - - 14
        - 71
  - file: tests/test_ext035_cli_wrapper.py
    ranges:
      - - 14
        - 112
---

The **Foundry** (PURSUIT §5G/§7; scoreboard instruments #7 long-horizon + #8 ship-log) is where
jaros-code builds real software end-to-end, the jarify way, graded **binary ship/no-ship** by
running it. It measures what benchmarks and the single-function suite cannot: bootstrap, multi-file
coordination, "did it actually run." MEASURED 2026-07-02 (docs/GAP-MAP.md #7): single-file tools
ship; multi-file **coordination** (imports/interfaces) is a real 3B gap that free-form generation,
context, and repair all failed — but a **structured two-plane build** (deterministic wiring + the
model filling only logic bodies) SHIPS a 2-file tool at the mechanism level. This spec productionizes
that mechanism.

### [REQ-1] Deterministic CLI-wrapper synthesis (structured-build wiring, two-plane)

The mechanical cross-module coordination the 3B botches (correct import line, arg marshalling, calling
the entry function, printing) must be produced by the DETERMINISTIC plane, not the model. A pure
function synthesizes a runnable CLI wrapper for an already-built module, derived from that module's
AST — so the model is freed to do only the logic bodies it is good at (Tenet 1 two-plane; the measured
multi-file lever).

#### Acceptance Criteria
- [x] `harness/cli_wrapper.py::synthesize_cli(module_file, entry_func, *, arg_mode="ints") -> str`
      AST-parses `module_file`, verifies `entry_func` is a top-level function, and returns a runnable
      CLI wrapper string: imports `entry_func` from the module by name, reads `sys.argv[1:]`, marshals
      them per `arg_mode` (`"ints"` -> `[int(a) ...]`, `"strings"` -> the list as-is, `"raw"` -> the
      argv list), calls `entry_func(marshalled)`, and prints the result.
- [x] Raises a clear error if `entry_func` is not a top-level def in `module_file` (no silent wrong wiring)
- [x] The generated wrapper is import-correct: `from <module-stem> import <entry_func>` (NOT `import <entry>`)
      — the exact mismatch the 3B produced free-form
- [x] Offline unit test (`tests/test_ext035_cli_wrapper.py`, NO model): given a real stats fixture module
      exposing `stats(nums)->str`, `synthesize_cli` output, assembled beside the module, RUNS as
      `python cli.py 3 1 4 1 5` and prints the correct line; plus the error case + arg_mode variants.
