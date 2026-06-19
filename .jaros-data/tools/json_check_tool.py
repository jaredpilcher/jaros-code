"""Read-only execution-plane tool ``json.check`` (EXT-001 / REQ-12).

Deterministically validates JSON for the config specialist, the analogue of py.check
for Python. Lets the loop catch a broken config edit before a test run and feed the
exact parse error back. Read-only -> replay-safe.
"""

from __future__ import annotations

import json
import os

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-12 Start


class JsonCheckTool:
    NAME = "json.check"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        if not payload.get("path") and "text" not in payload:
            return ValidationResult.reject("json.check requires a 'path' or 'text'")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload.get("path")
        if path:
            if not os.path.isfile(path):
                return {"tool": self.NAME, "path": path, "valid": False, "error": "not a file"}
            text = open(path, "r", encoding="utf-8", errors="replace").read()
        else:
            text = payload.get("text", "")
        try:
            json.loads(text)
            return {"tool": self.NAME, "path": path, "valid": True, "error": None}
        except ValueError as exc:
            return {"tool": self.NAME, "path": path, "valid": False, "error": str(exc)}
# #EXT-001-REQ-12 End
