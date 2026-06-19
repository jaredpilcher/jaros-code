"""Effectful execution-plane tool ``code.write_file`` (EXT-001 / REQ-6).

Overwrites a file with full new content. The reliable counterpart to the surgical
``code.apply_patch`` for the common case where a small model rewrites a whole small
file. Effectful; the Decision is recorded before the write (PRIME-001 Tenet 3).
"""

from __future__ import annotations

import os

from jaros.core.decision_gate import ValidationResult

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
