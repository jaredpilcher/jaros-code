"""EXT-034 REQ-3 — SWE-bench patch-solve adapter.

Given a SWE-bench-Lite instance's inert solve input (produced by
harness.swebench.build_solve_input — gold patch NEVER included), produce a
candidate unified-diff patch that harness.swebench.score_resolved can score.

Design principle (Tenet 1 / Tenet 2):
  A 2-4B model CANNOT reliably emit raw unified-diff syntax.  The robust approach:
    1. LOCATE the target file(s) — deterministic (navigate / multi_file helpers).
    2. READ the original source from the repo — deterministic file I/O.
    3. Have the model produce the EDITED file/function — model judgement.
    4. DETERMINISTICALLY form the unified diff (original vs edited) via difflib.
  Steps 1, 2, 4 are purely deterministic tools (Tenet 1 execution plane).
  Step 3 is the sole model call (Tenet 2: smallest possible model footprint).

All three callables (locate_fn, read_fn, gen_fn) are INJECTABLE so the full
adapter is OFFLINE-testable with mocks.  The live path (_make_live_fns) is a
documented factory stub; not called in offline tests.

HONESTY INVARIANT (Tenet 3):
  - build_solve_input guarantees gold `patch` is never in the solve input.
  - solve_swebench_instance asserts this invariant defensively.
  - The candidate patch is produced purely from the model's edited output and the
    deterministic diff — it never derives from the gold patch.
"""
from __future__ import annotations

import difflib
import re
from typing import Callable


# ---------------------------------------------------------------------------
# #EXT-034-REQ-3 Start
# ---------------------------------------------------------------------------


def make_unified_diff(path: str, original: str, edited: str) -> str:
    """Produce a valid git-style unified diff (--- a/path / +++ b/path / @@ hunks).

    Uses difflib.unified_diff for byte-identical reproducibility.  Returns ""
    if original == edited (no-op fix).

    Round-trip guarantee: applying the returned diff to `original` yields `edited`.
    The caller can verify with any standard `patch` tool or the _apply_unified_diff
    helper below.

    Args:
        path:     The file path as it should appear in the diff header (e.g.
                  "django/db/models/query.py").  A leading slash is stripped.
        original: The original file content (before the fix).
        edited:   The edited file content (after the fix).

    Returns:
        A unified-diff string in git format, or "" when original == edited.
    """
    if original == edited:
        return ""

    # Normalise path: strip any leading slash so diff headers are clean.
    clean_path = path.lstrip("/")

    # splitlines() WITHOUT keepends: lines carry no trailing "\n", so joining the
    # unified_diff output with "\n" yields exactly ONE newline per line. Using
    # keepends=True here doubled every content line ("\n".join over lines that
    # already end in "\n") -> "malformed patch" when git apply runs it.
    orig_lines = original.splitlines()
    edit_lines = edited.splitlines()

    diff_lines = list(
        difflib.unified_diff(
            orig_lines,
            edit_lines,
            fromfile=f"a/{clean_path}",
            tofile=f"b/{clean_path}",
            lineterm="",
        )
    )

    if not diff_lines:
        return ""

    return "\n".join(diff_lines) + "\n"


