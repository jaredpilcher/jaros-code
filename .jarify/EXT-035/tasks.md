# Implementation Tasks — EXT-035 The Foundry

### [TASK-1] Deterministic CLI-wrapper synthesizer (REQ-1)

Build `harness/cli_wrapper.py::synthesize_cli` — the deterministic multi-file wiring the two-plane
structured build needs. Pure function + AST; NO model calls. This productionizes the mechanism
validated 2026-07-02 (hand-templated then; now general + AST-derived + tested).

#### Steps
1. `harness/cli_wrapper.py`: `synthesize_cli(module_file: str, entry_func: str, *, arg_mode: str = "ints") -> str`.
   Parse `module_file` with `ast`; confirm `entry_func` is a top-level `FunctionDef` (else raise ValueError
   with a clear message). Derive the import module name from the file stem. Return a wrapper string:
   `import sys\nfrom <stem> import <entry_func>\n\nif __name__ == "__main__":\n    args = sys.argv[1:]\n`
   + marshalling per arg_mode (`ints`: `nums = [int(a) for a in args]; print(<entry>(nums))`;
   `strings`: `print(<entry>(args))`; `raw`: `print(<entry>(args))`) — keep it minimal + correct.
   Tag `# #EXT-035-REQ-1`.
2. `tests/test_ext035_cli_wrapper.py` (offline, NO model, use tmp_path): write a fixture module
   `statslib.py` with a real `def stats(nums): return f"count={len(nums)} sum={sum(nums)} ..."` (correct impl);
   call `synthesize_cli(fixture, "stats", arg_mode="ints")`; write the output as `cli.py` beside it;
   `subprocess.run([sys.executable, <abs cli.py>, "3","1","4","1","5"], cwd=tmpdir)` and assert stdout is
   the correct line. Add: import line is `from statslib import stats` (not `import stats`); ValueError when
   entry_func absent; a `strings`/`raw` arg_mode case. Full suite stays green.
3. Add the REQ-1 traceability entry to `.jarify/EXT-035/index.json` (create it). Do NOT touch sibling specs.

#### Implements
- [REQ-1] Deterministic CLI-wrapper synthesis (structured-build wiring, two-plane)

### [TASK-2] Assemble + ship-gate loop — the Foundry runner (REQ-2)

Build `harness/foundry.py::assemble_and_ship` — the deterministic assemble+run+grade step that
composes REQ-1's `synthesize_cli` into a reusable capability. NO model calls in this function (the
model plane's lib bodies are passed in), so the ship-gate logic is fully offline-testable and the
build-oracle flake cannot sink a correct tool. Productionizes the end-to-end mechanism validated
2026-07-02 (probe `.jaros-data/foundry/structured_v2.py`).

#### Steps
1. `harness/foundry.py`: define `ShipResult` (dataclass: `ship: bool`, `cli_code: str`,
   `cases: list` of `{argv, expected, got, ok}`, `project: str`). Implement
   `assemble_and_ship(lib_code, module_name, entry_func, ship_cases, *, arg_mode="ints", work_dir=None, project="foundry") -> ShipResult`:
   create/clean a sandbox dir (default under `.jaros-data/foundry/`), write `lib_code` as
   `<module_name>.py`, call `synthesize_cli(<abs module path>, entry_func, arg_mode=arg_mode)`, write
   `cli.py`, then for each `(argv, expected)` run `subprocess.run([sys.executable, <abs cli.py>, *argv],
   capture_output=True, text=True, timeout=15, cwd=sandbox)` and record `ok = stdout.strip() == expected`.
   `ship = all(ok)`. Tag `# #EXT-035-REQ-2`.
2. Append one JSON line to `.jaros-data/foundry/ship_log.jsonl` (project, ship, per-case ok summary).
3. `tests/test_ext035_foundry.py` (offline, NO model, tmp_path): a CORRECT `stats` fixture lib string +
   2 ship cases → `ship is True`; a WRONG lib string (e.g. off-by-one sum) → `ship is False` and the
   failing case's `got != expected` is captured. Assert full suite stays green (`python -m pytest -q`).
