"""Gated Jaros tool ``mcp.tool_call`` (EXT-054 / REQ-3).

Wraps an MCP (Model Context Protocol) server's `tools/call` as a gated Decision. Every MCP tool
invocation reaches the host ONLY through this `validate()`/`execute()` seam -- the SAME
gate -> executor -> decision-log choke point every other tool call passes through
(`harness.coding_loop.Runtime.apply`).

``validate()`` applies the SAME network-egress/destructive-command/privilege-escalation denylist
`shell_exec_tool.py` already enforces (EXT-001/REQ-7) to the MCP server's LAUNCH command
(`command` + `args`) -- launching an arbitrary subprocess is exactly the same risk class as
running an arbitrary shell command, so an MCP server configuration naming a denylisted command is
REFUSED HERE, before any subprocess is ever spawned. This is the invariant EXT-048's permission
rules and EXT-050's subagent tool allowlists already proved for their own extension surfaces: a
user-authorized extension can only NARROW what the hard gates already permit, never widen past
them.
"""

from __future__ import annotations

import re

from jaros.core.decision_gate import ValidationResult

# #EXT-054-REQ-3 Start
# Mirrors shell_exec_tool.py's `_DENY_PATTERNS`/`_DENY_RE` exactly (kept as a local copy so this
# tool has no import dependency on another dynamically-loaded tool module -- see
# `jaros.execution.tools.load_custom_tools`, which loads each tool file in isolation via
# `importlib.util.spec_from_file_location`, so a relative/sibling import between tool files isn't
# available here). Same two non-negotiable classes: no internet WRITES/network egress, no
# destructive or privilege-escalating host operations -- applied to an MCP server's LAUNCH
# command, the same risk class as a `shell.exec` command.
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


def _denied(command, args) -> "str | None":
    parts = [command] if isinstance(command, str) else []
    if isinstance(args, list):
        parts.extend(str(a) for a in args)
    text = " ".join(parts)
    m = _DENY_RE.search(text)
    return m.group(0) if m else None


class MCPToolCallTool:
    NAME = "mcp.tool_call"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        server = payload.get("server")
        if not isinstance(server, dict):
            return ValidationResult.reject("mcp.tool_call requires a 'server' dict")
        command = server.get("command")
        if not isinstance(command, str) or not command.strip():
            return ValidationResult.reject(
                "mcp.tool_call requires a non-empty server.command")
        tool = payload.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            return ValidationResult.reject("mcp.tool_call requires a non-empty 'tool' name")
        # THE HARD GATE: a denylisted server LAUNCH command is refused here, before any
        # subprocess is ever spawned -- an MCP tool can only NARROW what's already permitted,
        # never widen past this (mirrors shell.exec's own EXT-001/REQ-7 denylist exactly).
        args = server.get("args")
        hit = _denied(command, args)
        if hit is not None:
            return ValidationResult.reject(
                f"mcp.tool_call refused unsafe MCP server launch command (matched {hit!r}): "
                "no network egress / destructive / privilege-escalating server commands allowed")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        server = payload["server"]
        tool = payload["tool"]
        arguments = payload.get("arguments") or {}
        timeout = payload.get("timeout_s")
        from harness.mcp_client import MCPServerSpec, DEFAULT_TIMEOUT_S, call_tool

        args = server.get("args")
        env = server.get("env")
        spec = MCPServerSpec(
            name=str(server.get("name") or "mcp"),
            command=server["command"],
            args=tuple(a for a in args if isinstance(a, str)) if isinstance(args, list) else (),
            env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {},
        )
        return call_tool(
            spec, tool, arguments,
            timeout=float(timeout) if timeout else DEFAULT_TIMEOUT_S,
        )
# #EXT-054-REQ-3 End
