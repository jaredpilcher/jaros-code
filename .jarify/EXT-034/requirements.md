---
id: EXT-034
title: SWE-bench-Lite adapter (external repo bar)
status: covered
priority: high
implementation:
  - file: harness/swebench.py
    ranges:
      - - 1
        - 160
  - file: tests/test_swebench.py
    ranges:
      - - 1
        - 220
  - file: harness/swebench_solve.py
    ranges:
      - - 1
        - 280
  - file: tests/test_swebench_solve.py
    ranges:
      - - 1
        - 280
---

### [REQ-1] Instance loader and inert solve-input (honesty: gold patch never in solve input)

Implement the OFFLINE scaffold for loading SWE-bench-Lite instances and forming an
inert solve input that a model can act on.

`load_instances(path, n=None) -> list[dict]` — parse SWE-bench-Lite instances from a
local JSONL file (princeton-nlp/SWE-bench_Lite format). Return dicts with the fields:
instance_id, repo, base_commit, problem_statement, FAIL_TO_PASS, PASS_TO_PASS,
test_patch, patch. Defensive: skip malformed lines. Do NOT download anything; the path
is caller-provided.

`build_solve_input(instance, *, repo_context="") -> dict` — form the INERT solve input
the model receives: {problem_statement, repo, hint_files, context}. ONLY the visible
issue + repo context.

HONESTY INVARIANT (Tenet 3): the gold `patch` field is NEVER part of the solve input
and NEVER shown to the solver. It is oracle-only. Violations are Tenet 3 defects.

#### Acceptance Criteria
- [x] `load_instances(path, n=None) -> list[dict]` implemented: parses JSONL, returns required fields.
- [x] Malformed JSONL lines are skipped defensively (no crash, no silent pass).
- [x] `n` parameter correctly limits to the first n instances.
- [x] `build_solve_input(instance, *, repo_context="") -> dict` implemented with correct shape.
- [x] Gold `patch` field is NEVER present in the dict returned by `build_solve_input`.
- [x] `test_patch` (hidden tests) is also excluded from the solve input.
- [x] Offline test (a): load_instances parses 2-instance fixture JSONL, skips a malformed line.
- [x] Offline test (b): build_solve_input includes problem_statement + repo; honesty assertion confirms gold patch absent.

### [REQ-2] Deterministic resolve check and deferred live-slice protocol

Implement the oracle that scores whether a candidate patch resolves an instance,
using INJECTABLE side-effects for full offline testability.

`score_resolved(instance, candidate_patch, *, apply_fn, test_fn) -> dict` — deterministic
resolve check: call apply_fn(base_commit, candidate_patch, test_patch), then call
test_fn(tests) to get the set of PASSING test IDs. Return:
  {resolved: bool, fail_to_pass_passed: list, pass_to_pass_passed: list, reason: str}.
`resolved` == ALL FAIL_TO_PASS tests pass AND ALL PASS_TO_PASS tests still pass.
`test_fn` is the SOLE arbiter of test outcomes.

`swebench_eval(instances, *, solve_fn, apply_fn, test_fn) -> dict` — outer eval loop:
for each instance, candidate = solve_fn(build_solve_input(instance)); score_resolved;
aggregate resolved-rate + Wilson95 CI. Returns:
  {n, resolved, resolved_rate, wilson95, per_instance}.

`run_swebench_slice(n)` — documented STUB for the deferred live path.

NOTE: SWE-bench-Lite is a hard multi-step-repo class. Per PRIME-001 model-router
protocol these tasks route/escalate to qwen3-4b-thinking. Expected honest ~low resolved
rate for 2-4B models; the bar is mapped honestly, not flattered (Tenet 3).

