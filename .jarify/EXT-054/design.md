# EXT-054 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #18 names Claude Code's MCP client surface: connect
an external stdio (or HTTP/SSE) tool server, discover its tools, and call them — the ecosystem
standard for extending a coding harness without a code change. Today jaros-code has NOTHING here:
no client, no config surface, no wiring. Every tool jcode calls today is a hand-authored
`.jaros-data/tools/*.py` module.

The fix must not invent a second execution mechanism or a way around the existing safety gates: an
MCP tool call is just another host-affecting action, and every host-affecting action in this
harness already has a gated path (`jaros.core.decision_gate.validate_decision` + a registered
tool's own `validate()`/`execute()`, reached via `harness.coding_loop.Runtime.apply`). An MCP
`tools/call` must run through that SAME path, not a raw subprocess/socket call bypassing the gate.

## Mechanism

```
  MCP CONFIG (user-authored data, inert JSON -- never executed directly)
  +---------------------------------------------------------------------------------------+
  | <repo>/.jcode/mcp.json      (PROJECT tier)                                              |
  | ~/.jcode/mcp.json           (USER tier -- optional, mirrors EXT-042/046/047/050)         |
  |                                                                                           |
  |   { "servers": {                                                                        |
  |       "fs-tools": {"command": "npx", "args": ["-y", "@some/mcp-server"], "env": {}}       |
  |   } }                                                                                    |
  +-----------------------------------------+-----------------------------------------------+
                                              | discovered once per CLI instance (mirrors the
                                              | EXT-042/046/047/050 caching precedent)
                                              v
  CONFIG LOADER (harness/mcp_config.py -- NEW module, pure deterministic file I/O, no model calls)
  +---------------------------------------------------------------------------------------+
  | MCPServerDef(name, command, args: tuple[str,...], env: dict, source)                    |
  |                                                                                           |
  | load_project_mcp_config(root=".") / load_user_mcp_config() / load_mcp_config(root=".")    |
  |   project + user tiers; a project-tier server of the same name WINS on a name collision  |
  |   (mirrors EXT-050 subagents' precedence rule -- server names are a registry, like        |
  |   subagent names, not an additive list like EXT-047 hooks). Never raises: a missing/      |
  |   unreadable/malformed file, or one malformed server entry, contributes nothing rather    |
  |   than aborting discovery of the others. No mcp.json anywhere -> {} -> complete no-op.    |
  +-----------------------------------------+-----------------------------------------------+
                                              | a registry dict, cached on JcodeCli
                                              v
  MCP CLIENT (harness/mcp_client.py -- NEW module, pure deterministic subprocess/JSON-RPC I/O)
  +---------------------------------------------------------------------------------------+
  | MCPServerSpec(name, command, args, env)      MCPTool(name, description, input_schema,   |
  |                                                       server)                            |
  |                                                                                           |
  | class MCPClient: launches ONE server subprocess with a SCRUBBED environment (mirrors     |
  |   harness.secure_exec._scrubbed_env's allow-list -- no ambient host secrets/LLAMACPP_*    |
  |   reach the server) via `command`+`args`; speaks newline-delimited JSON-RPC 2.0 over      |
  |   stdin/stdout (the MCP stdio transport): `initialize` -> `notifications/initialized` ->  |
  |   `tools/list` -> `tools/call`. A background reader thread + bounded queue.Queue read      |
  |   means every read is TIMEOUT-BOUNDED on every platform (no `select()` on pipes, which    |
  |   doesn't work on Windows) -- a dead/hung/slow server degrades to an honest timeout        |
  |   error, NEVER a hang. `close()` closes stdin (lets a well-behaved server exit), waits     |
  |   briefly, then kill-trees the process (mirrors shell_exec_tool.py's `_kill_tree`) if it   |
  |   hasn't -- clean shutdown either way.                                                    |
  |                                                                                           |
  | discover_tools(spec, timeout=...) -> {"ok", "tools": [MCPTool,...], "error"}              |
  |   (launch -> initialize -> tools/list -> close, ONE stateless call)                        |
  | call_tool(spec, tool_name, arguments, timeout=...) -> {"ok", "result", "error"}            |
  |   (launch -> initialize -> tools/call -> close, ONE stateless call -- no server process    |
  |   is left running between calls; simpler lifecycle, no dangling-subprocess risk)          |
  +-----------------------------------------+-----------------------------------------------+
                                              | consumed from TWO places
                     +------------------------+------------------------+
                     v                                                  v
  GATED TOOL (.jaros-data/tools/mcp_tool_call_tool.py --      CLI SURFACE (harness/cli.py --
  NEW, loaded by the EXISTING load_custom_tools scan)          JcodeCli, EXISTING seam, additive)
  +----------------------------------------------+          +--------------------------------+
  | Decision type "mcp.tool_call"                 |          | __init__:                      |
  | payload: {server: {command,args,env,name},    |          |   self.mcp_servers =           |
  |           tool: <name>, arguments: {...}}     |          |     load_mcp_config(".")        |
  |                                                |          |                                 |
  | validate(decision):                           |          | cmd_mcp(arg):                  |
  |   * structural: server dict w/ non-empty      |          |   no arg -> lists configured    |
  |     command, non-empty tool name              |          |     servers + discover_tools()  |
  |   * THE HARD GATE (mirrors shell.exec's own    |          |     per server (bounded timeout,|
  |     EXT-001/REQ-7 denylist EXACTLY -- same     |          |     an unreachable server ->    |
  |     regex classes): the server's command+args  |          |     an honest inline error, not |
  |     are checked against the network-egress/    |          |     a crash)                    |
  |     destructive/privesc denylist -- a          |          |   "call <server> :: <tool> ::   |
  |     denylisted launch command is REJECTED      |          |     <json-args>" -> builds a    |
  |     here, before any subprocess is spawned      |          |     real Decision, applies it   |
  |                                                |          |     through self.rt (the SAME   |
  | execute(decision):                             |          |     Runtime.apply gate seam)    |
  |   harness.mcp_client.call_tool(spec, tool,     |          +--------------------------------+
  |   arguments, timeout) -- the real client       |
  +------------------------------------------------+
                     | reached ONLY via Runtime.apply (gate -> executor -> decision-log)
                     v
  GATE SEAM (harness/coding_loop.py::Runtime.apply -- UNCHANGED, no new parameter needed)
  +---------------------------------------------------------------------------------------+
  | apply(decision):                                                                       |
  |   [root-jail / hooks / permissions / tool-allowlist -- all EXISTING, unchanged]         |
  |   gated = validate_decision(decision)   <- mcp_tool_call_tool.validate() runs HERE,      |
  |                                             registered exactly like every other custom   |
  |                                             tool via load_custom_tools -- no Runtime      |
  |                                             change required for this spec                |
  |   if not gated.ok: raise RuntimeError(...)  <- a denylisted MCP server launch command    |
  |                                                 NEVER reaches execute()                  |
  |   outcome = executor.apply(decision, ...)   <- calls MCPToolCallTool.execute()            |
  +---------------------------------------------------------------------------------------+
```

- **No second reasoning mechanism.** WHICH server/tool a request names is either an explicit
  `/mcp call <server> :: <tool> :: <args>` invocation or, for discovery, a deterministic listing —
  the model is never consulted about whether/which MCP call happens in this slice.
- **The gate is never bypassed — this spec adds NO new `Runtime` parameter.** Unlike EXT-047/048/
  050 (which each added a Runtime constructor argument), EXT-054 needs no new bypass-adjacent
  mechanism: `mcp.tool_call` is just another registered custom tool whose OWN `validate()` is the
  hard gate for this Decision type, exactly like `shell.exec`'s own `validate()` is. A subprocess
  is NEVER spawned before `validate_decision()` has already accepted the Decision.
- **The denylist mirrors `shell.exec`'s EXACTLY (EXT-001/REQ-7)** — network egress (curl/wget/ssh/
  git push/pip install/...), destructive host operations (rm -rf, mkfs, shutdown, ...), and
  privilege escalation (sudo/runas/doas) are all refused as an MCP server's LAUNCH command, the
  same way they're refused as a `shell.exec` command — because launching an arbitrary subprocess
  is exactly that risk class. This is proven by an explicit test (mirroring EXT-050's identical
  "allowlisted-but-denylisted `shell.exec` is still refused" proof): an MCP server config naming a
  denylisted command is refused by `validate_decision()`, not merely by an application-level check
  that could be routed around.
