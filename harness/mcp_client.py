"""EXT-054: MCP (Model Context Protocol) stdio client -- first slice.

Launches an external MCP server subprocess, performs the `initialize` handshake, discovers its
tools (`tools/list`), and invokes one (`tools/call`) -- pure execution-plane subprocess/JSON-RPC
I/O (Tenet 1: no LLM call anywhere in this module). Every MCP tool a request actually EXECUTES
must reach the host through the gated `mcp.tool_call` Decision (see
`.jaros-data/tools/mcp_tool_call_tool.py`), never a raw call from this module used directly by an
agent.

**Bounded, never hangs.** Every subprocess stdout read goes through a background-thread +
`queue.Queue` reader with an explicit timeout on every `get()` -- this is portable to Windows
(unlike `select()` on a pipe, which only works on POSIX). A dead server (exits immediately), a
hung server (never responds), or a slow server (responds past the timeout) all degrade to an
honest `{"ok": False, "error": ...}` within the configured timeout -- never an indefinite block.

**Clean shutdown, every time.** `close()` (and the stateless `discover_tools`/`call_tool`
convenience functions, which always call it in a `finally`) closes stdin (EOF, letting a
well-behaved server exit on its own), waits briefly, then kill-trees the process (mirrors
`shell_exec_tool.py::_kill_tree` / `harness.secure_exec._kill_tree` exactly -- the same
process-tree-kill technique, not a divergent copy) if it hasn't exited -- no orphaned subprocess
is ever left running.

**Scrubbed environment.** The launched server subprocess gets a minimal allow-listed environment
(mirrors `harness.secure_exec._scrubbed_env`'s allow-list exactly, kept LOCAL here so this module
has no dependency on `secure_exec`'s private surface) plus whatever `env` the server's own config
supplies -- no ambient host secret (API keys, `LLAMACPP_*`, tokens) reaches the server by default.

**Stateless per-call lifecycle (this slice).** `discover_tools`/`call_tool` each launch a FRESH
subprocess, do the full handshake, perform the one action, and close -- no persistent server
connection is kept across CLI turns. Simpler, leak-free; a named deferred efficiency improvement.
"""

# #EXT-054-REQ-2 Start
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass, field

DEFAULT_TIMEOUT_S = 15.0

# Mirrors harness.secure_exec._scrubbed_env's allow-list exactly (kept local -- see module
# docstring). Only these host environment variables survive into a launched MCP server's
# environment; everything else (secrets, tokens, LLAMACPP_*, etc.) is dropped by default.
_SAFE_ENV_KEYS = (
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "LANG", "LC_ALL", "TMP", "TEMP",
    "TMPDIR", "PYTHONPATH", "PYTHONIOENCODING", "HOME", "USERPROFILE", "PATHEXT",
)


def _scrubbed_env(extra_env: "dict | None") -> dict:
    """Build a minimal safe environment for a launched MCP server subprocess: only the small
    `_SAFE_ENV_KEYS` allow-list survives from the host, plus whatever `extra_env` (the server's
    own config) supplies."""
    env: dict = {}
    for key in _SAFE_ENV_KEYS:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    if isinstance(extra_env, dict):
        for k, v in extra_env.items():
            if isinstance(k, str):
                env[k] = str(v)
    return env


