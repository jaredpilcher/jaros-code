# Implementation Tasks — EXT-010 Real-world robustness

### [TASK-1] Fix multi-file candidate localization to root against the target dir (REQ-5)

`harness/multi_file.candidate_files` returns `[]` for a cross-file fault when the process cwd is
not the target repo dir (every isolated eval / SWE-bench / daily-driver run), because it seeds
its import-closure BFS with the bare relative `test_file` and reads it relative to the process
cwd. Fix the seed to resolve against `root`; add a regression test.

#### Steps
1. In `harness/multi_file.py::candidate_files`, change the BFS seed so the test file is read from
   the target `root`: seed `frontier` with `str(root / Path(test_file).name)` (instead of the
   bare `test_file`). Do NOT change `_module_to_file` (it already returns absolute paths that read
   fine) or the traceback step. Keep the test-file-name exclusion in `add()` intact (we still
   don't fix the test itself). Minimal, surgical change.
2. Add `tests/test_ext010_multifile_localize.py` (offline, no model): create the 3-file scenario
   (`geometry.py` with `area` bug, `shapes.py` importing+using it, `test_shapes.py` asserting the
   end value) in a temp dir; call `candidate_files(tmp, <a pytest assertion-failure output string>,
   "test_shapes.py")` while the PROCESS cwd is the repo (not tmp); assert the returned list
   contains both `shapes.py` and `geometry.py` (import closure found) and excludes `test_shapes.py`.
   Include a guard that the same call previously returned `[]` is now non-empty.
3. Run `python -m pytest tests/test_ext010_multifile_localize.py -q` (pass) and `python -m pytest -q`
   (no NEW failures; the pre-existing untracked `logs/` stray doctest is not ours).
4. Tag the fixed lines `# #EXT-010-REQ-5` and add the traceability entry to `.jarify/EXT-010/index.json`.

#### Implements
- [REQ-5] Multi-file fault localization must resolve candidates against the target root, not the process CWD
