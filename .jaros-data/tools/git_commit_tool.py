"""Effectful execution-plane tool ``git.commit`` (EXT-037 / REQ-4).

Stages one or more paths (or the whole working tree when ``paths`` is omitted)
and commits them with a message, scoped to a caller-supplied project-root repo.

Guardrails, both enforced in ``validate()`` before any host effect:
  - every explicit ``path`` is root-jailed (EXT-037 / REQ-1's ``path_jail`` choke
    point) -- a path outside ``root`` is refused;
  - a deterministic secret/ignored-path scan (``_gitsecrets``) inspects what
    ``git status`` says WOULD actually be staged -- whether ``paths`` was given
    explicitly or the caller asked to stage everything -- and refuses the WHOLE
    commit if any candidate path matches a secret/credential or ignored/runtime
    pattern (``.env``, ``*.key``/``*.pem``, common credential files, ``.log``,
    ``__pycache__``, etc.), mirroring jaros-code's own commit discipline: never
    commit ``.env``, secrets, logs, or runtime state.

The secret scan runs a read-only ``git status --porcelain`` in ``validate()`` (no
staging happens there), so the guard is airtight before any file is ever added.
"""

from __future__ import annotations

import os
import sys

from jaros.core.decision_gate import ValidationResult

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _pathjail import path_escape_reason
except Exception:  # pragma: no cover - fail safe if helper missing
    def path_escape_reason(root, target):  # type: ignore
        return None

try:
    from _gitsecrets import secret_or_ignored_reason
except Exception:  # pragma: no cover - fail safe if helper missing
    def secret_or_ignored_reason(path):  # type: ignore
        return None

try:
    from _gittools import run_git
except Exception:  # pragma: no cover - fail safe if helper missing
    def run_git(cwd, args, timeout_s=30):  # type: ignore
        return {"command": ["git", *args], "exitCode": None, "stdout": "",
                "stderr": "git helper unavailable", "timedOut": False}

# #EXT-037-REQ-4 Start


def _parse_status_paths(porcelain_stdout: str) -> list:
    """Extract candidate file paths from ``git status --porcelain`` output,
    handling the rename ``"old -> new"`` form (keep only the new path)."""
    paths = []
    for line in porcelain_stdout.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest.strip().strip('"'))
    return paths


class GitCommitTool:
    NAME = "git.commit"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("git.commit requires a non-empty 'root' string")
        if not os.path.isdir(root):
            return ValidationResult.reject(f"git.commit root does not exist: {root!r}")
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            return ValidationResult.reject("git.commit requires a non-empty 'message' string")

        paths = payload.get("paths")
        if paths is not None:
            if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
                return ValidationResult.reject("git.commit 'paths' must be a list of non-empty strings")
            for p in paths:
                escape = path_escape_reason(root, p)
                if escape is not None:
                    return ValidationResult.reject(f"git.commit refused path outside root: {escape}")

        status_args = ["status", "--porcelain", "--untracked-files=all"]
        if paths:
            status_args = status_args + ["--"] + paths
        status = run_git(root, status_args)
        if status["exitCode"] != 0:
            return ValidationResult.reject(
                f"git.commit could not read repo status (is {root!r} a git repo?): "
                f"{(status['stderr'] or status['stdout']).strip()}")

        for candidate in _parse_status_paths(status["stdout"]):
            reason = secret_or_ignored_reason(candidate)
            if reason is not None:
                return ValidationResult.reject(
                    f"git.commit refused: staged path {candidate!r} looks like a secret/ignored "
                    f"path ({reason}) -- never committing .env/keys/credentials/logs/runtime state")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        message = payload.get("message")
        paths = payload.get("paths")

        add_args = ["add", "-A"]
        if paths:
            add_args = add_args + ["--"] + paths
        add_result = run_git(root, add_args)
        if add_result["exitCode"] != 0:
            return {
                "tool": self.NAME, "root": root, "message": message,
                "staged": [], "committed": False, "commitHash": None, "add": add_result,
            }

        staged = run_git(root, ["diff", "--cached", "--name-only"])
        staged_paths = [p for p in staged["stdout"].splitlines() if p.strip()]

        commit_result = run_git(root, ["commit", "-m", message])
        commit_hash = None
        if commit_result["exitCode"] == 0:
            rev = run_git(root, ["rev-parse", "HEAD"])
            if rev["exitCode"] == 0:
                commit_hash = rev["stdout"].strip()

        return {
            "tool": self.NAME,
            "root": root,
            "message": message,
            "staged": staged_paths,
            "committed": commit_result["exitCode"] == 0,
            "commitHash": commit_hash,
            "add": add_result,
            "commit": commit_result,
        }
# #EXT-037-REQ-4 End
