"""Read-only execution-plane tool ``fs.grep`` (EXT-001 / REQ-3).

Searches files under a root for a regular expression and returns matching
locations, deterministically ordered by (file, line). Read-only -> replay-safe.
"""

from __future__ import annotations

import os
import re

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-3 Start
_DEFAULT_MAX = 200
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".jaros-data"}
_MAX_FILE_BYTES = 1_000_000


class FsGrepTool:
    NAME = "fs.grep"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        pattern = payload.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return ValidationResult.reject("fs.grep requires a non-empty 'pattern' string")
        try:
            re.compile(pattern)
        except re.error as exc:
            return ValidationResult.reject(f"fs.grep pattern is not a valid regex: {exc}")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        pattern = payload["pattern"]
        root = payload.get("path", ".")
        suffix = payload.get("glob")  # optional simple extension filter, e.g. ".py"
        cap = int(payload.get("max_matches", _DEFAULT_MAX))
        rx = re.compile(pattern)

        matches: list[dict] = []
        truncated = False
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for name in sorted(filenames):
                if suffix and not name.endswith(suffix):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    if os.path.getsize(full) > _MAX_FILE_BYTES:
                        continue
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        for lineno, line in enumerate(fh, start=1):
                            if rx.search(line):
                                matches.append({
                                    "file": full.replace("\\", "/"),
                                    "line": lineno,
                                    "text": line.rstrip("\n")[:300],
                                })
                                if len(matches) >= cap:
                                    truncated = True
                                    break
                except OSError:
                    continue
                if truncated:
                    break
            if truncated:
                break
        matches.sort(key=lambda m: (m["file"], m["line"]))
        return {"tool": self.NAME, "pattern": pattern, "matches": matches,
                "count": len(matches), "truncated": truncated}
# #EXT-001-REQ-3 End
