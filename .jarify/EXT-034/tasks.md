# Implementation Tasks

### [TASK-1] Implement harness/swebench.py (loader + solve-input + resolver + eval)

Core implementation of the SWE-bench-Lite offline adapter. Pure Python, no Docker,
no dataset download, no live Jetson.

#### Steps
1. Create `harness/swebench.py` with module docstring documenting the offline scaffold,
   honesty invariant, and deferred live-path protocol.
2. Add `_parse_test_list(value) -> list[str]` helper that defensively handles both
   Python-list and JSON-stringified-list forms of FAIL_TO_PASS / PASS_TO_PASS.
3. Wrap `load_instances` and `build_solve_input` in `# #EXT-034-REQ-1 Start/End` comments.
   - `load_instances(path, n=None) -> list[dict]`: open JSONL, json.loads each line,
     skip malformed (try/except JSONDecodeError), limit to n if set.
   - `build_solve_input(instance, *, repo_context="") -> dict`: return
     {problem_statement, repo, hint_files, context}. NEVER include `patch` or `test_patch`.
4. Wrap `_wilson95`, `score_resolved`, `swebench_eval`, `run_swebench_slice` in
   `# #EXT-034-REQ-2 Start/End` comments.
   - `_wilson95(k, n) -> tuple[float, float]`: copy the wilson() formula from
     commit_replay.py (same z=1.96, same clamping).
   - `score_resolved(instance, candidate_patch, *, apply_fn, test_fn) -> dict`:
     call apply_fn(base_commit=..., candidate_patch=..., test_patch=...), catch exceptions;
     call test_fn(all_tests) -> set[str] of PASSING ids; compute ftp_passed/ptp_passed;
     return {resolved, fail_to_pass_passed, pass_to_pass_passed, reason}.
   - `swebench_eval(instances, *, solve_fn, apply_fn, test_fn) -> dict`:
     loop + score + aggregate; return {n, resolved, resolved_rate, wilson95, per_instance}.
   - `run_swebench_slice(n=10)`: raise NotImplementedError with documented live-path protocol
     (Docker + qwen3-4b-thinking routing, honest ~low expected score).
5. Add `__main__` block that imports argparse, parses `--path` / `--n` / `--dry-run`,
   prints a deferred-live-run note (no Docker/Jetson calls at import time).
6. Verify `ast.parse` + `import harness.swebench` are clean (no import-time side effects).

#### Implements
- [REQ-1] Instance loader and inert solve-input (honesty: gold patch never in solve input)
- [REQ-2] Deterministic resolve check and deferred live-slice protocol

### [TASK-2] Implement tests/test_swebench.py (offline test suite)

Offline test suite for all four public functions in harness/swebench.py. Uses a tiny
fixture JSONL in tmp_path and mock apply_fn/test_fn. No Docker, no download, no Jetson.

#### Steps
1. Create `tests/test_swebench.py` with module docstring explaining offline-only constraint.
2. Define two fixture instance dicts (`_INSTANCE_A`, `_INSTANCE_B`) and a
   `_write_fixture_jsonl(path, instances, *, include_malformed=False)` helper.
3. Implement group (a) — `load_instances` tests:
   - `test_load_instances_basic`: 2-instance fixture -> 2 returned.
   - `test_load_instances_skips_malformed`: 3 lines (1 bad) -> 2 returned.
   - `test_load_instances_limit`: n=1 -> 1 returned.
   - `test_load_instances_required_fields`: all 8 SWE-bench fields present.
4. Implement group (b) — `build_solve_input` honesty tests:
   - `test_build_solve_input_includes_problem_statement`.
   - `test_build_solve_input_includes_repo`.
   - `test_build_solve_input_excludes_gold_patch`: assert gold patch string NOT in json.dumps(si).
   - `test_build_solve_input_excludes_patch_key`: assert "patch" not in si.
   - `test_build_solve_input_repo_context_injected`.
5. Implement group (c) — `score_resolved` logic tests:
   - `test_score_resolved_true_when_all_pass`.
   - `test_score_resolved_false_when_ftp_fails`.
   - `test_score_resolved_false_when_ptp_breaks`.
   - `test_score_resolved_both_must_pass`.
6. Implement group (d) — sole-arbiter tests:
   - `test_score_resolved_test_fn_is_sole_arbiter`: model "claims" success, test_fn -> empty set -> not resolved.
   - `test_score_resolved_apply_fn_is_called`: verify apply_fn receives (base_commit, candidate_patch, test_patch).
7. Implement group (e) — `swebench_eval` aggregation tests:
   - `test_swebench_eval_aggregates_resolved_rate`: 2-instance, 1 resolves -> rate=0.5.
   - `test_swebench_eval_all_resolved`: 1 instance, all pass -> rate=1.0.
   - `test_swebench_eval_none_resolved`: 2 instances, none resolve -> rate=0.0.
   - `test_swebench_eval_result_keys`: all required keys present.
8. Run `python -m pytest tests/test_swebench.py -q` and full suite `python -m pytest tests/ -q`
   to confirm green before committing.

#### Implements
- [REQ-1] Instance loader and inert solve-input (honesty: gold patch never in solve input)
- [REQ-2] Deterministic resolve check and deferred live-slice protocol
