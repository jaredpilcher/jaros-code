# Implementation Tasks

### [TASK-1] MCP client (config + stdio protocol + gated Decision + `/mcp`)

Build the first slice of an MCP client: a two-tier `.jcode/mcp.json` config loader, a bounded
stdio JSON-RPC client (handshake/discovery/invocation, never hangs, clean subprocess shutdown), a
new gated `mcp.tool_call` Decision type enforcing the same denylist `shell.exec` uses on the
server's launch command, and a `/mcp` CLI command to list servers/tools and invoke one.

#### Steps
1. Create `harness/mcp_config.py`: `@dataclass(frozen=True) MCPServerDef(name, command, args,
   env, source)`. A private `_parse_server_entry`/`_parse_mcp_file` pair (tolerant JSON parse,
   skip malformed entries, never raise) and `load_project_mcp_config(root=".")`/
   `load_user_mcp_config()`/`load_mcp_config(root=".")` (project + user tiers, PROJECT wins on a
   name collision — mirrors EXT-050 subagents' precedence rule).
2. Create `harness/mcp_client.py`: `@dataclass(frozen=True) MCPServerSpec(name, command, args,
   env)` and `MCPTool(name, description, input_schema, server)`. A local `_scrubbed_env` (mirrors
   `harness.secure_exec._scrubbed_env`'s allow-list, kept local so this module has no dependency
   on `secure_exec`'s private surface) and a local `_kill_tree` (mirrors
   `shell_exec_tool.py::_kill_tree`). A background-thread + `queue.Queue`-based line reader so
   every stdout read is timeout-bounded on every platform (no `select()` on a pipe). `class
   MCPClient` (`start()`, `initialize()`, `list_tools()`, `call_tool(name, arguments)`, `close()`)
   speaking newline-delimited JSON-RPC 2.0 (`initialize` → `notifications/initialized` →
   `tools/list` / `tools/call`). Top-level `discover_tools(spec, timeout=...)` and
   `call_tool(spec, tool_name, arguments, timeout=...)` each do ONE stateless launch → handshake →
   action → close, returning a structured `{"ok", ..., "error"}` dict, never raising.
3. Create `.jaros-data/tools/mcp_tool_call_tool.py`: `class MCPToolCallTool` with `NAME =
   "mcp.tool_call"`. `validate()` checks the payload's `server`/`tool` structurally, THEN applies
   the SAME network-egress/destructive-command/privilege-escalation denylist regex classes
   `shell_exec_tool.py` uses to `server["command"]` + `server.get("args")` — a denylisted launch
   command is rejected here, before any subprocess is spawned. `execute()` calls
   `harness.mcp_client.call_tool(...)` and returns its result dict.
4. In `harness/cli.py`: `JcodeCli.__init__` loads `self.mcp_servers = load_mcp_config(".")`
   (defensive `try/except` → `{}`), mirroring the `self.hooks_config`/`self.skills`/
   `self.subagents` caching precedent. Add `cmd_mcp(self, arg)`: no argument lists every
   configured server + its LIVE-discovered tools (via `harness.mcp_client.discover_tools`, bounded
   timeout, an unreachable server contributes an honest inline error without blocking the rest);
   `"call <server> :: <tool> :: <json-args>"` builds a real `mcp.tool_call` Decision (via
   `self._mk`) and applies it through `self.rt` (the gated seam), returning an honest error for an
   unknown server or a `RuntimeError` (gate refusal) without raising. Document `/mcp` and the
   `.jcode/mcp.json` convention in the module docstring's command list and `/help`.
5. Update `harness/product_parity.py` row `id=18` (External-tool extensibility protocol): flip
   `state` to `"partial"`; `current_state` names what is genuinely delivered (two-tier config,
   stdio handshake, discovery, gated `mcp.tool_call` invocation via the narrows-never-bypasses
   denylist, `/mcp`) and what remains deferred (resources/prompts/notifications, the SSE/HTTP
   transport, a persistent server connection across turns, model-invocable auto-suggestion);
   `next_lever` names only that residual gap. Mirror the same honest update into
   `docs/GAP-MAP.md` row #18's `State`/`Current honest state`/`Next lever` columns (GAP-MAP state
   `probed`).
6. Update `tests/test_ext041_product_parity.py`: update
   `test_score_default_rows_reflects_honest_current_baseline`'s `n_total`/`n_works`/derived
   `n_partial + n_missing` assertions to match row #18's new `partial` state (the `works == [...]`
   pin does NOT gain `18`, since this slice is honestly `partial`).
7. Write `tests/test_ext054_mcp.py` (HERMETIC — no real external server/network; a FAKE in-process
   MCP server or a monkeypatched transport only): `load_mcp_config` project+user-tier combination,
   project-wins-on-collision, malformed-config/entry skipping, no-config no-op; `MCPClient`/
   `discover_tools`/`call_tool` against a fake stdio MCP server (a small controlled Python
   subprocess script speaking the real protocol, OR an injected fake `popen`-like object) proving
   the `initialize`/`tools/list`/`tools/call` handshake round-trips correctly; an unreachable/dead/
   hung server causes a BOUNDED, measured-elapsed-time honest error (never hangs — assert real
   wall-clock time stays under a small bound); a real subprocess is cleanly terminated (no
   orphaned process) in both the success and failure paths; `MCPToolCallTool.validate()` +
   `Runtime.apply` end-to-end proving the gated-Decision path for a tool call AND the
   can't-escalate-past-the-hard-gate invariant (a denylisted server launch command is refused by
   `validate_decision()`, mirroring EXT-050's identical proof); `/mcp` lists servers + tools (or an
   honest empty/unreachable message) and `/mcp call ...` invokes through `self.rt`; `/help`
   documents `/mcp`.

#### Implements
- [REQ-1] MCP server config — discover `.jcode/mcp.json` (project + user tiers)
- [REQ-2] MCP stdio client — bounded handshake, discovery, invocation, clean shutdown
- [REQ-3] Gated Decision — `mcp.tool_call` narrows, never bypasses, the hard gates
- [REQ-4] `/mcp` command — list configured servers + discovered tools, and invoke one
- [REQ-5] Honest Product-Parity Checklist update
