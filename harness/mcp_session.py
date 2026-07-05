"""EXT-054 REQ-6: a persistent MCP server connection manager -- makes MCP genuinely usable across
CLI turns, instead of slice 1's fresh-subprocess-per-call lifecycle (`harness.mcp_client`'s
stateless `discover_tools`/`call_tool`, still used directly by nothing after this module lands --
kept for its own tests/back-compat).

Pure execution-plane code (Tenet 1: no LLM call anywhere in this module, mirrors
`harness.mcp_client`'s own docstring invariant): `MCPSessionManager` keeps ONE live `MCPClient` per
CONFIGURED SERVER NAME alive for the life of the process, reusing it across every
`discover_tools`/`call_tool` invocation for that server. A crashed/exited server (`is_alive()` goes
`False`) is evicted and transparently relaunched on the next call -- one bounded retry; if the
fresh launch also fails, the call degrades to the SAME honest `{"ok": False, "error": ...}` shape
`harness.mcp_client`'s own stateless functions already return. Never raises, never hangs (every
underlying RPC is still the same timeout-bounded `MCPClient` call slice 1 built).

A process-wide singleton (`get_session_manager()`) is used by EVERY call site that needs an MCP
tool call -- `.jaros-data/tools/mcp_tool_call_tool.py`'s `execute()`, `harness.cli.JcodeCli`'s
`cmd_mcp`/`_mcp_call`, and the model-invocable routing path (`_route_mcp_tool`, REQ-7) -- so one
shared connection pool serves the whole CLI session, not one per call site. `close_all_sessions()`
is called from `harness.cli.JcodeCli.on_stop()` (the SAME seam EXT-047's Stop hooks already fire
from) so every live session is cleanly shut down at REPL `/quit`/EOF/interrupt or one-shot-run end
-- no subprocess is ever leaked.
"""

# #EXT-054-REQ-6 Start
from __future__ import annotations

from harness.mcp_client import DEFAULT_TIMEOUT_S, MCPClient, MCPServerSpec


class MCPSessionManager:
    """Keeps one live `MCPClient` session per server NAME, reused across calls; transparently
    relaunches a crashed session (one bounded retry) rather than either leaking a dead process or
    silently reverting to a fresh-subprocess-per-call lifecycle."""

    def __init__(self, popen=None) -> None:
        self._popen = popen
        self._clients: "dict[str, MCPClient]" = {}

    def _evict(self, name: str) -> None:
        """Close + drop a stored session (best-effort -- never raises)."""
        client = self._clients.pop(name, None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def _launch(self, spec: MCPServerSpec, timeout: float) -> "MCPClient | None":
        """Start + `initialize` a fresh `MCPClient` for `spec`. Returns `None` on any failure
        (never raises) -- the caller degrades to an honest error rather than propagating."""
        client = MCPClient(spec, timeout=timeout, popen=self._popen)
        try:
            client.start()
            client.initialize()
        except Exception:
            try:
                client.close()
            except Exception:
                pass
            return None
        return client

    def _get_client(self, spec: MCPServerSpec, timeout: float) -> "MCPClient | None":
        """Return a live, already-initialized session for `spec.name` -- REUSING one already held
        when it's still alive, evicting + relaunching when it's gone (crashed/exited), or launching
        one for the first time. Returns `None` (never raises) when a fresh launch also fails."""
        existing = self._clients.get(spec.name)
        if existing is not None:
            if existing.is_alive():
                return existing
            self._evict(spec.name)  # the server crashed/exited since the last call
        client = self._launch(spec, timeout)
        if client is not None:
            self._clients[spec.name] = client
        return client

    def discover_tools(self, spec: MCPServerSpec, timeout: float = DEFAULT_TIMEOUT_S) -> dict:
        """`tools/list` against `spec`'s REUSED (or freshly-launched) live session. Never raises:
        returns `{"ok": False, "tools": [], "error": <str>}` on any failure within `timeout`,
        after one evict+relaunch retry if the reused session had crashed mid-session."""
        client = self._get_client(spec, timeout)
        if client is None:
            return {"ok": False, "tools": [],
                     "error": f"MCP server {spec.name!r} is unreachable (launch failed)"}
        try:
            tools = client.list_tools()
            return {"ok": True, "tools": tools, "error": None}
        except Exception as exc:
            # The reused session may have crashed between calls -- evict + ONE honest retry with
            # a freshly-launched session before giving up.
            self._evict(spec.name)
            client = self._get_client(spec, timeout)
            if client is None:
                return {"ok": False, "tools": [], "error": str(exc)}
            try:
                tools = client.list_tools()
                return {"ok": True, "tools": tools, "error": None}
            except Exception as exc2:
                self._evict(spec.name)
                return {"ok": False, "tools": [], "error": str(exc2)}

    def call_tool(self, spec: MCPServerSpec, tool_name: str, arguments: "dict | None" = None,
                  timeout: float = DEFAULT_TIMEOUT_S) -> dict:
        """`tools/call` against `spec`'s REUSED (or freshly-launched) live session. Never raises:
        returns `{"ok": False, "result": None, "error": <str>}` on any failure within `timeout`,
        after one evict+relaunch retry if the reused session had crashed mid-session."""
        client = self._get_client(spec, timeout)
        if client is None:
            return {"ok": False, "result": None,
                     "error": f"MCP server {spec.name!r} is unreachable (launch failed)"}
        try:
            result = client.call_tool(tool_name, arguments or {})
            return {"ok": True, "result": result, "error": None}
        except Exception as exc:
            self._evict(spec.name)
            client = self._get_client(spec, timeout)
            if client is None:
                return {"ok": False, "result": None, "error": str(exc)}
            try:
                result = client.call_tool(tool_name, arguments or {})
                return {"ok": True, "result": result, "error": None}
            except Exception as exc2:
                self._evict(spec.name)
                return {"ok": False, "result": None, "error": str(exc2)}

    def close_all(self) -> None:
        """Cleanly shut down EVERY live session this manager holds. Never raises; safe to call
        more than once (a second call is a no-op -- nothing left to close)."""
        for name in list(self._clients):
            self._evict(name)


# -- process-wide singleton -------------------------------------------------------------------
# Every call site (the gated `mcp.tool_call` tool, `/mcp`/`/mcp call`, and the REQ-7
# model-invocable routing path) shares ONE `MCPSessionManager` so a server launched by one call
# site is reused by the others -- one connection pool for the whole CLI process/session.
_singleton: "MCPSessionManager | None" = None


def get_session_manager() -> MCPSessionManager:
    """Return the process-wide `MCPSessionManager` singleton, constructing it on first use."""
    global _singleton
    if _singleton is None:
        _singleton = MCPSessionManager()
    return _singleton


def close_all_sessions() -> None:
    """Close every live session on the process-wide singleton (a no-op if none exists yet).
    Called from `harness.cli.JcodeCli.on_stop()` -- see that method's docstring -- so a REPL
    `/quit`/EOF/interrupt or a one-shot run's end always cleans up, never leaking a subprocess."""
    if _singleton is not None:
        _singleton.close_all()


def reset_session_manager() -> None:
    """Test seam: close + discard the process-wide singleton so the NEXT `get_session_manager()`
    call constructs a fresh one. Never raises."""
    global _singleton
    if _singleton is not None:
        _singleton.close_all()
    _singleton = None
# #EXT-054-REQ-6 End
