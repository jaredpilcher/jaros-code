# EXT-034 Design: SWE-bench-Lite Adapter

## Overview

SWE-bench-Lite (300 GitHub-issue tasks, 11 Python repos) is the gold-standard external
bar for repository-level coding. This adapter places jaros-code on that bar via a
pure-Python offline scaffold with injectable side-effects, mirroring the existing
`harness/commit_replay.py` Docker-oracle pattern.

The hard multi-step-repo class (all SWE-bench tasks) routes to qwen3-4b-thinking
(PRIME-001 model-router protocol). The live Docker run is deferred; this spec implements
the OFFLINE contract/scaffold only.

## Data Format (princeton-nlp/SWE-bench_Lite)

Each JSONL line is a dict with these fields:

```text
{
  "instance_id":        "django__django-12345",    # unique instance key
  "repo":               "django/django",            # GitHub repo (owner/name)
  "base_commit":        "abc123",                   # SHA the model checkouts to
  "problem_statement":  "Issue text ...",           # VISIBLE to the solver
  "FAIL_TO_PASS":       ["tests/test_X.py::test_Y"], # tests that must go red->green
  "PASS_TO_PASS":       ["tests/test_X.py::test_Z"], # tests that must stay green
  "test_patch":         "diff ...",                 # adds/updates the tests — HIDDEN from solver
  "patch":              "diff ...",                 # GOLD reference patch — NEVER shown to solver
}
```

HONESTY INVARIANT: `patch` (gold) is oracle-only. It must never appear in `build_solve_input`.
Violations are Tenet-3 defects.

## Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        harness/swebench.py                           │
│                                                                      │
│  load_instances(path, n)          parse JSONL, skip malformed        │
│         │                                                            │
│         ▼                                                            │
│  build_solve_input(instance)      problem_statement + repo + ctx     │
│    NEVER includes: patch, test_patch                                 │
│         │                                                            │
│         ▼                                                            │
│  solve_fn(solve_input) ──────────►  candidate_patch                  │
│    (injectable — offline: stub)                                      │
│         │                                                            │
│         ▼                                                            │
│  score_resolved(instance, candidate_patch,                           │
│                 apply_fn, test_fn)                                   │
│    apply_fn(base_commit, candidate_patch, test_patch)  (INJECTABLE)  │
│    test_fn(tests) -> set[str]  SOLE ARBITER              (INJECTABLE)│
│         │                                                            │
│         ▼                                                            │
│  {resolved, fail_to_pass_passed, pass_to_pass_passed, reason}        │
│         │                                                            │
│         ▼                                                            │
│  swebench_eval(instances, solve_fn, apply_fn, test_fn)               │
│  → {n, resolved, resolved_rate, wilson95, per_instance}              │
│                                                                      │
│  run_swebench_slice(n) — STUB (deferred live Docker+qwen3 path)      │
└──────────────────────────────────────────────────────────────────────┘
```

## Injectable Side-Effects Pattern

Both `apply_fn` and `test_fn` are injectable, mirroring `commit_replay.py`'s
`_run_nodes` / `_apply_func` pattern. This gives full offline testability:

```text
OFFLINE (tests):               LIVE (deferred):
  apply_fn = mock no-op          apply_fn = docker_apply(repo, ...)
  test_fn  = lambda -> set()     test_fn  = docker_run_tests(repo, ...)
```

## Score Resolve Logic

```text
score_resolved(instance, candidate_patch, *, apply_fn, test_fn):

1. apply_fn(base_commit, candidate_patch, test_patch)
   └─ on exception → resolved=False, reason=str(e)

2. passed = test_fn(fail_to_pass + pass_to_pass)   # set of PASSING test IDs

3. ftp_passed = [t for t in FAIL_TO_PASS if t in passed]
   ptp_passed = [t for t in PASS_TO_PASS if t in passed]

4. resolved = (len(ftp_passed) == len(FAIL_TO_PASS))
           AND (len(ptp_passed) == len(PASS_TO_PASS))
```

## Wilson95 CI

Mirrors `commit_replay.py wilson()` exactly (same formula, honest small-n interval).

## Deferred Live Path (`run_swebench_slice`)

SWE-bench-Lite tasks are hard multi-step-repo class (PRIME-001 routing):

```text
1. Pull SWE-bench-Lite JSONL slice (10-20 instances).
2. Build/pull Docker sandbox per repo (mirrors commit_replay.py _run_nodes).
3. Route each instance: model_router → qwen3-4b-thinking (hard-repo class).
4. qwen3-4b-thinking produces a candidate unified-diff patch.
5. Apply candidate + test_patch via Docker (apply_fn live).
6. Score with score_resolved; report Wilson95 CI (Tenet 3: honest ~low expected).
```

This is deferred until Docker sandbox + qwen3-4b-thinking integration are in place.
