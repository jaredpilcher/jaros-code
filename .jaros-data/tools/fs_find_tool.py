"""Read-only execution-plane tool ``fs.find`` (EXT-001 / REQ-10).

Finds files whose name matches a glob pattern under a root, so an agent can locate
the file it needs across a tree. Deterministically ordered. Read-only -> replay-safe.
"""

from __future__ import annotations

import fnmatch
import os

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-10 Start
_DEFAULT_MAX = 200
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".jaros-data"}


class FsFindTool:
    NAME = "fs.find"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        pattern = payload.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return ValidationResult.reject("fs.find requires a non-empty 'pattern' string")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        pattern = payload["pattern"]
        root = payload.get("path", ".")
        cap = int(payload.get("max_results", _DEFAULT_MAX))
        matches: list[str] = []
        truncated = False
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for name in sorted(filenames):
                if fnmatch.fnmatch(name, pattern):
                    matches.append(os.path.join(dirpath, name).replace("\\", "/"))
                    if len(matches) >= cap:
                        truncated = True
                        break
            if truncated:
                break
        matches.sort()
        return {"tool": self.NAME, "pattern": pattern, "matches": matches,
                "count": len(matches), "truncated": truncated}
# #EXT-001-REQ-10 End