def solve_swebench_instance(
    instance: dict,
    *,
    locate_fn: Callable,
    read_fn: Callable,
    gen_fn: Callable,
) -> str:
    """Produce a candidate unified-diff patch for one SWE-bench-Lite instance.

    The candidate patch is a concatenation of per-file unified diffs covering
    every file that locate_fn identifies as a target.

    Args:
        instance:   SWE-bench-Lite instance dict (from load_instances).
        locate_fn:  INJECTABLE: locate_fn(solve_input: dict) -> list[str]
                    Returns the file paths the issue likely touches.  The paths
                    are passed as-is to read_fn.
        read_fn:    INJECTABLE: read_fn(path: str) -> str
                    Returns the original source of the file at path.  Must be
                    deterministic for the given base_commit state.
        gen_fn:     INJECTABLE: gen_fn(solve_input: dict, path: str, original: str) -> str
                    Returns the model's edited version of the file.  This is the
                    sole model call — everything else is deterministic.

    Returns:
        A multi-file unified-diff patch string (may be "" if no files change or
        locate_fn returns an empty list).

    HONESTY INVARIANT (Tenet 3):
        build_solve_input guarantees the gold `patch` field is NOT in solve_input.
        This function asserts that invariant defensively — a violation is a hard
        error, not a silent pass.
    """
    from harness.swebench import build_solve_input  # local import avoids circularity

    solve_input = build_solve_input(instance)

    # Defensive honesty assertion: the gold patch must never reach the model.
    assert "patch" not in solve_input, (
        f"HONESTY VIOLATION (Tenet 3): gold 'patch' key leaked into solve_input "
        f"for instance {instance.get('instance_id', '?')}. "
        "This is a defect in build_solve_input — fix it immediately."
    )

    target_files: list[str] = locate_fn(solve_input)

    patches: list[str] = []
    for path in target_files:
        original: str = read_fn(path)
        edited: str = gen_fn(solve_input, path, original)
        diff = make_unified_diff(path, original, edited)
        if diff:
            patches.append(diff)

    return "".join(patches)


def _make_live_fns(registry: dict, repo_dir: str) -> dict:
    """Factory for the LIVE solve path (deferred — documented, not run in tests).

    Returns a dict of {locate_fn, read_fn, gen_fn} for use with
    solve_swebench_instance in a live (Docker + qwen3-4b-thinking) context.

    DEFERRED until:
      - Docker sandbox is validated for the target SWE-bench repos.
      - qwen3-4b-thinking model-rewire integration (EXT-021) is in place.

    locate_fn
        Derives target file paths from the solve_input.  Priority:
          1. hint_files from the dataset (file paths the dataset provides, when
             non-empty).  These are the most reliable signal.
          2. harness.multi_file.candidate_files on the problem_statement text
             (Agentless-style: treat the issue body as a pseudo-traceback and pull
             any filenames mentioned).
          3. harness.navigate.find_usages on keywords extracted from the issue
             (fallback when hints and traceback are absent).

    read_fn
        Reads the file from repo_dir at the current state (post base_commit
        checkout performed by apply_fn / Docker setup before this runs).

    gen_fn
        Calls the routed solve via harness.solve_routed.solve_routed with
        model=qwen3-4b-thinking (hard-repo-repair class per PRIME-001 router).
        The model's output is an edited file body (not a raw diff — see module
        docstring for why).

    Args:
        registry:  The model registry dict (from harness.model_registry).
        repo_dir:  Absolute path to the checked-out repo directory.

    Returns:
        dict with keys 'locate_fn', 'read_fn', 'gen_fn'.  Each is a callable
        with the signature documented in solve_swebench_instance.
    """
    from pathlib import Path

    def locate_fn(solve_input: dict) -> list[str]:
        """Locate target files via hint_files -> multi_file -> navigate (live only)."""
        from harness.multi_file import candidate_files as _candidate_files

        hints = solve_input.get("hint_files", "") or ""
        # 1. Dataset hint_files: if the dataset provides explicit file hints, use them.
        if hints.strip():
            candidates = [
                h.strip()
                for h in re.split(r"[\n,;]", hints)
                if h.strip() and h.strip().endswith(".py")
            ]
            if candidates:
                return candidates

        # 2. Agentless-style: extract file paths mentioned in the problem statement.
        problem = solve_input.get("problem_statement", "")
        return _candidate_files(repo_dir, problem, "")  # treat problem as pseudo-output

    def read_fn(path: str) -> str:
        """Read file from repo_dir at current state (post base_commit checkout)."""
        return Path(path).read_text(encoding="utf-8")

    def gen_fn(solve_input: dict, path: str, original: str) -> str:
        """Generate the fixed file using the routed solve (qwen3-4b-thinking).

        DEFERRED: requires EXT-021 model-rewire integration to be validated.
        When implemented:
          - Build a task prompt from solve_input['problem_statement'] + original.
          - Call solve_routed(problem, registry=registry) -> result.
          - Extract the model's edited file text from result['solve']['code'].
          - Return it as the 'edited' string.
        """
        raise NotImplementedError(
            "Live gen_fn requires qwen3-4b-thinking model-rewire integration (EXT-021). "
            "Docker sandbox + model-rewire must be validated first before calling "
            "_make_live_fns. See run_swebench_slice() in harness/swebench.py for the "
            "deferred live-path protocol."
        )

    return {"locate_fn": locate_fn, "read_fn": read_fn, "gen_fn": gen_fn}


