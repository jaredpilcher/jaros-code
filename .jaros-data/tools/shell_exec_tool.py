"""Effectful execution-plane tool ``shell.exec`` (EXT-001 / REQ-5).

Runs a command with a timeout and captures stdout, stderr, and the exit code: the
primitive single-purpose agents use to run builds and tests. Effectful and not
purely deterministic; the Decision is recorded before the command runs so the run
stays attributable (PRIME-001 Tenet 3). Output is bounded/truncated.
"""

from __future__ import annotations

import subprocess

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-5 Start
_DEFAULT_TIMEOUT_S = 120
_MAX_OUTPUT = 100_000  # cap captured stdout/stderr so a decision stays bounded


def _truncate(text: str) -> str:
    if len(text) > _MAX_OUTPUT:
        return text[:_MAX_OUTPUT] + f"\n...[truncated {len(text) - _MAX_OUTPUT} chars]"
    return text


class ShellExecTool:
    NAME = "shell.exec"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        command = payload.get("command")
        if not command or not isinstance(command, (str, list)):
            return ValidationResult.reject("shell.exec requires a non-empty 'command' (str or list)")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        command = payload["command"]
        cwd = payload.get("cwd") or None
        timeout = int(payload.get("timeout_s", _DEFAULT_TIMEOUT_S))
        use_shell = isinstance(command, str)
        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                shell=use_shell,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "tool": self.NAME,
                "command": command,
                "exitCode": proc.returncode,
                "stdout": _truncate(proc.stdout or ""),
                "stderr": _truncate(proc.stderr or ""),
                "timedOut": False,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "tool": self.NAME,
                "command": command,
                "exitCode": None,
                "stdout": _truncate(exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")),
                "stderr": _truncate(exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")),
                "timedOut": True,
            }
# #EXT-001-REQ-5 End