4. Add the REQ-2 traceability entry to `.jarify/EXT-035/index.json`. Do NOT touch sibling specs.

#### Implements
- [REQ-2] Assemble + ship-gate loop (the Foundry runner, deterministic)

### [TASK-3] Deterministic import-resolver + wire into build_from_intent (REQ-3)

Build `harness/import_wiring.py::resolve_imports` (pure AST, no model) — the deterministic fix for the
MEASURED cross-module import-emission gap — and wire it into `build_from_intent`'s `deps` path so a
generated module that references a dep symbol without importing it still passes its oracle.

#### Steps
1. `harness/import_wiring.py`: `resolve_imports(module_code, dep_exports)`. AST-parse `module_code`;
   compute the set of bound names (module-level defs/classes/assignments + already-imported names +
   function params are local, so focus on module-level `ast.Name` loads not bound at module scope) and
   the set of USED names (`ast.Name` in Load context anywhere). For each used-but-unbound name that is in
   some dep's export list (`dep_exports`: stem → [names]), collect `from <stem> import <name>`. Prepend the
   deduped, sorted import lines to `module_code`. Idempotent (skip a name already imported). Use `builtins`
   to exclude builtin names. Keep it conservative — when unsure, do NOT inject (never break working code).
   Tag `# #EXT-035-REQ-3`.
2. `harness/intent_loop.py`: in `build_from_intent`, when `deps` is truthy, derive `dep_exports` from each
   dep source via AST (top-level def/class names per dep stem), and run `resolve_imports(generated_code,
   dep_exports)` on the model's output BEFORE `_run_oracle`. No-op when `deps` is falsy. Tag `# #EXT-035-REQ-3`.
   Keep it minimal + backward-compatible (existing single-module builds unchanged).
3. `tests/test_ext035_import_wiring.py` (offline, NO model): the three cases in REQ-3's last criterion
   (inject-missing + idempotent; already-correct-unchanged; unrelated-name-not-injected). Plus a focused
   check that the build_from_intent wiring calls resolve_imports on the deps path (can be a small unit test
   of the derive-dep_exports helper if isolating the model call is hard). Tag `# #EXT-035-REQ-3`.
4. Run `python -m pytest -q` (root pytest.ini scopes to tests/); confirm full suite green, report counts.
5. Add the REQ-3 traceability entry to `.jarify/EXT-035/index.json` (preserve REQ-1/REQ-2). Do NOT touch sibling specs.

#### Implements
- [REQ-3] Deterministic import-resolver — fix the model's cross-module import-emission

### [TASK-4] resolve_imports: also inject `import <module>` for qualified `<stem>.attr` refs (REQ-3)

MEASURED: with REQ-3 wired, gemma wrote a CORRECT coordinating `packer` using `codec.encode(item)` but
omitted `import codec`; `resolve_imports` only injected bare-name `from X import name`, so the qualified
form was missed. Extend it to handle BOTH import forms. Small, surgical extension to the tool built in TASK-3.

#### Steps
1. `harness/import_wiring.py::resolve_imports`: in addition to the existing bare-name path, detect
   used-unbound MODULE references — walk for `ast.Attribute` nodes whose `.value` is an `ast.Name` in Load
   context that is NOT bound (not defined/imported/builtin) and whose id equals a supplied dep's module STEM
   (a key of `dep_exports`). For each such stem, inject `import <stem>` (deduped, sorted with the existing
   `from`-imports, idempotent — skip if `import <stem>` already present). Keep conservative (only inject for
   stems that are actual `dep_exports` keys). Tag `# #EXT-035-REQ-3` (same REQ).
2. `tests/test_ext035_import_wiring.py`: add a case — `resolve_imports("def pack(items):\n    return '|'.join(codec.encode(i) for i in items)\n", {"codec": ["encode"]})` injects `import codec`, leaves `pack` intact,
   is idempotent, and does NOT also add a spurious `from codec import ...`. Keep the existing bare-name tests green.