#### Acceptance Criteria
- [x] `score_resolved(..., *, apply_fn, test_fn) -> dict` implemented with correct shape.
- [x] `resolved=True` only when ALL FAIL_TO_PASS pass AND ALL PASS_TO_PASS pass.
- [x] `resolved=False` when any FAIL_TO_PASS test still fails.
- [x] `resolved=False` when any PASS_TO_PASS test regresses.
- [x] `test_fn` is sole arbiter: mock solve "claims" success but test_fn says fail -> resolved=False.
- [x] `apply_fn` exception returns resolved=False with error reason (no crash).
- [x] `swebench_eval(instances, *, solve_fn, apply_fn, test_fn) -> dict` loops + aggregates correctly.
- [x] Wilson95 CI mirrored from commit_replay.py wilson() — same formula.
- [x] `run_swebench_slice(n)` stub raises NotImplementedError, documents deferred live path.
- [x] `__main__` block (or `run_swebench_slice`) documents the live Docker + qwen3-4b-thinking route.
- [x] Offline test (c): score_resolved resolved=True/False cases for FAIL_TO_PASS and PASS_TO_PASS.
- [x] Offline test (d): test_fn sole-arbiter case (patch "claims" success but test_fn returns fail).
- [x] Offline test (e): swebench_eval resolves-rate over 2-instance fixture.

### [REQ-3] Patch-solve adapter: solve_input -> candidate unified-diff patch

Given an inert solve_input (produced by build_solve_input — gold patch NEVER leaked), produce
a candidate unified-diff patch that score_resolved can score.

DESIGN: A 2-4B model cannot reliably emit raw unified-diff syntax. The robust approach:
  1. LOCATE the target file(s) — deterministic (navigate / multi_file / hints).
  2. READ the original source — deterministic file I/O.
  3. Model produces the EDITED file body — single model call.
  4. DETERMINISTICALLY form the unified diff via difflib (original vs edited).

All callables (locate_fn, read_fn, gen_fn) are INJECTABLE for offline testability.
The live path (_make_live_fns) is a documented factory stub (deferred).

`make_unified_diff(path, original, edited) -> str` — deterministic: produce a valid
git-style unified diff (--- a/path / +++ b/path / @@ hunks) via difflib.unified_diff.
Returns "" if original == edited. Must round-trip: applying the diff to original yields edited.

`solve_swebench_instance(instance, *, locate_fn, read_fn, gen_fn) -> str` — candidate-patch
producer with injectable callables:
  - locate_fn(solve_input) -> list[str]: which file(s) the issue touches.
  - read_fn(path) -> str: original source.
  - gen_fn(solve_input, path, original) -> str: model's fix (edited source).
Calls make_unified_diff for each file; concatenates into one multi-file patch.
NEVER sees the gold patch (build_solve_input guarantees this; asserted defensively).

`_make_live_fns(registry, repo_dir) -> dict` — factory for the LIVE path (deferred):
locate_fn via navigate/multi_file, read_fn reads the repo file, gen_fn = routed solve
(qwen3-4b-thinking for hard-multi-step-repo class). Documented; not run in offline tests.

`swebench_eval_with_solve(instances, *, locate_fn, read_fn, gen_fn, apply_fn, test_fn) -> dict`
— convenience wrapper composing solve_swebench_instance -> score_resolved -> aggregate.
Returns the same shape as swebench_eval: {n, resolved, resolved_rate, wilson95, per_instance}.

#### Acceptance Criteria
- [x] `make_unified_diff(path, original, edited) -> str` implemented; returns "" for no-op.
- [x] make_unified_diff round-trips: applying diff to original yields edited (difflib).
- [x] Diff header uses git-style "--- a/path" / "+++ b/path" prefixes.
- [x] `solve_swebench_instance(instance, *, locate_fn, read_fn, gen_fn) -> str` implemented.
- [x] locate_fn, read_fn, gen_fn are injectable (offline-testable via mocks).
- [x] solve_swebench_instance asserts gold patch not in solve_input (honesty invariant).
- [x] Multi-file: two located files -> two-file patch concatenated.
- [x] `_make_live_fns(registry, repo_dir) -> dict` documented stub (deferred, not called in tests).
- [x] `swebench_eval_with_solve(...)` convenience wrapper implemented; same result shape as swebench_eval.
- [x] Offline test (a): make_unified_diff round-trips (multiple cases: add, delete, from-empty).
- [x] Offline test (b): make_unified_diff("", x, x) == "" and ("", "", "") == "".
- [x] Offline test (c): solve_swebench_instance with mocks produces non-empty multi-file diff.
- [x] Offline test (d): gold patch sentinel absent from candidate (honesty — gen_fn never sees it).
- [x] Offline test (e): no-op gen (edited==original) -> empty patch -> score_resolved unresolved.
