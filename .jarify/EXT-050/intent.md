# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #19 names a gap Claude Code closes but jcode does
not: **user-authorable subagents**. In Claude Code, a developer drops a markdown file describing a
scoped agent (a system prompt + a tool allowlist + an optional model) and the CLI can delegate a
task to it with its own narrower context and toolset. Today every jcode agent is builder-authored
Python in `.jaros-data/agents/` — there is no way for a user of this repo, or any repo jcode runs
in, to author a new scoped agent without editing the harness itself.

This spec closes that gap the same way EXT-046 (custom skills/commands) closed the analogous
command-authoring gap: a small, deterministic, execution-plane module
(`harness/subagents.py`) discovers user-authored markdown files at a conventional path
(`.jcode/agents/<name>.md`, project tier, and `~/.jcode/agents/<name>.md`, user tier — project wins
on a name collision, mirroring EXT-042/046/047/048's two-tier convention) and registers each as a
named, delegatable subagent. The file's body is inert data — a system-prompt prefix, never
executed as code — that, once combined with a delegated task, is handed to the SAME gated
`harness.coding_loop.Runtime` + plain-language routing chain every other agent turn already uses.
No new reasoning mechanism, no new side-effect path, and no new Decision type is invented.

This converges PRIME-001 on two tenets at once. **Tenet 1 (two-plane discipline):** the `.md` file
is pure inert data, discovered and parsed by deterministic code; the subagent it describes is
STILL just a Gemma judgement step emitting inert Decisions — the gated `Runtime.apply` seam (gate
→ executor → decision-log) performs every side effect exactly as it does for every other agent,
never bypassed. Critically, this spec ADDS a safety invariant at that exact seam: a subagent's
`tools:` allowlist can only NARROW what the hard gates already permit — intersected with them, never
substituted for them — so a user-authored subagent can never grant itself capability the built-in
denylist/path-jail/secrets gates already refuse. **Tenet 5 (Claude-Code-like UX):** this is direct
product-surface parity — a developer can author a new scoped subagent for THIS repo without waiting
on a jaros-code code change, precisely what row #19 asks for. Per Tenet 3 (honesty), the
Product-Parity Checklist (EXT-041) row #19 is only flipped once the registry, delegation, and the
tool-allowlist safety invariant are genuinely built and test-covered; any deferred residual (e.g.
narrowing the deeper multi-step/`/agent` flows' own internally-constructed Runtimes) is named, not
hidden.
