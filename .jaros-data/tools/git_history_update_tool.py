"""Effectful execution-plane tool ``git.history_update`` (EXT-037 / REQ-4).

The ONE explicitly-gated history-mutating operation exposed by the toolbelt --
amending the last commit, hard-resetting the working tree/index to a ref, or
force-pushing a branch to a remote. NONE of these run by default: ``validate()``
REJECTS the decision unless the payload's ``allow_unsafe`` key is the literal
boolean ``True`` (mirroring ``shell_exec_tool.py``'s REQ-2 override -- any other
value, missing/``False``/a truthy string, leaves the gate fully in effect, never
default-on). This is the one seam where history-rewrite/force-push is possible at
all; every other git tool in this spec is append-only (init/commit/branch-create)
or read-only.
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
_ACTIONS = {"amend", "reset_hard", "force_push"}


class GitHistoryUpdateTool:
    NAME = "git.history_update"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("git.history_update requires a non-empty 'root' string")
        if not os.path.isdir(root):
            return ValidationResult.reject(f"git.history_update root does not exist: {root!r}")
        action = payload.get("action")
        if action not in _ACTIONS:
            return ValidationResult.reject(f"git.history_update 'action' must be one of {sorted(_ACTIONS)}")
        # Never default-on: only the literal boolean True opts a caller past this
        # gate, for THIS one decision -- no force-push / history-rewrite by default.
        if payload.get("allow_unsafe") is not True:
            return ValidationResult.reject(
                "git.history_update refused: history-rewrite/force-push requires an explicit "
                "'allow_unsafe: true' in this decision's payload (never default-on)")
        if action == "reset_hard":
            ref = payload.get("ref")
            if not isinstance(ref, str) or not ref:
                return ValidationResult.reject("git.history_update 'reset_hard' requires a non-empty 'ref'")
        if action == "amend":
            message = payload.get("message")
            if message is not None and not isinstance(message, str):
                return ValidationResult.reject("git.history_update 'amend' 'message' must be a string if given")
        if action == "force_push":
            remote = payload.get("remote")
            branch = payload.get("branch")
            if not isinstance(remote, str) or not remote:
                return ValidationResult.reject("git.history_update 'force_push' requires a non-empty 'remote'")
            if not isinstance(branch, str) or not branch:
                return ValidationResult.reject("git.history_update 'force_push' requires a non-empty 'branch'")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        action = payload.get("action")

        if action == "amend":
            message = payload.get("message")
            args = ["commit", "--amend"] + (["-m", message] if message else ["--no-edit"])
            result = run_git(root, args)
            return {
                "tool": self.NAME, "root": root, "action": action,
                "applied": result["exitCode"] == 0, **result,
            }

        if action == "reset_hard":
            ref = payload.get("ref")
            result = run_git(root, ["reset", "--hard", ref])
            return {
                "tool": self.NAME, "root": root, "action": action, "ref": ref,
                "applied": result["exitCode"] == 0, **result,
            }

        # action == "force_push"
        remote, branch = payload.get("remote"), payload.get("branch")
        result = run_git(root, ["push", "--force", remote, branch])
        return {
            "tool": self.NAME, "root": root, "action": action, "remote": remote,
            "branch": branch, "applied": result["exitCode"] == 0, **result,
        }
# #EXT-037-REQ-4 End
