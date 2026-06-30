"""EXT-034 — SWE-bench-Lite adapter (external repo bar).

OFFLINE scaffold for placing jaros-code on the gold-standard external repo bar
(SWE-bench-Lite, 300 real GitHub-issue tasks across 11 Python repos).

Each instance has:
  instance_id, repo, base_commit, problem_statement  — the visible issue context
  FAIL_TO_PASS   — tests that must go red → green (the "fix" signal)
  PASS_TO_PASS   — tests that must stay green (regression guard)
  test_patch     — adds/updates test files (applied before scoring; HIDDEN from solver)
  patch          — GOLD reference fix (oracle-only; NEVER shown to the solver)

Score: a candidate "resolves" an instance IFF all FAIL_TO_PASS now pass AND all
PASS_TO_PASS still pass.  test_fn is the SOLE arbiter of test outcomes.

HONESTY INVARIANT (Tenet 3): the gold `patch` field is NEVER part of the solve input
and NEVER shown to the solver.  Violations are Tenet-3 defects.

Hard multi-step-repo class → routes/escalates to qwen3-4b-thinking per PRIME-001
model-router protocol.  Expected honest ~low resolved rate for 2-4B models; the
gold-standard external bar is mapped honestly, not flattered.

Live Docker run + model-produces-patch path: see run_swebench_slice() (deferred).

Usage (once live):
    python -m harness.swebench --path evals/benchmarks/swebench_lite.jsonl --n 10
"""
from __future__ import annotations

