# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #18 names a gap Claude Code closes but jcode does
not: an **MCP (Model Context Protocol) client** — the ecosystem-standard way a developer connects
an EXTERNAL tool server (any process speaking the MCP stdio JSON-RPC protocol) to their coding
harness, instantly gaining every tool that server exposes without a code change to the harness
itself. Today jaros-code has no such client at all (`state="missing"`, GAP-MAP `unmeasured`) —
every tool jcode can call is a hand-authored Python module under `.jaros-data/tools/`.

This spec closes the FIRST SLICE of that gap the same way EXT-046 (skills), EXT-047 (hooks), and
EXT-050 (subagents) each closed their own product-surface gap: a small, deterministic,
execution-plane client (`harness/mcp_client.py`) that speaks the MCP stdio transport (launch a
server subprocess, `initialize` handshake, `tools/list` discovery, `tools/call` invocation) plus a
defensive two-tier config loader (`harness/mcp_config.py`, mirroring `.jcode/hooks.json`/
`.jcode/mcp.json`'s `.jcode/agents/*.md` precedent) for `.jcode/mcp.json` (project) and
`~/.jcode/mcp.json` (user). No new reasoning mechanism is invented: WHICH server/tool a request
names is either explicit (`/mcp call <server> :: <tool> :: <args>`) or, in this first slice,
purely a listing/invocation surface — the model never decides whether an MCP call happens.

**The critical two-plane move this spec makes:** every MCP `tools/call` becomes a real Decision
(`type="mcp.tool_call"`) applied through `harness.coding_loop.Runtime.apply` — the SAME gate →
executor → decision-log choke point every other tool call already passes through (EXT-047's hooks
and EXT-050's subagents both proved this seam is reusable for a brand-new external-authorization
surface). A new gated tool (`.jaros-data/tools/mcp_tool_call_tool.py`) applies the SAME
network-egress/destructive-command denylist `shell.exec` already enforces (EXT-001/REQ-7) to the
MCP server's LAUNCH command (command + args) — an MCP server configuration that names a
denylisted command is refused at the hard gate, before any subprocess is ever spawned. This is the
exact invariant EXT-048 (permission rules) and EXT-050 (subagent tool allowlists) already proved
for their own extension surfaces: a user-authorized extension can only NARROW what the hard gates
already permit, never widen past them.

This converges PRIME-001 on two tenets at once. **Tenet 1 (two-plane discipline):** the MCP client
is pure execution-plane code (subprocess I/O, JSON-RPC framing, config parsing) — no model call
anywhere in `harness/mcp_client.py`/`harness/mcp_config.py`, and every MCP tool invocation reaches
the host through a real gated Decision, never a raw call. **Tenet 5 (Claude-Code-like UX):** this
is direct product-surface parity — a developer can connect any MCP-speaking server (the same
servers Claude Code, Cursor, and the rest of the ecosystem already use) to jcode and call its
tools, gated exactly like a built-in one. Per Tenet 3, the Product-Parity Checklist (EXT-041) is
flipped HONESTLY: this first slice delivers config, the stdio handshake, discovery, gated
invocation, and the narrows-never-bypasses safety invariant — genuinely enough to move row #18 off
`missing`, but resources/prompts/notifications/SSE transport (the rest of the MCP spec) are named,
not hidden, as deferred to a later slice. A dead/slow/malicious server can never hang or escalate
the harness — every subprocess interaction is timeout-bounded and every launch passes the hard
gate first.