def swebench_eval_with_solve(
    instances: list[dict],
    *,
    locate_fn: Callable,
    read_fn: Callable,
    gen_fn: Callable,
    apply_fn: Callable,
    test_fn: Callable,
) -> dict:
    """Convenience wrapper: solve each instance then score it.

    Composes solve_swebench_instance -> score_resolved -> aggregate.
    Returns the same shape as swebench_eval:
      {n, resolved, resolved_rate, wilson95, per_instance}.

    All five callables are INJECTABLE so the full pipeline is offline-testable.

    Args:
        instances:  List of SWE-bench-Lite instance dicts (from load_instances).
        locate_fn:  INJECTABLE: locate_fn(solve_input) -> list[str].
        read_fn:    INJECTABLE: read_fn(path: str) -> str.
        gen_fn:     INJECTABLE: gen_fn(solve_input, path, original) -> str.
        apply_fn:   INJECTABLE: apply_fn(*, base_commit, candidate_patch, test_patch).
        test_fn:    INJECTABLE SOLE ARBITER: test_fn(tests: list[str]) -> set[str].

    Returns:
        {n, resolved, resolved_rate, wilson95, per_instance}
    """
    from harness.swebench import _wilson95, score_resolved

    per_instance: list[dict] = []
    resolved_count = 0

    for instance in instances:
        candidate_patch = solve_swebench_instance(
            instance, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
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


# ---------------------------------------------------------------------------
# #EXT-034-REQ-3 End
# ---------------------------------------------------------------------------


def _apply_unified_diff(original: str, diff_text: str) -> str:
    """Apply a unified diff produced by make_unified_diff back to `original`.

    Pure-Python implementation: parses the @@ hunk headers and + / - / context
    lines.  Intended for round-trip tests only — not a general-purpose patch tool.

    Returns the reconstructed edited string, or `original` if diff_text is empty.
    """
    if not diff_text:
        return original

    lines = original.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)

    result: list[str] = []
    orig_pos = 0  # 0-based cursor into `lines`

    i = 0
    # Skip file header lines (--- a/... and +++ b/...)
    while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
        i += 1

    while i < len(diff_lines):
        hdr = diff_lines[i]
        if not hdr.startswith("@@"):
            i += 1
            continue

        # Parse @@ -start[,count] +start[,count] @@
        m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", hdr)
        if not m:
            i += 1
            continue

        orig_start = int(m.group(1)) - 1  # convert to 0-based index
        i += 1

        # Copy unchanged lines preceding this hunk.
        while orig_pos < orig_start and orig_pos < len(lines):
            result.append(lines[orig_pos])
            orig_pos += 1

        # Process hunk lines until the next @@ or EOF.
        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            hunk_line = diff_lines[i]
            if hunk_line.startswith("+"):
                # Added line: include without the leading '+'.
                result.append(hunk_line[1:])
                i += 1
            elif hunk_line.startswith("-"):
                # Removed line: skip from original.
                orig_pos += 1
                i += 1
            elif hunk_line.startswith(" "):
                # Context line: include, advance both.
                result.append(hunk_line[1:])
                orig_pos += 1
                i += 1
            else:
                # Diff metadata (e.g. "\ No newline at end of file") — skip.
                i += 1

    # Append any remaining lines from the original.
    while orig_pos < len(lines):
        result.append(lines[orig_pos])
        orig_pos += 1

    return "".join(result)
