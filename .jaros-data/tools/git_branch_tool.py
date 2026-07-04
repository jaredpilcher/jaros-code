"""Effectful execution-plane tool ``git.branch`` (EXT-037 / REQ-4).

Creates, lists, or switches branches in a caller-supplied project-root repo.
``action`` selects the operation (default ``"list"``, read-only); ``"create"``
and ``"switch"`` require a ``name``, sanity-checked so it cannot be mistaken for
a CLI flag or contain shell-hostile characters -- this is a normal (non-history-
rewriting) git operation, so it is NOT behind the REQ-4 ``allow_unsafe`` gate
(see ``git_history_update_tool.py`` for the one gated operation).
"""

from __future__ import annotations

import os
import re
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
_ACTIONS = {"list", "create", "switch"}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class GitBranchTool:
    NAME = "git.branch"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("git.branch requires a non-empty 'root' string")
        if not os.path.isdir(root):
            return ValidationResult.reject(f"git.branch root does not exist: {root!r}")
        action = payload.get("action", "list")
        if action not in _ACTIONS:
            return ValidationResult.reject(f"git.branch 'action' must be one of {sorted(_ACTIONS)}")
        if action != "list":
            name = payload.get("name")
            if not isinstance(name, str) or not name or not _NAME_RE.match(name):
                return ValidationResult.reject(
                    "git.branch requires a valid non-empty 'name' for create/switch "
                    "(letters/digits/'.'/'_'/'-'/'/' only, no leading '-')")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        action = payload.get("action", "list")

        if action == "list":
            result = run_git(root, ["branch", "--list"])
            branches, current = [], None
            for line in result["stdout"].splitlines():
                line = line.strip()
                if not line:
                    continue
                is_current = line.startswith("* ")
                name = line[2:].strip() if is_current else line
                branches.append(name)
                if is_current:
                    current = name
            return {
                "tool": self.NAME, "root": root, "action": action,
                "branches": branches, "current": current, **result,
            }

        name = payload.get("name")
        if action == "create":
            result = run_git(root, ["branch", name])
            return {
                "tool": self.NAME, "root": root, "action": action, "name": name,
                "created": result["exitCode"] == 0, **result,
            }

        # action == "switch"
        create_if_missing = bool(payload.get("create_if_missing"))
        args = ["checkout", "-b", name] if create_if_missing else ["checkout", name]
        result = run_git(root, args)
        return {
            "tool": self.NAME, "root": root, "action": action, "name": name,
            "switched": result["exitCode"] == 0, **result,
        }
# #EXT-037-REQ-4 End
