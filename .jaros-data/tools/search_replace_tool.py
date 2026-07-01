"""Effectful execution-plane tool ``code.search_replace`` (EXT-001 / REQ-13).

Applies a ``search`` -> ``replace`` block edit to a file using the RESILIENT match
strategy proven in the SWE-bench-Lite slice (exact match, then rstrip-tolerant
match, then a difflib line-level fallback) -- the resilient counterpart to
``code.apply_patch``'s brittle exact-unique match. To keep a SINGLE source of truth
(PRIME-001 Tenet 3 -- no divergent copy of the matching logic), this tool DELEGATES
the matching to the already-tested ``harness.swebench_live.apply_search_replace``;
it does not re-implement it. Effectful: the Decision is recorded before the edit is
applied (Tenet 3).
"""

from __future__ import annotations

import os
import sys

from jaros.core.decision_gate import ValidationResult

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _codesafety import unsafe_reason  # generated-code safety gate (REQ-11)
except Exception:  # pragma: no cover
    def unsafe_reason(code):  # type: ignore
        return None

# Add the repo root to sys.path so `harness.swebench_live` imports cleanly
# (mirrors `.jaros-data/agents/locate_agent.py`).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from harness.swebench_live import apply_search_replace  # noqa: E402

# #EXT-001-REQ-13 Start


def _classify_tier(original: str, search: str) -> str:
    """Deterministic, read-only classification of WHICH tier matched -- for the
    ``matchedBy`` report field only. The actual match/replace is fully delegated to
    ``apply_search_replace`` above; this never performs or influences the edit."""
    if search in original:
        return "exact"
    norm = lambda s: "\n".join(x.rstrip() for x in s.split("\n"))
    if norm(search) in norm(original):
        return "rstrip"
    return "difflib"


class SearchReplaceTool:
    NAME = "code.search_replace"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path")
        if not isinstance(path, str) or not path:
            return ValidationResult.reject("code.search_replace requires a 'path' string")
        if "search" not in payload or "replace" not in payload:
            return ValidationResult.reject("code.search_replace requires 'search' and 'replace' strings")
        if not isinstance(payload.get("search"), str) or not isinstance(payload.get("replace"), str):
            return ValidationResult.reject("'search' and 'replace' must be strings")
        hit = unsafe_reason(payload.get("replace", ""))
        if hit is not None:
            return ValidationResult.reject(
                f"code.search_replace refused unsafe generated code (matched {hit!r}): "
                "no network/process/destructive-fs/dynamic-exec operations allowed")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload["path"]
        search = payload["search"]
        replace = payload["replace"]

        if not os.path.isfile(path):
            raise RuntimeError(f"code.search_replace: file not found: {path}")
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        before = len(content.encode("utf-8"))

        new = apply_search_replace(content, search, replace)
        if new is None:
            raise RuntimeError("code.search_replace: no search/replace tier matched")

        matched_by = _classify_tier(content, search)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        return {"tool": self.NAME, "path": path, "applied": True, "created": False,
                "bytesBefore": before, "bytesAfter": len(new.encode("utf-8")),
                "matchedBy": matched_by}
# #EXT-001-REQ-13 End
