"""Shared git-CLI helper for the git tools (EXT-037 / REQ-4).

Every git tool below shells out to the system ``git`` binary via ``run_git``, a
single choke point that applies a timeout and NEVER raises -- a missing binary, a
bad ``cwd``, or a command that exceeds the timeout all come back as a structured,
honest result dict instead of an uncaught exception, mirroring
``shell_exec_tool.py``'s (EXT-037 / REQ-2) never-raise contract for the same class
of effect (an external process). Git subcommands are short-lived and do not spawn
long-running descendants the way an arbitrary shell command can, so a plain
``subprocess.run(..., timeout=...)`` (which already kills the immediate process on
timeout) is sufficient here; this is an honest, narrower guarantee than
``shell_exec``'s process-TREE kill, not a silent gap.

Underscore-prefixed so the Jaros custom-tool loader (``load_custom_tools``) skips
it as a tool module, mirroring ``_pathjail.py`` / ``_envtools.py`` / ``_codesafety.py``.
"""

from __future__ import annotations

import os
import subprocess

# #EXT-037-REQ-4 Start
_DEFAULT_TIMEOUT_S = 30


def has_git_repo(root: str) -> bool:
    """True if ``root`` already looks like the top of a git working tree (a
    ``.git`` entry present -- a directory for a normal repo, a file for a
    worktree/submodule gitlink)."""
    return isinstance(root, str) and bool(root) and os.path.exists(os.path.join(root, ".git"))


def run_git(cwd: str, args: list, timeout_s: int = _DEFAULT_TIMEOUT_S) -> dict:
    """Run ``git <args>`` in ``cwd``. NEVER raises -- returns a structured result
    dict (``command``, ``exitCode``, ``stdout``, ``stderr``, ``timedOut``, and an
    ``error`` key on an unexpected failure such as a missing ``cwd``) instead of
    letting an exception escape to the caller (PRIME-001 Tenet 3)."""
    command = ["git", *args]
    try:
        proc = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=timeout_s,
        )
        return {
            "command": command,
            "exitCode": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "timedOut": False,
        }
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "command": command,
            "exitCode": None,
            "stdout": out or "",
            "stderr": err or "",
            "timedOut": True,
        }
    except Exception as exc:  # pragma: no cover-defensive - bad cwd / missing git binary
        return {
            "command": command,
            "exitCode": None,
            "stdout": "",
            "stderr": str(exc),
            "timedOut": False,
            "error": str(exc),
        }
# #EXT-037-REQ-4 End
