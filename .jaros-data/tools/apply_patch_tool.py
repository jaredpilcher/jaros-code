"""Effectful execution-plane tool ``code.apply_patch`` (EXT-001 / REQ-4).

Applies a single exact ``old`` -> ``new`` string edit to a file: the small,
reliable edit format a 2B model can produce. ``old`` must occur exactly once. An
empty ``old`` with an absent path creates a new file. Effectful: the Decision is
recorded before the edit is applied (PRIME-001 Tenet 3).
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

# #EXT-001-REQ-4 Start


class ApplyPatchTool:
    NAME = "code.apply_patch"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path")
        if not isinstance(path, str) or not path:
            return ValidationResult.reject("code.apply_patch requires a 'path' string")
        if "old" not in payload or "new" not in payload:
            return ValidationResult.reject("code.apply_patch requires 'old' and 'new' strings")
        if not isinstance(payload.get("old"), str) or not isinstance(payload.get("new"), str):
            return ValidationResult.reject("'old' and 'new' must be strings")
        hit = unsafe_reason(payload.get("new", ""))
        if hit is not None:
            return ValidationResult.reject(
                f"code.apply_patch refused unsafe generated code (matched {hit!r}): "
                "no network/process/destructive-fs/dynamic-exec operations allowed")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload["path"]
        old = payload["old"]
        new = payload["new"]

        # New-file creation: empty `old` and the file does not yet exist.
        if old == "" and not os.path.exists(path):
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(new)
            return {"tool": self.NAME, "path": path, "applied": True, "created": True,
                    "bytesBefore": 0, "bytesAfter": len(new.encode("utf-8"))}

        if not os.path.isfile(path):
            raise RuntimeError(f"code.apply_patch: file not found: {path}")
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        before = len(content.encode("utf-8"))
        occurrences = content.count(old)
        if occurrences == 0:
            raise RuntimeError("code.apply_patch: 'old' text not found in file")
        if occurrences > 1:
            raise RuntimeError(f"code.apply_patch: 'old' text is not unique ({occurrences} matches)")
        updated = content.replace(old, new, 1)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(updated)
        return {"tool": self.NAME, "path": path, "applied": True, "created": False,
                "bytesBefore": before, "bytesAfter": len(updated.encode("utf-8"))}
# #EXT-001-REQ-4 End
