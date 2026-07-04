"""Read-only execution-plane tool ``env.python_detect`` (EXT-037 / REQ-3).

Reports the available Python interpreter(s) + version -- a read-only observation
the orchestrator uses to confirm a runnable Python exists before setting up a
project environment. No host effect (nothing is created/changed), so ``validate()``
always accepts; the only gated concern in REQ-3 (root-jail, global-install denial)
applies to the venv/install/pin tools below, which actually write to the host.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from jaros.core.decision_gate import ValidationResult

# #EXT-037-REQ-3 Start
_DEFAULT_CANDIDATES = [sys.executable, "python3", "python", "py"]
_PROBE_TIMEOUT_S = 10


def _probe_version(resolved: str) -> str | None:
    try:
        proc = subprocess.run([resolved, "--version"], capture_output=True, text=True,
                               timeout=_PROBE_TIMEOUT_S)
    except Exception:
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    return text or None


class PythonDetectTool:
    NAME = "env.python_detect"

    def validate(self, decision) -> ValidationResult:
        # Read-only detection: nothing to gate, no host effect to jail.
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            candidates = _DEFAULT_CANDIDATES

        seen_real: set[str] = set()
        found: list[dict] = []
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate:
                continue
            resolved = candidate if os.path.isabs(candidate) else shutil.which(candidate)
            if not resolved:
                continue
            real = os.path.realpath(resolved)
            if real in seen_real:
                continue
            seen_real.add(real)
            version = _probe_version(resolved)
            if version is None:
                continue
            found.append({"path": resolved, "version": version})

        return {
            "tool": self.NAME,
            "found": found,
            "primary": found[0] if found else None,
            "available": bool(found),
        }
# #EXT-037-REQ-3 End
