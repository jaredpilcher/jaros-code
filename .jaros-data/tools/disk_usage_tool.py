"""Read-only custom tool: ``fs.disk_usage`` — free/used bytes for a path.

Reports disk usage via ``shutil.disk_usage``. Read-only: it opens nothing for
writing and changes no state. ``path`` defaults to the current directory.
"""

from __future__ import annotations

import shutil

from jaros.core.decision_gate import ValidationResult


class DiskUsageTool:
    NAME = "fs.disk_usage"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path", ".")
        if not isinstance(path, str):
            return ValidationResult.reject("fs.disk_usage 'path' must be a string")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path", ".")
        total, used, free = shutil.disk_usage(path)
        return {
            "tool": self.NAME,
            "path": path,
            "totalBytes": total,
            "usedBytes": used,
            "freeBytes": free,
            "percentUsed": round(used / total * 100, 1) if total else 0.0,
        }
