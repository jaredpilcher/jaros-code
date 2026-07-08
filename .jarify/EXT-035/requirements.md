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
        - 134
  - file: tests/test_ext035_foundry.py
    ranges:
      - - 14
        - 94
  - file: tests/test_ext035_ship_completeness.py
    ranges:
      - - 12
        - 89
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

### [REQ-3] Deterministic import-resolver — fix the model's cross-module import-emission

MEASURED 2026-07-02 (docs/GAP-MAP.md #7, coordination axis): with dependency modules available in the
build env (REQ-4 EXT-008), gemma still fails to reliably EMIT the cross-module import — it references a
dep symbol without importing it (NameError) or guesses the wrong module name (`FITS_record` vs `FITS_rec`,
`module_accumulator` vs `accumulator`, `codec.encode` not imported). Import-emission is model-choice-limited
and name-dependent, so multi-module builds don't coordinate even when the dep is present. The FIX is
two-plane (Tenet 1): the model writes the logic; the DETERMINISTIC plane resolves the import lines. A pure
AST function injects `from <mod> import <name>` for each name the module USES but has not defined/imported,
when that name is a known export of a supplied dependency — turning the model's import-omission into a
non-issue. Wired into `build_from_intent`'s `deps` path so a generated module that merely *references* a
dep symbol still passes its oracle.

#### Acceptance Criteria
- [x] `harness/import_wiring.py::resolve_imports(module_code: str, dep_exports: dict[str, list[str]]) -> str`
      (pure, offline, AST, NO model): parse `module_code`; collect names that are USED but not bound
      (not defined, not already imported, not a builtin); for each used-unbound name that is an exported
      name of some dep in `dep_exports` (module-stem → [names]), prepend `from <stem> import <name>`.
      Deterministic order (sorted), dedup, idempotent (re-running injects nothing new). Tag `# #EXT-035-REQ-3`.
- [x] Does NOT inject for names already imported/defined/builtin, and does NOT touch the model's logic body
- [x] Wired into `harness/intent_loop.py::build_from_intent`: when `deps` is supplied, run `resolve_imports`
      on the model's generated code (with `dep_exports` derived from the `deps` sources via AST) BEFORE the
      oracle runs — so a module that references a dep symbol without importing it still passes. Backward-
      compatible: no-op when `deps` is falsy or the code already imports correctly.
- [x] Offline tests (`tests/test_ext035_import_wiring.py`, NO model): (a) `resolve_imports("def pack(items):\n    return '|'.join(encode(i) for i in items)\n", {"codec": ["encode"]})`
      injects `from codec import encode` and leaves `pack` intact + is idempotent; (b) an already-correct
      import is unchanged; (c) an unrelated undefined name is NOT injected. Full suite stays green.
- [x] BOTH import forms handled: MEASURED 2026-07-02 — with REQ-3 wired, gemma wrote a CORRECT coordinating
      `packer` that calls `codec.encode(item)` (module-qualified form) but omitted `import codec`; the
      used-unbound name is the MODULE `codec` (referenced via `codec.<attr>`), which `resolve_imports`'
      bare-name path did not inject. VERIFIED: prepending `import codec` makes it ship. So `resolve_imports`
      must ALSO inject `import <stem>` when a used-unbound name equals a supplied dep's module STEM (detected
      via `<stem>.<attr>` attribute access, i.e. an `ast.Attribute` whose `.value` is an unbound `ast.Name`
      matching a dep stem). This unlocks genuine multi-component coordination for the (common) qualified form.
      Offline test: a `packer` using `codec.encode(...)` + `dep_exports={"codec":[...]}` → `import codec`
      injected, and idempotent; bare-name form still works. Full suite green.
- [x] Also wired into `harness/system_builder.py::build_system`'s OWN multi-module BUILD/ASSEMBLE
      path, not just `build_from_intent`'s externally-supplied `deps` path: MEASURED 2026-07-08 — a
      clean `build_system` run generated `command_processor.py` starting `class
      CommandProcessor(DataManager):` with no `from data_manager import DataManager`, so every
      module generated in the SAME build that references a SIBLING module (not an external `deps`
      dict) never got its missing import repaired, causing a NameError at import time and every
      acceptance check to fail. Fix: immediately after the per-module BUILD loop populates `built`
      and before the ASSEMBLE step, `build_system` derives a sibling `dep_exports` map via
      `harness.intent_loop._derive_dep_exports(built)` and runs `resolve_imports` over every module
      against its own siblings (excluding itself); no-op for single-module builds (byte-identical).
      Offline test (`tests/test_ext035_sibling_import_repair.py`, NO model): the exact MEASURED
      repro is fixed and imports cleanly, an already-correct sibling import is left byte-unchanged
      (idempotent), and a name no sibling exports is not invented. Full suite stays green.

### [REQ-4] Ship-gate heeds module completeness (don't ship an incomplete build)

MEASURED gap (docs/GAP-MAP.md #7, 4-module scale-test 2026-07-02): the ship-gate grades ship/no-ship purely on
whether the assembled tool's CLI `ship_cases` produce the right stdout. But a dependency MODULE can be INCOMPLETE and
still ship if the CLI cases don't exercise the missing part — measured: gemma built a codec with a correct `encode`
but OMITTED `decode`; its `build_from_intent` oracle CAUGHT it (`oracle_pass=False`), yet the CLI cases (encode-path
only) passed → SHIP=True on an incomplete module. Claude Code would ship a COMPLETE module. Deterministic two-plane
fix: let the ship-gate account for per-module oracle results — a module that failed its own oracle must block/flag
the ship, not pass on run-cases alone.

#### Acceptance Criteria
- [x] `assemble_and_ship` gains an optional keyword `module_oracles: dict[str, bool] | None = None` (module name →
      did its build_from_intent oracle pass). Default `None` → behavior byte-identical to today (backward compatible)
- [x] When `module_oracles` is provided and ANY value is False, `ship` is False regardless of the CLI cases — an
      incomplete build does not ship. The CLI cases still RUN (diagnostic), so `cases` is still populated
- [x] `ShipResult` gains `incomplete_modules: list[str]` (the module names whose oracle was False, sorted;
      empty when `module_oracles` is None or all True). The ship-log line includes it
- [x] Offline test (`tests/test_ext035_ship_completeness.py`, NO model): (a) a CORRECT single-module lib + passing
      cases + `module_oracles={'lib': True}` → ship True, incomplete_modules []; (b) the SAME correct lib + passing
      cases but `module_oracles={'lib': True, 'dep': False}` → ship False, incomplete_modules ['dep'], cases still
      ran + all ok; (c) `module_oracles=None` → identical result to omitting it (backward compat). Full suite green