- **Bounded, never hangs.** Every subprocess read goes through a background-thread + `queue.Queue`
  reader with an explicit timeout on every `get()` call — this works identically on Windows and
  POSIX (unlike `select()` on a pipe, which doesn't work on Windows). A dead server (exits
  immediately), a hung server (never responds), or a slow server (responds past the timeout) all
  degrade to an honest `{"ok": False, "error": ...}` within the configured timeout — never an
  indefinite block. `close()` always attempts a clean shutdown (stdin EOF, bounded wait, then
  kill-tree) regardless of how the call above it concluded.
- **Scrubbed environment.** The server subprocess launches with a minimal allow-listed environment
  (mirrors `harness.secure_exec._scrubbed_env`'s allow-list exactly, kept as a local copy so this
  module has no dependency on `secure_exec`'s private surface) plus whatever `env` the server's own
  config supplies — no ambient host secret (API keys, `LLAMACPP_*`, tokens) reaches the server
  process by default.
- **Stateless per-call lifecycle (this slice).** `discover_tools`/`call_tool` each launch a FRESH
  subprocess, do the full handshake, perform the one action, and close — no persistent server
  connection is kept across CLI turns. This trades a little latency for a much simpler, leak-free
  lifecycle (no "did I forget to close a lingering server process" class of bug) — named as a
  deferred efficiency improvement, not hidden.
- **Discovery is cached (registry only) once per `JcodeCli` instance**, exactly mirroring
  `self.skills`/`self.hooks_config`/`self.subagents` — but note this caches the CONFIG (which
  servers exist), not a live connection; `/mcp` re-discovers tools live each time it's invoked
  (a server's tool list can change between calls, unlike a static skill/hook file).
- **Never raises.** `load_mcp_config` degrades tier-by-tier and entry-by-entry, exactly like
  `harness/hooks.py`/`harness/subagents.py`; every `mcp_client` function returns a structured
  `{"ok": False, "error": ...}` rather than propagating an exception to its caller.

## Two-plane / honesty

`harness/mcp_client.py` and `harness/mcp_config.py` are pure deterministic execution-plane code
(Tenet 1): subprocess I/O, JSON-RPC framing, and JSON config parsing — no LLM call anywhere in
either module. The DECISION to invoke a specific MCP tool (in this slice) is either an explicit
`/mcp call` command or a discovery listing, never a model judgement. Per Tenet 3,
`harness/product_parity.py` row #18 is flipped to `"partial"` (GAP-MAP `probed`), not `"works"` —
honestly reflecting that this is a genuine first slice (config, handshake, discovery, gated
invocation, and the narrows-never-bypasses safety invariant are all delivered and test-covered)
while resources, prompts, notifications, and the SSE/HTTP transport (the rest of the MCP spec) are
named, not hidden, as deferred.

## Backward compatibility (no regression)

- A repo with no `.jcode/mcp.json` anywhere yields `JcodeCli.mcp_servers == {}` — `/mcp` reports an
  honest empty message, and no MCP-related subprocess is ever spawned. Every existing command/
  Decision type is entirely unaffected — this spec adds a NEW Decision type and NEW modules, and
  touches `harness/cli.py` only additively (a new `self.mcp_servers` attribute + a new `cmd_mcp`
  method + a `/help` line).
- `harness.coding_loop.Runtime` itself is UNCHANGED by this spec (no new constructor parameter) —
  every existing caller/test is byte-identical.

## Out of scope (first slice — REQ-6/7 below close two of these)

MCP resources and prompts (only `tools/list`/`tools/call` are implemented); server-initiated
notifications; the HTTP/SSE transport (stdio only); ~~a persistent server connection kept alive
across multiple CLI turns~~ (closed by REQ-6 below); ~~a "model-invocable when relevant"
auto-suggestion mode where the orchestrator reaches for an MCP tool without an explicit
`/mcp call`~~ (closed by REQ-7 below); MCP server authoring/scaffolding tooling; OAuth/remote-server
authentication. These remain honestly named in `docs/GAP-MAP.md` row #18's "Next lever" as the
residual gap, per Tenet 3.

## Slice 2 — REQ-6 (persistent connections) + REQ-7 (model-invocable routing)

```text
  REQ-6: PERSISTENT CONNECTION MANAGER (harness/mcp_session.py -- NEW, pure execution-plane)
  +---------------------------------------------------------------------------------------+
  | class MCPSessionManager:                                                                |
  |   _clients: dict[str, MCPClient]        -- one live session PER CONFIGURED SERVER NAME  |
  |                                                                                           |
  |   _get_client(spec, timeout):                                                           |
  |     existing = self._clients.get(spec.name)                                             |
  |     if existing and existing.is_alive(): return existing        <- REUSED, no relaunch   |
  |     if existing: existing.close(); evict                        <- crashed -> evicted    |
  |     client = MCPClient(spec, timeout); client.start(); client.initialize()               |
  |     on success: self._clients[spec.name] = client; return client                         |
  |     on failure: return None (never raises)                                               |
  |                                                                                           |
  |   discover_tools(spec, timeout) / call_tool(spec, tool, args, timeout):                  |
  |     client = _get_client(...)                                                           |
  |     try the RPC on the reused client;                                                    |
  |     on any failure (server crashed mid-session) -> evict + ONE retry with a FRESH client; |
  |     still failing -> honest {"ok": False, "error": ...} (same shape mcp_client returns)   |
  |                                                                                           |
  |   close_all(): evict + close() every live session -- called from JcodeCli.on_stop()      |
  |                                                                                           |
  | get_session_manager() / close_all_sessions() -- a process-wide singleton + convenience   |
  | wrapper, so EVERY call site (cmd_mcp, _mcp_call, the REQ-7 model-invocable path, and       |
  | MCPToolCallTool.execute()) shares ONE connection pool, not one each.                      |
  +-----------------------------------------+-----------------------------------------------+
                                              | replaces mcp_client.call_tool()'s stateless
                                              | per-call launch inside MCPToolCallTool.execute()
                                              v
  MCPToolCallTool.execute() (unchanged validate(), unchanged Decision shape) now calls
  `get_session_manager().call_tool(spec, tool, arguments, timeout)` instead of the module-level
  stateless `harness.mcp_client.call_tool(...)` -- the gate/Decision/safety story is IDENTICAL,
  only the lifecycle underneath changed (a REUSED subprocess instead of a fresh one per call).

  JcodeCli.on_stop() (EXT-047's existing Stop-hook seam) additionally calls
  `close_all_sessions()` UNCONDITIONALLY (not gated on hooks_config) so every live MCP session is
  cleanly shut down at REPL /quit/EOF/interrupt or one-shot-run end, with or without any
  .jcode/hooks.json configured.
```

```text
  REQ-7: MODEL-INVOCABLE MCP TOOLS (harness/cli.py -- JcodeCli._route_plain, additive step)
  +---------------------------------------------------------------------------------------+
  | _route_plain(line):                                                                     |
  |   [multistep / subagent-delegation / deterministic-intent fast paths -- UNCHANGED]      |
  |                                                                                           |
  |   if self.mcp_servers:              <- zero cost / zero behavior change when empty        |
  |     tools = discover ALL configured servers' tools via the REQ-6 MCPSessionManager        |
  |     if tools:                                                                            |
  |       prompt the SAME small local model with the catalog (server::tool + description)     |
  |         -> "MCP_TOOL: <server::tool or none>" + "MCP_ARGS: <best-effort JSON>"            |
  |       picked = parse the reply (deterministic regex, mirrors orchestrator_agent's         |
  |                parse_route style)                                                        |
  |       if picked is an EXACT key in the discovered-tool catalog built THIS call:           |
  |         build a mcp.tool_call Decision (SAME shape /mcp call builds) -> self.rt.apply(...) |
  |         -- return its result, DONE (never reaches the orchestrator for this turn)         |
  |       else (none / hallucinated / mismatched name):                                       |
  |         fall through -- the request continues to the orchestrator UNAFFECTED              |
  |                                                                                           |
  |   [orchestrator agent -- UNCHANGED, unaware this step exists]                             |
  +---------------------------------------------------------------------------------------+
```

- **No new `Runtime` parameter, no `validate()` change.** REQ-7's Decision is built and applied
  exactly like `/mcp call`'s — `MCPToolCallTool.validate()` is the SAME hard gate either way, so a
  denylisted server launch command is refused identically regardless of which path proposed the
  Decision. The model only ever contributes an inert `(server::tool, arguments)` pick; the
  deterministic membership check against the ACTUAL discovered registry is what makes this
  "conservative" — a name the model invents (or a stale one from a server that's since gone away)
  can never reach `self.rt.apply` as an assumed-valid Decision.
- **Two-plane, not a second reasoning mechanism.** This is the SAME `_route_plain` chain every
  plain request already goes through — REQ-7 adds one more candidate action alongside `fix`/
  `find`/`run`/.../the orchestrator's own choices, not a parallel routing system.