3. `python -m pytest -q` (root pytest.ini → tests/); full suite green, report counts.
4. Update the REQ-3 traceability ranges in `.jarify/EXT-035/index.json` if line numbers shift. Do NOT touch sibling specs.

#### Implements
- [REQ-3] Deterministic import-resolver — fix the model's cross-module import-emission (both import forms)

### [TASK-5] Wire resolve_imports into build_system's multi-module BUILD/ASSEMBLE path (REQ-3)

MEASURED REPRO 2026-07-08 (a clean gemma `build_system` run): a 3-module `todo-list-cli` build
wrote `command_processor.py` starting `class CommandProcessor(DataManager):` with NO
`from data_manager import DataManager` -> `NameError` at import of `command_processor` ->
every acceptance check fails rc=1 -> 0/3. `harness/import_wiring.py::resolve_imports`
(TASK-3/TASK-4) already handles this exact shape (base-class reference is an `ast.Name` Load
node caught by `_used_names`) — it is wired into `build_from_intent`'s externally-supplied
`deps` path (TASK-3), but `harness/system_builder.py::build_system` NEVER runs it over its
OWN multi-module BUILD output, so a module that references a SIBLING module generated in the
SAME build (not an external `deps` dict) never gets its missing import repaired. This task
closes that wiring gap — purely mechanical, no oracle/gate change.

#### Steps
1. `harness/system_builder.py::build_system`: immediately after the per-module BUILD loop
   (the loop that populates `built: dict[str, str]`) and before the `# 3. ASSEMBLE` step,
   derive a sibling `dep_exports` map by calling `harness.intent_loop._derive_dep_exports(built)`
   (reusing the existing AST-derivation helper unchanged — `built`'s `{name.py: code}` shape
   already matches `_derive_dep_exports`'s expected `deps` input). For each module name in
   `built`, build its own sibling view (`dep_exports` minus that module's own stem, so a
   module is never offered an import of itself) and run
   `built[name] = resolve_imports(built[name], sibling_exports)`, skipping the call when the
   sibling view is empty (single-module builds stay byte-identical). Tag `# #EXT-035-REQ-3`.
   Do not touch any other stage (PLAN/ASSEMBLE/SCAN/ACCEPTANCE/REPAIR) or any acceptance
   oracle (`adt_oracle.py`, `system_suite.py`, `_minimum_acceptance`, `code_quality.py`).
2. `tests/test_ext035_sibling_import_repair.py` (offline, NO model): reproduce the exact
   MEASURED case — a `data_manager.py` exporting `DataManager` and a `command_processor.py`
   string `class CommandProcessor(DataManager):` with no import. Assert (a) the raw
   unrepaired module genuinely raises `NameError` on compile/exec (proves the repro is real);
   (b) `resolve_imports` injects `from data_manager import DataManager` and the fixed module
   then imports/execs cleanly; (c) a canned-llm `build_system(...)` run over the 3-module
   plan (`data_manager.py`/`command_processor.py`/`main.py`) produces
   `result["modules"]["command_processor.py"]` with the injected import, the assembled
   on-disk file matches, and it imports cleanly from `root`; (d) a module that already has
   the correct sibling import is left byte-unchanged (idempotent) through the full
   `build_system` path; (e) a name not exported by any sibling is not injected (no spurious
   import). Tag `# #EXT-035-REQ-3`.
3. Run `python -m pytest tests/test_ext035_sibling_import_repair.py tests/test_ext035*.py -q`
   and `tests/test_ext036_system_builder.py -q` (targeted files only — no broad `-k` sweep,
   per the standing Jetson model-swap caution); report exact counts.
4. Update the REQ-3 traceability ranges in `.jarify/EXT-035/index.json` to add the new
   `system_builder.py` range and the new test file, preserving the existing REQ-1/REQ-2/REQ-3
   entries. Do not touch sibling specs.

#### Implements
- [REQ-3] Deterministic import-resolver — fix the model's cross-module import-emission (multi-module build_system wiring)
