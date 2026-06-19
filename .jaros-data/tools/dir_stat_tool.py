"""Read-only custom tool: ``fs.stat`` — directory inventory.

Lists the entries of a directory with sizes and types. Read-only: it only
``scandir``s — it creates, modifies, and deletes nothing. ``path`` defaults to
the current directory; results are capped to keep payloads inert and small.
"""

from __future__ import annotations

import os

from jaros.core.decision_gate import ValidationResult

_MAX_ENTRIES = 200


class DirStatTool:
    NAME = "fs.stat"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        if not isinstance(payload.get("path", "."), str):
            return ValidationResult.reject("fs.stat 'path' must be a string")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path", ".")
        entries = []
        count = 0
        for entry in sorted(os.scandir(path), key=lambda e: e.name):
            if count >= _MAX_ENTRIES:
                break
            try:
                st = entry.stat()
                entries.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "sizeBytes": st.st_size,
                })
                count += 1
            except OSError:
                continue
        return {"tool": self.NAME, "path": path, "count": len(entries), "entries": entries}
