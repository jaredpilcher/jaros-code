"""Read-only execution-plane tool ``git.log`` (EXT-037 / REQ-4).

Reads commit history for a caller-supplied project-root repo. No host effect;
an empty/uninitialized repo (no commits yet) is an honest ``hasCommits: false``
result, not an error.
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
_FIELD_SEP = "\x1f"
_DEFAULT_MAX_COUNT = 20


def _parse_log(stdout: str) -> list:
    commits = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(_FIELD_SEP)
        if len(parts) < 4:
            continue
        commit_hash, author, date = parts[0], parts[1], parts[2]
        subject = _FIELD_SEP.join(parts[3:])
        commits.append({"hash": commit_hash, "author": author, "date": date, "subject": subject})
    return commits


class GitLogTool:
    NAME = "git.log"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("git.log requires a non-empty 'root' string")
        if not os.path.isdir(root):
            return ValidationResult.reject(f"git.log root does not exist: {root!r}")
        max_count = payload.get("max_count", _DEFAULT_MAX_COUNT)
        if not isinstance(max_count, int) or isinstance(max_count, bool) or max_count <= 0:
            return ValidationResult.reject("git.log 'max_count' must be a positive integer")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        max_count = payload.get("max_count", _DEFAULT_MAX_COUNT)
        fmt = _FIELD_SEP.join(["%H", "%an", "%ad", "%s"])
        result = run_git(root, ["log", f"-n{max_count}", f"--pretty=format:{fmt}", "--date=iso-strict"])
        commits = _parse_log(result["stdout"]) if result["exitCode"] == 0 else []
        return {
            "tool": self.NAME,
            "root": root,
            "commits": commits,
            "hasCommits": bool(commits),
            **result,
        }
# #EXT-037-REQ-4 End
