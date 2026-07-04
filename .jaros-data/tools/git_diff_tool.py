"""Read-only execution-plane tool ``git.diff`` (EXT-037 / REQ-4).

Reads a unified diff (working tree vs. index, or staged vs. HEAD) for a
caller-supplied project-root repo. No host effect; reads are not root-jailed
(mirrors ``_pathjail.py``'s "reads may range broadly" rule) -- only the optional
``paths`` filter is type-checked here.
"""

from __future__ import annotations

import os
import sys

from jaros.core.decision_gate import ValidationResult

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _gittools import run_git
except Exception:  # pragma: no cover - fail safe if helper missing
    def run_git(cwd, args, timeout_s=30):  # type: ignore
        return {"command": ["git", *args], "exitCode": None, "stdout": "",
                "stderr": "git helper unavailable", "timedOut": False}

# #EXT-037-REQ-4 Start


class GitDiffTool:
    NAME = "git.diff"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("git.diff requires a non-empty 'root' string")
        if not os.path.isdir(root):
            return ValidationResult.reject(f"git.diff root does not exist: {root!r}")
        paths = payload.get("paths")
        if paths is not None and (
            not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths)
        ):
            return ValidationResult.reject("git.diff 'paths' must be a list of non-empty strings")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        staged = bool(payload.get("staged"))
        paths = payload.get("paths")
        args = ["diff"] + (["--cached"] if staged else [])
        if paths:
            args = args + ["--"] + paths
        result = run_git(root, args)
        return {
            "tool": self.NAME,
            "root": root,
            "staged": staged,
            "diff": result["stdout"],
            "hasChanges": bool(result["stdout"].strip()),
            **result,
        }
# #EXT-037-REQ-4 End
