"""Effectful execution-plane tool ``git.init`` (EXT-037 / REQ-4).

Initializes a git repository at a caller-supplied project root. Root-scoped: the
tool only ever operates AT ``root`` (it is the ``cwd`` for the ``git init``
process) and never touches anything outside it -- there is no separate path to
jail here since ``git init`` creates only the repo's own ``.git`` directory
inside ``root``.
"""

from __future__ import annotations

import os
import sys

from jaros.core.decision_gate import ValidationResult

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _gittools import has_git_repo, run_git
except Exception:  # pragma: no cover - fail safe if helper missing
    def has_git_repo(root):  # type: ignore
        return False

    def run_git(cwd, args, timeout_s=30):  # type: ignore
        return {"command": ["git", *args], "exitCode": None, "stdout": "",
                "stderr": "git helper unavailable", "timedOut": False}

# #EXT-037-REQ-4 Start


class GitInitTool:
    NAME = "git.init"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("git.init requires a non-empty 'root' string")
        if not os.path.isdir(root):
            return ValidationResult.reject(f"git.init root does not exist: {root!r}")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        already = has_git_repo(root) if isinstance(root, str) else False
        result = run_git(root, ["init"])
        return {
            "tool": self.NAME,
            "root": root,
            "alreadyInitialized": already,
            "initialized": result["exitCode"] == 0,
            **result,
        }
# #EXT-037-REQ-4 End
