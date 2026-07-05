---
id: EXT-054
title: MCP client — external-tool extensibility protocol (first slice)
status: partial
priority: medium
---

# EXT-054 — MCP client (first slice)

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #18 — a developer drops a
`.jcode/mcp.json` config naming an external MCP (Model Context Protocol) stdio server, jcode
discovers its tools, and can invoke them gated through the existing Decision path. This first slice
delivers the config loader, the stdio JSON-RPC client (handshake + discovery + invocation, bounded
by explicit timeouts, never hangs), a gated `mcp.tool_call` Decision type enforcing the SAME
denylist `shell.exec` already uses on the server's launch command, and a `/mcp` CLI surface.
Resources, prompts, notifications, and the SSE/HTTP transport are honestly deferred.

### [REQ-1] MCP server config — discover `.jcode/mcp.json` (project + user tiers)

A deterministic loader discovers an MCP server config at the PROJECT level
(`<repo>/.jcode/mcp.json`) and the USER level (`~/.jcode/mcp.json`, mirroring the EXT-042/046/047/
050 two-tier convention), each holding a `{"servers": {"<name>": {"command": str, "args": [str,...],
"env": {str: str}}}}` map.

#### Acceptance Criteria
- [x] `harness.mcp_config.load_mcp_config(root=".")` returns a `dict[str, MCPServerDef]` keyed by
      server name, combining PROJECT + USER tiers, with a PROJECT-tier server of the same name
      taking precedence over a USER-tier one (mirrors EXT-050 subagents' precedence rule).
- [x] `MCPServerDef` carries `name`, `command`, `args` (a tuple of strings, empty tuple when
      absent), `env` (a dict of str->str, empty dict when absent), and `source` (the config file
      path, for diagnostics).
- [x] A missing `.jcode/mcp.json` (either tier) yields an empty contribution from that tier — never
      raises, never treated as an error.
- [x] Malformed JSON, a non-dict top level, a missing/non-dict `servers` key, or a malformed
      individual server entry (missing/blank `command`, non-dict item, non-list `args`, non-dict
      `env`) is SKIPPED — never raised — so one bad entry can never break discovery of the others.
- [x] No `.jcode/mcp.json` anywhere (either tier) yields `load_mcp_config() == {}` — a graceful
      no-op, zero behavior change for every downstream caller.

### [REQ-2] MCP stdio client — bounded handshake, discovery, invocation, clean shutdown

`harness.mcp_client` speaks the MCP stdio JSON-RPC transport: launch a server subprocess (scrubbed
environment — no ambient host secrets reach the server), perform the `initialize` handshake (plus
the `notifications/initialized` follow-up notification), `tools/list` to discover tools, and
`tools/call` to invoke one. EVERY subprocess read is timeout-bounded (a background-thread +
`queue.Queue` reader, portable to Windows where `select()` on a pipe does not work) — a dead, hung,
or slow server degrades to an honest `{"ok": False, "error": ...}` within the configured timeout,
NEVER an indefinite hang. `close()`/the stateless per-call lifecycle always attempts a clean
subprocess shutdown (stdin EOF, bounded wait, then a process-tree kill if still running).

#### Acceptance Criteria
- [x] `harness.mcp_client.discover_tools(spec, timeout=...)` launches the server named by `spec`
      (an `MCPServerSpec`), performs `initialize` + `tools/list`, and returns
      `{"ok": True, "tools": [MCPTool, ...], "error": None}` on success — each `MCPTool` carrying
      `name`, `description`, `input_schema`, and `server` (the spec's name).
- [x] `harness.mcp_client.call_tool(spec, tool_name, arguments, timeout=...)` launches the server,
      performs `initialize` + `tools/call` with the given `tool_name`/`arguments`, and returns
      `{"ok": True, "result": ..., "error": None}` on success.
- [x] A server that never responds (or exits without a valid handshake) causes `discover_tools`/
      `call_tool` to return `{"ok": False, "error": ...}` within the configured `timeout` —
      asserted by measuring the actual bounded elapsed wall-clock time in a test, never hanging.
- [x] The launched subprocess's environment is scrubbed to a small allow-list (mirrors
      `harness.secure_exec._scrubbed_env`'s allow-list) plus whatever `env` the server's config
      supplies — no ambient host environment variable not on the allow-list reaches the child.
- [x] Every code path (success, timeout, a malformed JSON-RPC response, an unexpected exception)
      results in the launched subprocess being cleanly terminated — no orphaned process is left
      running after `discover_tools`/`call_tool` returns, proven for a real subprocess in a test.

### [REQ-3] Gated Decision — `mcp.tool_call` narrows, never bypasses, the hard gates

Every MCP `tools/call` reaches the host ONLY as a `mcp.tool_call` Decision applied through
`harness.coding_loop.Runtime.apply` — the SAME gate → executor → decision-log choke point every
other tool call already passes through. A new custom tool
(`.jaros-data/tools/mcp_tool_call_tool.py`) registers this Decision type; its `validate()` applies
the SAME network-egress/destructive-command/privilege-escalation denylist `shell.exec`
(EXT-001/REQ-7) already enforces to the MCP server's LAUNCH command (`command` + `args`) — a
denylisted launch command is refused HERE, before any subprocess is ever spawned. This mirrors
EXT-048's/EXT-050's identical safety invariant: a user-authorized extension surface can only NARROW
what the hard gates already permit, never widen past them.

#### Acceptance Criteria
- [x] `MCPToolCallTool.validate(decision)` rejects a `mcp.tool_call` Decision whose payload is
      missing a `server` dict, a non-empty `server.command`, or a non-empty `tool` name.
- [x] `MCPToolCallTool.validate(decision)` rejects a `mcp.tool_call` Decision whose `server.command`
      (+ `args`) matches the network-egress/destructive/privilege-escalation denylist (e.g. a
      server command containing `curl`, `rm -rf`, `sudo`) — proven by an explicit test applying the
      Decision through a REAL `harness.coding_loop.Runtime` (mirrors EXT-050's identical
      "allowlisted-but-denylisted `shell.exec` is still refused" proof) and asserting the rejection
      happens at `validate_decision()` (`RuntimeError` matching "gate rejected"), i.e. BEFORE any
      subprocess is spawned.
- [x] A `mcp.tool_call` Decision with a SAFE server command passes the hard gate and reaches
      `MCPToolCallTool.execute()`, which calls `harness.mcp_client.call_tool(...)` and returns its
      result.
- [x] This spec adds NO new `harness.coding_loop.Runtime` constructor parameter — `mcp.tool_call`'s
      gate is entirely its own `validate()`, registered exactly like every other custom tool via
      the existing `load_custom_tools` scan; every pre-EXT-054 `Runtime` caller/test is
      byte-identical.

### [REQ-4] `/mcp` command — list configured servers + discovered tools, and invoke one

`/mcp` (no argument) lists every configured MCP server and its LIVE-discovered tools (name +
description), reporting an honest per-server error when a server is unreachable within a bounded
timeout rather than hanging the whole listing. `/mcp call <server> :: <tool> :: <json-args>`
invokes a discovered tool through the gated `mcp.tool_call` Decision path (via `self.rt`). `/help`
documents both and the `.jcode/mcp.json` convention.

#### Acceptance Criteria
- [x] `JcodeCli.__init__` loads `self.mcp_servers = load_mcp_config(".")` (defensive
      `try/except` → `{}`), mirroring the `self.hooks_config`/`self.skills`/`self.subagents`
      caching precedent.
- [x] `JcodeCli.cmd_mcp("")` with no configured servers reports an honest
      "(no MCP servers configured...)"-style message rather than a blank/silent gap.
- [x] `JcodeCli.cmd_mcp("")` with configured servers lists each server name and its discovered
      tools (name + description), or an honest per-server "(unreachable — ...)" note for a server
      that fails discovery — one unreachable server never prevents the others from being listed.
- [x] `JcodeCli.cmd_mcp("call <server> :: <tool> :: <json-args>")` builds a real `mcp.tool_call`
      Decision and applies it through `self.rt` (the gated seam); an unknown server name returns an
      honest error (naming `/mcp` as where to discover what's configured) without raising; a gate
      refusal (e.g. a denylisted server command) surfaces the gate's own rejection reason.
- [x] `/help`'s command list documents `/mcp` and the `.jcode/mcp.json` convention (the
      `{"servers": {...}}` shape).

### [REQ-5] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=18` (External-tool extensibility protocol) is flipped to
`"partial"` (NOT `"works"`) — honestly reflecting that this is a genuine first slice: config
loading, the stdio handshake, discovery, gated invocation via the narrows-never-bypasses safety
invariant, and `/mcp` are genuinely delivered and test-covered, while resources/prompts/
notifications/the SSE/HTTP transport/a persistent server connection remain deferred, named in
`next_lever`. `docs/GAP-MAP.md` row #18 and `tests/test_ext041_product_parity.py`'s honesty-pin are
updated to match, mirroring how EXT-042/043/044/045/046/047/048/049/050 each did on landing.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=18` `state` is `"partial"`, with `current_state` naming
      exactly what is delivered and what remains deferred, and `next_lever` naming the residual gap.
- [x] `docs/GAP-MAP.md` row #18's `State`/`Current honest state`/`Next lever` columns are updated to
      match (GAP-MAP `probed`, not `closed`).
- [x] `tests/test_ext041_product_parity.py`'s aggregate-bound assertions (`n_total`/`n_works`/
      `n_partial`/`n_missing`/`pct`) are updated to reflect row #18's new `partial` state (the
      `works == [...]` pin is UNCHANGED — row #18 is not added to it, since this slice is honestly
      `partial`, not `works`).
