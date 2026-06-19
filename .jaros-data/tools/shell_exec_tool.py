"""Effectful execution-plane tool ``shell.exec`` (EXT-001 / REQ-5).

Runs a command with a timeout and captures stdout, stderr, and the exit code: the
primitive single-purpose agents use to run builds and tests. Effectful and not
purely deterministic; the Decision is recorded before the command runs so the run
stays attributable (PRIME-001 Tenet 3). Output is bounded/truncated.
"""

from __future__ import annotations

import re
import subprocess

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-5 Start
_DEFAULT_TIMEOUT_S = 120
_MAX_OUTPUT = 100_000  # cap captured stdout/stderr so a decision stays bounded

# Safety denylist (EXT-001 / REQ-7): deterministic gate that REFUSES dangerous
# commands so the harness is safe to run unattended. Two non-negotiable classes:
#   1. no internet WRITES / network egress (no exfiltration, no remote pushes)
#   2. no destructive or privilege-escalating host operations
# Refused at the gate -> the command never executes (PRIME-001 two-plane safety).
_DENY_PATTERNS = [
    # --- network / internet (no egress, no writes to the internet) ---
    r"\bcurl\b", r"\bwget\b", r"\bnc\b", r"\bncat\b", r"\btelnet\b", r"\bssh\b",
    r"\bscp\b", r"\bsftp\b", r"\bftp\b", r"\brsync\b",
    r"invoke-webrequest", r"invoke-restmethod", r"\biwr\b", r"\bcurl\.exe\b",
    r"start-bitstransfer", r"net\s+use", r"\bnslookup\b",
    r"git\s+push", r"git\s+remote\s+add", r"git\s+fetch", r"git\s+pull", r"git\s+clone",
    r"pip\s+install", r"pip3\s+install", r"npm\s+install", r"npm\s+i\b",
    r"conda\s+install", r"apt(-get)?\s+install", r"choco\s+install", r"winget\s+install",
    r"urllib", r"requests\.(get|post|put|delete)", r"http[s]?://",
    # --- destructive host operations ---
    r"\brm\s+-rf\b", r"\brm\s+-fr\b", r"rmdir\s+/s", r"\bdel\s+/", r"remove-item.*-recurse",
    r"\bmkfs\b", r"\bdd\s+if=", r"\bformat\b", r":\(\)\s*\{", r">\s*/dev/sd",
    r"\bshutdown\b", r"\breboot\b", r"\bhalt\b", r"reg\s+delete", r"\bdiskpart\b",
    # --- privilege escalation ---
    r"\bsudo\b", r"\brunas\b", r"\bdoas\b",
]
_DENY_RE = re.compile("|".join(_DENY_PATTERNS), re.IGNORECASE)


def _denied(command) -> str | None:
    text = command if isinstance(command, str) else " ".join(map(str, command))
    m = _DENY_RE.search(text)
    return m.group(0) if m else None


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
        hit = _denied(command)
        if hit is not None:
            return ValidationResult.reject(
                f"shell.exec refused unsafe command (matched {hit!r}): "
                "no network egress / destructive / privilege-escalating commands allowed")
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
