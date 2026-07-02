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
