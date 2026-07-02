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
  - file: harness/foundry.py
    ranges:
      - - 23
        - 107
  - file: tests/test_ext035_foundry.py
    ranges:
      - - 14
        - 94
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

### [REQ-2] Assemble + ship-gate loop (the Foundry runner, deterministic)

The mechanism validated end-to-end 2026-07-02 (build lib bodies + synthesize CLI wiring → assemble →
run → ship) must be a reusable harness capability, not a one-off probe. The **assemble + ship-gate**
step is pure deterministic plane: given already-built module source (the MODEL plane's output) plus the
entry function and a set of ship cases, it wires the CLI (via REQ-1 `synthesize_cli`), assembles both
files in a sandbox, RUNS the tool as a program on each case, and grades binary ship/no-ship by exact
stdout match — gated on the RUN, never on the (flaky) build oracle. This decouples the gate from the
model so it is fully offline-testable, and appends the verdict to the ship-log (scoreboard #8).

#### Acceptance Criteria
- [x] `harness/foundry.py::assemble_and_ship(lib_code, module_name, entry_func, ship_cases, *, arg_mode="ints", work_dir=None) -> ShipResult`
      where `ship_cases` is a list of `(argv_list, expected_stdout)`. Writes `lib_code` as `<module_name>.py`
      in a sandbox dir, synthesizes `cli.py` via `synthesize_cli`, and runs each case as
      `subprocess.run([python, <abs cli.py>, *argv], cwd=sandbox)` with an ABSOLUTE script path (the probe-bug fix).
- [x] `ship` is True iff EVERY ship case's stdout stripped exactly equals its expected — gated on the RUN,
      not on any build oracle (the measured build_from_intent oracle-flake must not sink a correct tool)
- [x] `ShipResult` carries `ship: bool`, `cli_code: str`, and per-case `(argv, expected, got, ok)` results
      so a failure is diagnosable; the sandbox is isolated (localhost-only, no egress, no destructive ops per design safety envelope)
- [x] Appends one JSON line per run to the ship-log (`.jaros-data/foundry/ship_log.jsonl`) with project id, ship, and per-case summary
- [x] Offline unit test (`tests/test_ext035_foundry.py`, NO model, tmp_path): pass a CORRECT fixture
      `stats` lib string + 2 ship cases → `ship is True`; pass a WRONG lib string → `ship is False` with
      the failing case captured. Full suite stays green.
