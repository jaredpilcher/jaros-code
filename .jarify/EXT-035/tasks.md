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
