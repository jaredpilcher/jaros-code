"""Read-only execution-plane tool ``git.status`` (EXT-037 / REQ-4).

Reports the working-tree status of a caller-supplied project-root repo. No host
effect (nothing is created/changed), so ``validate()`` only checks the shape of
the request; ``git status`` itself never mutates the repo.
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


def _parse_entries(porcelain_stdout: str) -> list:
    entries = []
    for line in porcelain_stdout.splitlines():
        if len(line) < 4:
            continue
        index_status, worktree_status = line[0], line[1]
        path = line[3:].strip().strip('"')
        entries.append({"path": path, "indexStatus": index_status, "worktreeStatus": worktree_status})
    return entries


class GitStatusTool:
    NAME = "git.status"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("git.status requires a non-empty 'root' string")
        if not os.path.isdir(root):
            return ValidationResult.reject(f"git.status root does not exist: {root!r}")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        result = run_git(root, ["status", "--porcelain", "--untracked-files=all"])
        entries = _parse_entries(result["stdout"]) if result["exitCode"] == 0 else []
        return {
            "tool": self.NAME,
            "root": root,
            "clean": result["exitCode"] == 0 and not entries,
            "entries": entries,
            **result,
        }
# #EXT-037-REQ-4 End
