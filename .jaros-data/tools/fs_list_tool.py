"""Read-only execution-plane tool ``fs.list`` (EXT-001 / REQ-2).

Returns the sorted entries of a directory, each tagged dir/file with its size, so a
single-purpose agent can decide where to look next. Read-only -> replay-safe.
"""

from __future__ import annotations

import os

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-2 Start


class FsListTool:
    NAME = "fs.list"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path")
        if not isinstance(path, str) or not path:
            return ValidationResult.reject("fs.list requires a non-empty 'path' string")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload["path"]
        if not os.path.isdir(path):
            return {"tool": self.NAME, "path": path, "error": "not a directory"}
        entries = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            is_dir = os.path.isdir(full)
            try:
                size = 0 if is_dir else os.path.getsize(full)
            except OSError:
                size = 0
            entries.append({"name": name, "type": "dir" if is_dir else "file", "sizeBytes": size})
        return {"tool": self.NAME, "path": path, "entries": entries, "count": len(entries)}
# #EXT-001-REQ-2 End
