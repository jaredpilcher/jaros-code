"""EXT-054: MCP server configuration -- discover `.jcode/mcp.json` (project) and/or
`~/.jcode/mcp.json` (user), mirroring the EXT-042 `JCODE.md` / EXT-046 `skills` / EXT-047 `hooks` /
EXT-050 `subagents` two-tier convention.

The config file is pure inert DATA (Tenet 1, two-plane discipline): this module only loads/parses
it into a registry of `MCPServerDef`s -- it never launches a server subprocess itself (that is
`harness.mcp_client`'s job, consulted only through the gated `mcp.tool_call` Decision path).

Every function here is defensive, mirroring `harness/hooks.py`/`harness/subagents.py`: a
missing/unreadable config file, an unresolvable home directory, or malformed JSON degrades to "no
servers configured" rather than raising -- an MCP config feature must never crash the CLI it
extends. No `.jcode/mcp.json` anywhere (either tier) is a complete no-op: zero behavior change.
"""

# #EXT-054-REQ-1 Start
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_MCP_SUBPATH = Path(".jcode") / "mcp.json"
_USER_MCP_SUBPATH = Path(".jcode") / "mcp.json"


@dataclass(frozen=True)
class MCPServerDef:
    """One configured MCP server: how to LAUNCH it (`command` + `args`), an optional `env`
    overlay, and `source` (the config file path, for diagnostics). Launching is never done here --
    see `harness.mcp_client`."""

    name: str
    command: str
    args: "tuple[str, ...]" = ()
    env: "dict[str, str]" = field(default_factory=dict)
    source: str = ""


def _parse_server_entry(name, item, source: str) -> "MCPServerDef | None":
    """Parse one `servers` entry. Returns `None` (skip) for anything malformed (not a dict, a
    missing/blank `command`) -- never raises. A non-list `args` or non-dict `env` degrades to
    empty rather than rejecting the whole entry."""
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(item, dict):
        return None
    command = item.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    raw_args = item.get("args")
    args = tuple(a for a in raw_args if isinstance(a, str)) if isinstance(raw_args, list) else ()
    raw_env = item.get("env")
    env = ({str(k): str(v) for k, v in raw_env.items()} if isinstance(raw_env, dict) else {})
    return MCPServerDef(name=name.strip(), command=command, args=args, env=env, source=source)


def _parse_mcp_file(path: Path) -> "dict[str, MCPServerDef]":
    """Parse one `mcp.json` file into `{name: MCPServerDef}`. Never raises: a missing file,
    unreadable/non-UTF-8 file, invalid JSON, a non-dict top level, a missing/non-dict `servers`
    key, or any per-entry malformation degrades to that piece contributing nothing rather than
    aborting the whole parse (one bad server entry never blocks the others)."""
    out: "dict[str, MCPServerDef]" = {}
    try:
        if not path.is_file():
            return out
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    servers = raw.get("servers")
    if not isinstance(servers, dict):
        return out
    for name, item in servers.items():
        sd = _parse_server_entry(name, item, str(path))
        if sd is not None:
            out[sd.name] = sd
    return out


def load_project_mcp_config(root: "str | Path" = ".") -> "dict[str, MCPServerDef]":
    """Discover + parse the PROJECT-level `<root>/.jcode/mcp.json`. Returns `{}` when absent,
    unreadable, or malformed -- never raises."""
    try:
        return _parse_mcp_file(Path(root) / _PROJECT_MCP_SUBPATH)
    except Exception:
        return {}


def load_user_mcp_config() -> "dict[str, MCPServerDef]":
    """Discover + parse the USER-level `~/.jcode/mcp.json`. Returns `{}` when absent, unreadable,
    malformed, or the home directory can't be resolved -- never raises."""
    try:
        home = Path.home()
    except Exception:
        return {}
    try:
        return _parse_mcp_file(home / _USER_MCP_SUBPATH)
    except Exception:
        return {}


def load_mcp_config(root: "str | Path" = ".") -> "dict[str, MCPServerDef]":
    """Combine the PROJECT + USER tiers into one `{name: MCPServerDef}` registry: a PROJECT-tier
    server WINS on a name collision with a USER-tier one (mirrors EXT-050 subagents' precedence
    rule -- server names are a registry, not an additive list like EXT-047 hooks). Returns `{}`
    (no servers anywhere) when neither tier has content -- a graceful no-op that leaves every
    caller byte-identical to before this spec. Never raises.
    """
    user = load_user_mcp_config()
    project = load_project_mcp_config(root)
    merged: "dict[str, MCPServerDef]" = dict(user)
    merged.update(project)  # project wins on a name collision
    return merged
# #EXT-054-REQ-1 End
