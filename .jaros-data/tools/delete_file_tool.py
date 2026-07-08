"""Effectful execution-plane tool ``code.delete_file`` (EXT-037 / REQ-14).

Deletes a file if it exists. The gated counterpart to ``code.write_file`` (REQ-11) for
the leaf-repair "adopt" cleanup path in ``harness/system_builder.py``, which previously
always raw-unlinked stale module files regardless of whether a ``runtime`` was present --
bypassing the Jaros Decision gate + hash-chain every other product-surface host FS effect
goes through (Tenet 1). Mirrors ``write_file_tool.py``'s structure exactly.
"""

from __future__ import annotations

import os
import sys

from jaros.core.decision_gate import ValidationResult

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _pathjail import path_escape_reason  # root-jail gate (EXT-037 / REQ-1)
except Exception:  # pragma: no cover - fail safe if helper missing
    def path_escape_reason(root, target):  # type: ignore
        return None

# #EXT-037-REQ-14 Start


class DeleteFileTool:
    NAME = "code.delete_file"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        path = payload.get("path")
        if not isinstance(path, str) or not path:
            return ValidationResult.reject("code.delete_file requires a 'path' string")
        root = payload.get("root")
        if isinstance(root, str) and root:
            escape = path_escape_reason(root, path)
            if escape is not None:
                return ValidationResult.reject(
                    f"code.delete_file refused path outside root: {escape}")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload["path"]
        try:
            existed = os.path.isfile(path)
            if existed:
                os.remove(path)
        except OSError as exc:
            # Never raise out of the branch (Tenet 3: an honest failure, not a crash) --
            # a missing file is a silent no-op success, handled above; this only catches a
            # genuine OS-level failure (e.g. a permissions error) on an existing file.
            return {"tool": self.NAME, "path": path, "applied": False, "error": str(exc)}
        return {"tool": self.NAME, "path": path, "applied": True, "existed": existed}
# #EXT-037-REQ-14 End
