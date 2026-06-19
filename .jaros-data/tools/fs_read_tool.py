"""Read-only execution-plane tool ``fs.read`` (EXT-001 / REQ-1).

Reads a UTF-8 text file and returns its contents plus line/byte counts, bounded by
a byte cap so the action stays inert. Read-only -> replay-safe.
"""

from __future__ import annotations

import os

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-1 Start
_MAX_BYTES = 1_000_000  # 1 MB read cap keeps a single decision bounded


class FsReadTool:
    NAME = "fs.read"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path")
        if not isinstance(path, str) or not path:
            return ValidationResult.reject("fs.read requires a non-empty 'path' string")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload["path"]
        cap = int(payload.get("max_bytes", _MAX_BYTES))
        if not os.path.isfile(path):
            return {"tool": self.NAME, "path": path, "error": "not a file"}
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read(cap)
        truncated = size > cap
        return {
            "tool": self.NAME,
            "path": path,
            "content": data,
            "lines": data.count("\n") + (1 if data and not data.endswith("\n") else 0),
            "bytes": size,
            "truncated": truncated,
        }
# #EXT-001-REQ-1 End