def _kill_tree(proc) -> None:
    """Kill `proc` AND its descendants (mirrors `shell_exec_tool.py::_kill_tree` /
    `harness.secure_exec._kill_tree` exactly -- the same choke point, not a divergent copy) so a
    hung MCP server subprocess is never orphaned."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), 9)  # SIGKILL, avoids importing `signal` for one use
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


@dataclass(frozen=True)
class MCPServerSpec:
    """How to launch one MCP server: `command` + `args` (a subprocess invocation) plus an
    optional `env` overlay. Mirrors `harness.mcp_config.MCPServerDef` but is the CLIENT-facing
    shape (no `source`)."""

    name: str
    command: str
    args: "tuple[str, ...]" = ()
    env: "dict[str, str]" = field(default_factory=dict)


@dataclass(frozen=True)
class MCPTool:
    """One tool an MCP server reported via `tools/list`."""

    name: str
    description: str
    input_schema: dict
    server: str


class _LineReader:
    """Reads lines from `stream` on a background thread into a bounded queue, so every read the
    caller performs is timeout-bounded on every platform (no `select()` on a pipe, which does not
    work on Windows). Puts `None` once the stream closes (EOF) -- distinct from a `queue.Empty`
    timeout, which the caller must also handle."""

    def __init__(self, stream) -> None:
        self._q: "queue.Queue" = queue.Queue()
        self._stream = stream
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            for line in iter(self._stream.readline, ""):
                if not line:
                    break
                self._q.put(line)
        except Exception:
            pass
        finally:
            self._q.put(None)  # EOF sentinel

    def readline(self, timeout: float):
        """Returns the next line (str), `None` on EOF, or raises `queue.Empty` on timeout (the
        caller distinguishes "server closed" from "server hasn't answered yet")."""
        return self._q.get(timeout=timeout)


class MCPError(Exception):
    """Raised internally by `MCPClient` methods; callers of the top-level `discover_tools`/
    `call_tool` functions never see this -- it's caught and converted to an honest error dict."""


class MCPClient:
    """A single MCP server session over stdio JSON-RPC 2.0 (newline-delimited messages).
    Construct, `start()`, `initialize()`, then `list_tools()`/`call_tool()`, then `close()` --
    or use the module-level `discover_tools`/`call_tool` convenience functions, which do this for
    you in one bounded, always-cleaned-up call."""

    def __init__(self, spec: MCPServerSpec, timeout: float = DEFAULT_TIMEOUT_S,
                 popen=None) -> None:
        self._spec = spec
        self._timeout = float(timeout) if timeout else DEFAULT_TIMEOUT_S
        self._popen = popen or subprocess.Popen
        self._proc = None
        self._reader: "_LineReader | None" = None
        self._next_id = 1

    # -- lifecycle --------------------------------------------------------------------------
    def start(self) -> None:
        """Launch the server subprocess. Raises `MCPError` on failure to start (caught by the
        module-level convenience functions)."""
        env = _scrubbed_env(self._spec.env)
        cmd = [self._spec.command, *self._spec.args]
        try:
            popen_kwargs = dict(
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env, bufsize=1,
            )
            if sys.platform != "win32":
                popen_kwargs["start_new_session"] = True
            self._proc = self._popen(cmd, **popen_kwargs)
        except Exception as exc:
            raise MCPError(f"failed to start MCP server {self._spec.name!r}: {exc}") from exc
        self._reader = _LineReader(self._proc.stdout)

    def close(self) -> None:
        """Clean shutdown: close stdin (EOF, lets a well-behaved server exit), wait briefly, then
        kill-tree if it hasn't. Never raises."""
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            _kill_tree(proc)
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
        self._proc = None

    def __enter__(self) -> "MCPClient":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # #EXT-054-REQ-6 Start
    def is_alive(self) -> bool:
        """`True` while the launched subprocess is still running, `False` once it has exited
        (or `close()` ran, or `start()` was never called) -- never raises. Consulted by
        `harness.mcp_session.MCPSessionManager` to decide whether a cached session can be
        REUSED for another call, or must be evicted + relaunched (the server crashed)."""
        proc = self._proc
        if proc is None:
            return False
        try:
            return proc.poll() is None
        except Exception:
            return False
    # #EXT-054-REQ-6 End

    # -- JSON-RPC framing ---------------------------------------------------------------------
    def _send(self, obj: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise MCPError("MCP server subprocess is not running")
        try:
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()
        except Exception as exc:
            raise MCPError(f"failed to write to MCP server {self._spec.name!r}: {exc}") from exc

    def _recv(self, expected_id, deadline_s: float) -> dict:
        """Read lines until one matches `expected_id` (skipping notifications/other ids) or the
        remaining budget is exhausted. Raises `MCPError` on timeout, EOF, or malformed JSON."""
        import time
        remaining = deadline_s
        while remaining > 0:
            t0 = time.time()
            try:
                line = self._reader.readline(timeout=remaining)
            except queue.Empty:
                raise MCPError(
                    f"MCP server {self._spec.name!r} did not respond within {deadline_s}s")
            remaining -= (time.time() - t0)
            if line is None:
                raise MCPError(f"MCP server {self._spec.name!r} closed its output unexpectedly")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue  # a non-JSON line (e.g. stray log noise) -- skip, keep waiting
            if not isinstance(msg, dict):
                continue
            if msg.get("id") == expected_id:
                return msg
            # a notification or a response to a different id -- keep waiting for ours
        raise MCPError(f"MCP server {self._spec.name!r} did not respond within {deadline_s}s")

    def _request(self, method: str, params: "dict | None" = None) -> dict:
        req_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        msg = self._recv(req_id, self._timeout)
        if "error" in msg and msg["error"]:
            raise MCPError(f"MCP server {self._spec.name!r} error calling {method!r}: "
                            f"{msg['error']}")
        return msg.get("result") or {}

    def _notify(self, method: str, params: "dict | None" = None) -> None:
        try:
            self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})
        except Exception:
            pass  # best-effort -- a notification failing to send is never fatal

    # -- MCP protocol steps -------------------------------------------------------------------
    def initialize(self) -> dict:
        result = self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "jaros-code", "version": "0.1"},
        })
        self._notify("notifications/initialized")
        return result

    def list_tools(self) -> "list[MCPTool]":
        result = self._request("tools/list")
        tools_raw = result.get("tools") if isinstance(result, dict) else None
        tools: "list[MCPTool]" = []
        for item in (tools_raw or []):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue
            tools.append(MCPTool(
                name=name, description=str(item.get("description") or ""),
                input_schema=item.get("inputSchema") or {}, server=self._spec.name,
            ))
        return tools

    def call_tool(self, name: str, arguments: "dict | None" = None) -> dict:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})


