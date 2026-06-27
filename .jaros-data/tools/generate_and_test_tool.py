"""Execution-plane tool ``code.generate_and_test`` (EXT-012 / REQ-12).

Pure selection tool: given N candidate implementations and their self-test
pass-counts (computed by the caller via the existing run_tests op), deterministically
SELECT and return the best candidate.

HONESTY NOTE: Selection is ONLY by the model's own self-tests (derived from the
visible spec/intent), NEVER by the hidden oracle. The hidden oracle is never
exposed to this tool or to the solve prompt. Any result improvement comes solely
from the model genuinely solving more on its own spec-derived tests.

Decision payload:
  candidates   (list[str], required)  — N candidate Python source strings.
  results      (list[int], required)  — parallel list of pass-counts per candidate
                                        (ints >= 0, computed by the caller via the
                                        run_tests op or equivalent).

Returns:
  {
    "tool":       "code.generate_and_test",
    "chosen":     <str>,   # the selected candidate source
    "index":      <int>,   # 0-based index in the candidates list
    "pass_count": <int>,   # pass-count of the selected candidate
  }

Selection rule (fully deterministic, no LLM call):
  1. The FIRST candidate whose pass_count equals the maximum possible (i.e. all
     self-tests pass) is chosen.
  2. If no candidate passes all self-tests, the candidate with the HIGHEST
     pass_count is chosen.  Ties are broken by the LOWEST index (stable).

This tool is BUILT but NOT YET wired into the default solve path.  It must be
measured on held-out commits (integrate-or-prune gate, EXT-012 REQ-7) before any
default use.
"""

from __future__ import annotations

from jaros.core.decision_gate import ValidationResult

# #EXT-012-REQ-12 Start

NAME = "code.generate_and_test"


class GenerateAndTestTool:
    NAME = "code.generate_and_test"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        candidates = payload.get("candidates")
        results = payload.get("results")

        if not isinstance(candidates, list) or len(candidates) == 0:
            return ValidationResult.reject(
                "code.generate_and_test requires a non-empty list 'candidates'"
            )
        for i, c in enumerate(candidates):
            if not isinstance(c, str):
                return ValidationResult.reject(
                    f"code.generate_and_test: candidates[{i}] is not a str"
                )
        if not isinstance(results, list) or len(results) != len(candidates):
            return ValidationResult.reject(
                "code.generate_and_test requires 'results' to be a list of ints "
                "with the same length as 'candidates'"
            )
        for i, r in enumerate(results):
            if not isinstance(r, int):
                return ValidationResult.reject(
                    f"code.generate_and_test: results[{i}] is not an int"
                )

        return ValidationResult.accept(decision)  # type: ignore[attr-defined]

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        candidates: list[str] = payload["candidates"]
        results: list[int] = payload["results"]

        # Determine the maximum possible pass count (total self-tests).
        # We infer it as max(results); if all are 0 we treat 0 as the cap.
        # The "all-pass" check uses == max_possible, so we must know the ceiling.
        # The caller is responsible for passing the correct counts; we treat the
        # maximum observed count as "all tests pass" ONLY when explicitly flagged
        # via the optional "total_tests" key.  Without it we use max(results).
        total_tests = payload.get("total_tests")
        if isinstance(total_tests, int) and total_tests > 0:
            max_possible = total_tests
        else:
            max_possible = max(results) if results else 0

        # Step 1: find the first candidate that passes all self-tests.
        chosen_index: int = -1
        for i, count in enumerate(results):
            if count == max_possible and max_possible > 0:
                chosen_index = i
                break

        # Step 2: if no all-pass found, pick the highest-pass-count (lowest index on tie).
        if chosen_index < 0:
            best_count = -1
            for i, count in enumerate(results):
                if count > best_count:
                    best_count = count
                    chosen_index = i

        # Safety: if still -1 (empty candidates caught by validate, but guard anyway)
        if chosen_index < 0:
            chosen_index = 0

        return {
            "tool": self.NAME,
            "chosen": candidates[chosen_index],
            "index": chosen_index,
            "pass_count": results[chosen_index],
        }

# #EXT-012-REQ-12 End
