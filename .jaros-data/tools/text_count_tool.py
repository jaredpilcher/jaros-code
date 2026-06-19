"""Read-only custom tool: ``text.count`` — line/word/char counts for a file.

Reads a text file and reports counts. Read-only: it opens the file for reading
only, with a size cap so the action stays inert and bounded. Requires ``path``.
"""

from __future__ import annotations

import os

from jaros.core.decision_gate import ValidationResult

_MAX_BYTES = 2_000_000  # 2 MB cap


class TextCountTool:
    NAME = "text.count"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path")
        if not isinstance(path, str) or not path:
            return ValidationResult.reject("text.count requires a 'path' string")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload["path"]
        size = os.path.getsize(path)
        if size > _MAX_BYTES:
            return {"tool": self.NAME, "path": path, "error": "file too large", "sizeBytes": size}
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        return {
            "tool": self.NAME,
            "path": path,
            "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
            "words": len(text.split()),
            "chars": len(text),
            "sizeBytes": size,
        }
