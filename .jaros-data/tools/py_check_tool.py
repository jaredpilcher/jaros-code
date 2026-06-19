"""Read-only execution-plane tool ``py.check`` (EXT-001 / REQ-8).

Deterministically validates Python syntax via ``compile``. A sharp verb the agents
and loop use to catch a broken edit before wasting a test run, and to feed the exact
SyntaxError back for correction. Read-only -> replay-safe.
"""

from __future__ import annotations

import os

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-8 Start


class PyCheckTool:
    NAME = "py.check"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        if not payload.get("path") and "code" not in payload:
            return ValidationResult.reject("py.check requires a 'path' or 'code'")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload.get("path")
        if path:
            if not os.path.isfile(path):
                return {"tool": self.NAME, "path": path, "valid": False, "error": "not a file"}
            src = open(path, "r", encoding="utf-8", errors="replace").read()
        else:
            src = payload.get("code", "")
        try:
            compile(src, str(path or "<code>"), "exec")
            return {"tool": self.NAME, "path": path, "valid": True, "error": None, "line": None}
        except SyntaxError as exc:
            return {"tool": self.NAME, "path": path, "valid": False,
                    "error": exc.msg, "line": exc.lineno}
# #EXT-001-REQ-8 End
