"""Effectful execution-plane tool ``code.write_file`` (EXT-001 / REQ-6).

Overwrites a file with full new content. The reliable counterpart to the surgical
``code.apply_patch`` for the common case where a small model rewrites a whole small
file. Effectful; the Decision is recorded before the write (PRIME-001 Tenet 3).
"""

from __future__ import annotations

import os
import sys

from jaros.core.decision_gate import ValidationResult

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _codesafety import unsafe_reason  # generated-code safety gate (REQ-11)
except Exception:  # pragma: no cover - fail safe if helper missing
    def unsafe_reason(code):  # type: ignore
        return None

# #EXT-001-REQ-6 Start
_MAX_BYTES = 1_000_000


class WriteFileTool:
    NAME = "code.write_file"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path")
        content = payload.get("content")
        if not isinstance(path, str) or not path:
            return ValidationResult.reject("code.write_file requires a 'path' string")
        if not isinstance(content, str):
            return ValidationResult.reject("code.write_file requires a 'content' string")
        if len(content.encode("utf-8")) > _MAX_BYTES:
            return ValidationResult.reject("code.write_file content exceeds size cap")
        hit = unsafe_reason(content)
        if hit is not None:
            return ValidationResult.reject(
                f"code.write_file refused unsafe generated code (matched {hit!r}): "
                "no network/process/destructive-fs/dynamic-exec operations allowed")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload["path"]
        content = payload["content"]
        existed = os.path.isfile(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        return {"tool": self.NAME, "path": path, "applied": True, "created": not existed,
                "bytesAfter": len(content.encode("utf-8"))}
# #EXT-001-REQ-6 End
