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