# -- module-level, stateless, one-shot convenience functions ---------------------------------

def discover_tools(spec: MCPServerSpec, timeout: float = DEFAULT_TIMEOUT_S,
                    popen=None) -> dict:
    """Launch `spec`'s server, `initialize`, `tools/list`, then close -- one bounded, stateless
    call. Never raises: returns `{"ok": False, "tools": [], "error": <str>}` on any failure
    (dead/hung/slow server, malformed handshake, ...) within `timeout`."""
    client = MCPClient(spec, timeout=timeout, popen=popen)
    try:
        client.start()
        client.initialize()
        tools = client.list_tools()
        return {"ok": True, "tools": tools, "error": None}
    except MCPError as exc:
        return {"ok": False, "tools": [], "error": str(exc)}
    except Exception as exc:  # never raise -- a client failure must never crash its caller
        return {"ok": False, "tools": [], "error": f"MCP discovery failed: {exc}"}
    finally:
        client.close()


def call_tool(spec: MCPServerSpec, tool_name: str, arguments: "dict | None" = None,
              timeout: float = DEFAULT_TIMEOUT_S, popen=None) -> dict:
    """Launch `spec`'s server, `initialize`, `tools/call(tool_name, arguments)`, then close -- one
    bounded, stateless call. Never raises: returns `{"ok": False, "result": None, "error": <str>}`
    on any failure within `timeout`."""
    client = MCPClient(spec, timeout=timeout, popen=popen)
    try:
        client.start()
        client.initialize()
        result = client.call_tool(tool_name, arguments)
        return {"ok": True, "result": result, "error": None}
    except MCPError as exc:
        return {"ok": False, "result": None, "error": str(exc)}
    except Exception as exc:  # never raise -- a client failure must never crash its caller
        return {"ok": False, "result": None, "error": f"MCP tool call failed: {exc}"}
    finally:
        client.close()
# #EXT-054-REQ-2 End