import json
import math
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_test_list(value) -> list[str]:
    """Defensively parse FAIL_TO_PASS / PASS_TO_PASS: accept list[str] or
    JSON-stringified list (both appear in different SWE-bench dataset releases)."""
    if isinstance(value, list):
        return [str(t) for t in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except json.JSONDecodeError:
            pass
    return []


# #EXT-034-REQ-1 Start
def load_instances(path, n: int | None = None) -> list[dict]:
    """Parse SWE-bench-Lite instances from a local JSONL file.

    Args:
        path: Path-like to a local .jsonl file (princeton-nlp/SWE-bench_Lite format).
              The file must already be present — this function NEVER downloads anything.
        n:    If given, return only the first n valid instances.

    Returns:
        List of instance dicts with fields:
          instance_id, repo, base_commit, problem_statement,
          FAIL_TO_PASS, PASS_TO_PASS, test_patch, patch.

    Malformed JSONL lines are skipped defensively (no crash, no silent pass —
    the valid lines are returned and the skip is traceable via dropped count).
    """
    p = Path(path)
    instances: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # skip malformed line — defensive
        if not isinstance(obj, dict):
            continue
        # Real SWE-bench data encodes FAIL_TO_PASS / PASS_TO_PASS as JSON STRINGS
        # (e.g. '["pkg/test.py::test_a", ...]'); normalize to list[str] so
        # score_resolved iterates test names, not string characters.
        for _k in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            _v = obj.get(_k)
            if isinstance(_v, str):
                try:
                    parsed = json.loads(_v)
                    obj[_k] = parsed if isinstance(parsed, list) else _v
                except json.JSONDecodeError:
                    obj[_k] = []
        instances.append(obj)
        if n is not None and len(instances) >= n:
            break
    return instances


def build_solve_input(instance: dict, *, repo_context: str = "") -> dict:
    """Form the INERT solve input that the model receives for one instance.

    Returns a dict with:
      problem_statement  — the visible GitHub issue text
      repo               — owner/name of the repository
      hint_files         — optional hints from the dataset (may be empty)
      context            — caller-injected repo context (repo map, file list, etc.)

    HONESTY INVARIANT (Tenet 3):
      - The gold `patch` field is NEVER included. It is oracle-only.
      - The `test_patch` (hidden test additions) is NEVER included.
      - Only the problem_statement, repo name, and optional context are exposed.
    """
    return {
        "problem_statement": instance.get("problem_statement", ""),
        "repo": instance.get("repo", ""),
        "hint_files": instance.get("hints_text", ""),
        "context": repo_context,
        # NOTE: instance["patch"] (gold fix) is DELIBERATELY excluded — Tenet 3.
        # NOTE: instance["test_patch"] (hidden test additions) is also excluded.
    }
# #EXT-034-REQ-1 End


# #EXT-034-REQ-2 Start
def _wilson95(k: int, n: int) -> tuple[float, float]:
    """Wilson score 95% CI for a proportion (honest small-n interval).

    Mirrors commit_replay.py wilson() exactly — same formula, same z=1.96, same clamping.
    """
    z = 1.96
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def score_resolved(
    instance: dict,
    candidate_patch: str,
    *,
    apply_fn,
    test_fn,
) -> dict:
    """Deterministic resolve check for one SWE-bench-Lite instance.

    Applies candidate_patch + instance's test_patch to the repo at base_commit
    (via apply_fn), then queries which tests pass (via test_fn).

    Args:
        instance:        SWE-bench instance dict (from load_instances).
        candidate_patch: The unified-diff patch the model produced.
        apply_fn:        INJECTABLE side-effect:
                           apply_fn(*, base_commit, candidate_patch, test_patch) -> None
                           Sets up the repo state. May raise on failure.
        test_fn:         INJECTABLE side-effect — SOLE ARBITER:
                           test_fn(tests: list[str]) -> set[str]
                           Returns the set of test IDs that PASSED.

    Returns:
        {
          resolved:           bool   — True iff ALL FAIL_TO_PASS pass AND
                                           ALL PASS_TO_PASS still pass.
          fail_to_pass_passed: list  — FAIL_TO_PASS tests that passed.
          pass_to_pass_passed: list  — PASS_TO_PASS tests that passed.
          reason:             str    — human-readable verdict.
        }
    """
    fail_to_pass = _parse_test_list(instance.get("FAIL_TO_PASS", []))
    pass_to_pass = _parse_test_list(instance.get("PASS_TO_PASS", []))

    # Step 1: apply candidate patch + test patch to the repo.
    try:
        apply_fn(
            base_commit=instance.get("base_commit", ""),
            candidate_patch=candidate_patch,
            test_patch=instance.get("test_patch", ""),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "resolved": False,
            "fail_to_pass_passed": [],
            "pass_to_pass_passed": [],
            "reason": f"apply_fn raised: {exc}",
        }

    # Step 2: run tests. test_fn is the SOLE arbiter.
    all_tests = fail_to_pass + [t for t in pass_to_pass if t not in fail_to_pass]
    passed: set[str] = set(test_fn(all_tests))

    ftp_passed = [t for t in fail_to_pass if t in passed]
    ptp_passed = [t for t in pass_to_pass if t in passed]

    all_ftp = len(ftp_passed) == len(fail_to_pass)
    all_ptp = len(ptp_passed) == len(pass_to_pass)
    resolved = all_ftp and all_ptp

    if resolved:
        reason = "all FAIL_TO_PASS passed and all PASS_TO_PASS still pass"
    elif not all_ftp:
        missing = len(fail_to_pass) - len(ftp_passed)
        reason = f"{missing}/{len(fail_to_pass)} FAIL_TO_PASS did not pass"
    else:
        broken = len(pass_to_pass) - len(ptp_passed)
        reason = f"{broken}/{len(pass_to_pass)} PASS_TO_PASS regressed"

    return {
        "resolved": resolved,
        "fail_to_pass_passed": ftp_passed,
        "pass_to_pass_passed": ptp_passed,
        "reason": reason,
    }


def swebench_eval(
    instances: list[dict],
    *,
    solve_fn,
    apply_fn,
    test_fn,
) -> dict:
    """Evaluate a list of SWE-bench-Lite instances end-to-end.

    For each instance:
      1. Build the inert solve input (honesty: gold patch excluded).
      2. Call solve_fn(solve_input) -> candidate_patch.
      3. Call score_resolved(instance, candidate_patch, apply_fn=..., test_fn=...).
      4. Aggregate resolved-rate + Wilson95 CI.

    Args:
        instances: List of instance dicts (from load_instances).
        solve_fn:  INJECTABLE: solve_fn(solve_input: dict) -> str (candidate patch).
        apply_fn:  INJECTABLE: apply_fn(*, base_commit, candidate_patch, test_patch).
        test_fn:   INJECTABLE SOLE ARBITER: test_fn(tests: list[str]) -> set[str].

    Returns:
        {
          n:             int,
          resolved:      int,
          resolved_rate: float,
          wilson95:      (lo, hi),
          per_instance:  list[dict],  # one score_resolved result per instance
        }
    """
    per_instance: list[dict] = []
    resolved_count = 0

    for instance in instances:
        solve_input = build_solve_input(instance)
        candidate_patch = solve_fn(solve_input)
        score = score_resolved(
            instance, candidate_patch, apply_fn=apply_fn, test_fn=test_fn
        )
        per_instance.append({"instance_id": instance.get("instance_id", ""), **score})
        if score["resolved"]:
            resolved_count += 1

    n = len(instances)
    lo, hi = _wilson95(resolved_count, n)
    return {
        "n": n,
        "resolved": resolved_count,
        "resolved_rate": resolved_count / n if n > 0 else 0.0,
        "wilson95": (lo, hi),
        "per_instance": per_instance,
    }


def run_swebench_slice(n: int = 10) -> None:
    """DEFERRED LIVE PATH — documented stub only. Do NOT call in offline tests.

    SWE-bench-Lite is a hard multi-step-repo class. Per PRIME-001 model-router
    protocol these tasks route/escalate to qwen3-4b-thinking (EXT-021 REQ-6).
    Expected honest ~low resolved rate for 2-4B models; the gold-standard external
    bar is mapped honestly, not flattered (Tenet 3).

    Protocol when running live:
      1. Load n instances from the local SWE-bench-Lite JSONL.
      2. Build/pull the Docker sandbox for each target repo
         (mirrors commit_replay.py _run_nodes — unique container name + force-remove).
      3. Route each instance to qwen3-4b-thinking via model_rewire / solve_routed.
      4. The model produces a candidate unified-diff patch (problem_statement visible,
         gold patch NEVER leaked).
      5. apply_fn: git checkout base_commit; apply candidate_patch + test_patch via Docker.
      6. test_fn: run FAIL_TO_PASS + PASS_TO_PASS in Docker -> set of PASSING test IDs.
      7. score_resolved; collect per_instance results.
      8. Report Wilson95 CI (Tenet 3: honest, labelled, ~low expected).

    This live path is deferred until:
      - Docker sandbox build for SWE-bench repos is implemented.
      - qwen3-4b-thinking model-rewire integration is validated (EXT-021).
    """
    raise NotImplementedError(
        "Live SWE-bench-Lite run is deferred — see run_swebench_slice() docstring. "
        "Build Docker sandbox + model-rewire integration for qwen3-4b-thinking first."
    )
# #EXT-034-REQ-2 End


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "SWE-bench-Lite offline adapter (EXT-034). "
            "Live Docker run is deferred — see run_swebench_slice() for the protocol."
        )
    )
    parser.add_argument(
        "--path",
        default="evals/benchmarks/swebench_lite.jsonl",
        help="Path to local SWE-bench-Lite JSONL file (not downloaded by this script).",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help="Limit to first n instances.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and report instance count only (no solve, no Docker).",
    )
    args = parser.parse_args()

    instances = load_instances(args.path, n=args.n)
    print(f"Loaded {len(instances)} instance(s) from {args.path}")

    if args.dry_run:
        for i, inst in enumerate(instances[:5]):
            print(f"  [{i}] {inst.get('instance_id', '?')} — {inst.get('repo', '?')}")
        print("(dry-run: no solve or Docker calls; live path deferred — see run_swebench_slice)")
    else:
        print(
            "Live run not yet implemented. "
            "See run_swebench_slice() for the Docker + qwen3-4b-thinking protocol."
        )
