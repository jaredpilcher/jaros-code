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
