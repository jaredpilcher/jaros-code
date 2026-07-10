# Implementation Tasks

### [TASK-1] Suite scaffold + CSV→JSON ETL task wired to fs_oracle (REQ-1, REQ-2)

#### Steps
1. Create `harness/real_systems_suite.py` with a `RealSystemTask` dataclass (name, cls, sentence,
   oracle_kind, oracle_spec) and `run_real_systems_suite(tasks, llm)` that builds each via `build_system`,
   asserts the leaf path is OFF for the spec (no `leaf_for_spec` fingerprint), grades by the task's oracle,
   returns per-class pass@1.
2. Add the CSV→JSON group-by ETL `RealSystemTask` (contract-exact sentence) and wire its grading to
   `harness/fs_oracle.py` (seed a CSV tree, run the built entrypoint, byte-compare the output JSON file)
   plus an exact-stdout check variant where useful.
3. Add `tests/test_ext060_real_systems_suite.py` (OFFLINE, no Jetson): prove the fs_oracle grading catches
   a WRONG built stub (wrong grouping) and passes a CORRECT stub, and that the leaves-OFF assertion holds.
4. Update `.jarify/EXT-060/index.json` (REQ-1/REQ-2 ranges); flip `status` toward `partial`.

#### Implements
- [REQ-1] Suite scaffold + leaves-OFF pass@1 runner
- [REQ-2] CSV→JSON group-by ETL task graded by fs_oracle

### [TASK-2] Retry/backoff library task wired to import_driver (REQ-3)

#### Steps
1. In `harness/real_systems_suite.py`, add a `RETRY_BACKOFF_LIB_TASK` `RealSystemTask` (oracle_kind
   'import') with a contract-exact sentence for a single-file `retry.py` exporting `retry(times,
   exceptions=Exception)`; add `'import'` dispatch in `grade_real_system_task`/`_grade_*` that wires
   `harness/import_driver.py` (`drive_import`): import the built module, apply the decorator to a
   fail-then-succeed callable with an injected sleep, assert retry-count + eventual success + no real sleep.
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks) + leak-free.
3. Extend `tests/test_ext060_real_systems_suite.py` (OFFLINE, no Jetson): hand-authored CORRECT retry.py
   stub passes the import_driver grading; a WRONG one (wrong count / gives up early) fails; leaves-OFF holds.
4. Run `python -m pytest tests/test_ext060_real_systems_suite.py tests/test_ext059_import_driver.py -q`;
   confirm green. Update `.jarify/EXT-060/index.json` (REQ-3 ranges) + check REQ-3 boxes.

#### Implements
- [REQ-3] Retry/backoff decorator library task graded by import_driver

### [TASK-3] INI-section config-query CLI task wired to the existing cli-exact oracle (REQ-4)

#### Steps
1. In `harness/real_systems_suite.py`, add `INI_SECTION_QUERY_TASK` (a `RealSystemTask`, `oracle_kind
   ="cli-exact"`) with a contract-exact sentence for a single-file `main.py` that reads an INI-format
   config file from standard input and takes exactly two command-line arguments (a section name, then
   a key name), prints the value of that key inside that section followed by a single trailing
   newline and nothing else, or prints nothing and exits nonzero if the section or key is absent.
   Wire it via the EXISTING cli-exact grading path (`_grade_cli_exact` / `_run_check_variant`'s
   `exact_stdout` check) -- no new oracle code.
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks as the other tasks --
   static `leaf_for_spec` + post-build `build_path` check) + leak-free (the oracle-chosen argv/stdin/
   expected_stdout values are all derivable from the visible sentence contract).
3. Add `tests/test_ext060_ini_query.py` (OFFLINE, no Jetson): a hand-authored CORRECT `main.py` stub
   passes the cli-exact grading; a WRONG one (wrong value or extra output) fails.
4. Run `python -m pytest tests/test_ext060_ini_query.py tests/test_ext060*.py -q`; confirm green.
   Update `.jarify/EXT-060/index.json` (REQ-4 ranges) + check REQ-4 boxes in requirements.md.

#### Implements
- [REQ-4] INI-section config-query CLI task graded by the existing cli-exact oracle

### [TASK-4] Memoize/cache decorator library task wired to the existing import_driver oracle (REQ-5)

#### Steps
1. In `harness/real_systems_suite.py`, add `MEMOIZE_LIB_TASK` (a `RealSystemTask`, `oracle_kind
   ="import"`) with a contract-exact sentence for a single-file `memoize.py` module exporting
   exactly one public function `memoize(maxsize=128)` that returns a decorator; the decorated
   callable caches its return value keyed by the tuple of positional arguments it is called with
   (a repeated call with the SAME arguments returns the cached value without re-invoking the
   wrapped callable; a call with NEW arguments does invoke it). Wire it via the ALREADY-LANDED
   `"import"` oracle dispatch (`_grade_import` -> `harness/import_driver.py`'s `drive_import`) --
   no new oracle code. The oracle's `api_calls` chain calls `memoize()` with NO arguments (relying
   entirely on the `maxsize=128` default) to also exercise the EXT-036 REQ-45 signature-contract-
   default repair on this second library class.
2. Add it to `REAL_SYSTEMS_TASKS` (append after the existing INI task, outside any existing
   REQ-tagged block). Keep leaves-OFF enforced (same two checks as the other tasks -- static
   `leaf_for_spec` + post-build `build_path` check) + leak-free (every oracle-chosen value is
   derivable from the visible sentence contract).
3. Add `tests/test_ext060_memoize.py` (OFFLINE, no Jetson/model): a hand-authored CORRECT
   `memoize.py` stub passes the import_driver grading; a WRONG stub (never caches -- always calls
   through) is caught; leaves-OFF holds (`leaf_for_spec` returns `None` for the sentence); the
   task is a member of `REAL_SYSTEMS_TASKS`.
4. Run `python -m pytest tests/test_ext060_memoize.py tests/test_ext060*.py -q`; confirm green.
   Update `.jarify/EXT-060/index.json` (REQ-5 ranges) + check REQ-5 boxes in requirements.md.

#### Implements
- [REQ-5] Memoize/cache decorator library task graded by the existing import_driver oracle
