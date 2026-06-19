"""Read-only custom tool: ``sys.info`` — host platform snapshot.

Reports platform, Python, and CPU info. Performs NO writes and mutates nothing —
a safe read-only Execution-Plane action. Drop into the shared ``tools/`` folder.
"""

from __future__ import annotations

import os
import platform

from jaros.core.decision_gate import ValidationResult


class SysInfoTool:
    NAME = "sys.info"

    def validate(self, decision) -> ValidationResult:
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        return {
            "tool": self.NAME,
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        }
