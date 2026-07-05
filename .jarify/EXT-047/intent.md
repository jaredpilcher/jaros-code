# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #16 names a gap Claude Code closes but jcode does
not: **user-configurable lifecycle hooks**. In Claude Code, a developer configures a shell command
that fires automatically at `PreToolUse` (before a tool call), `PostToolUse` (after one),
`SessionStart`, or `Stop` -- extending the product with deterministic, user-authored side effects
(a linter run before every edit, a notification on session end, a guard that refuses a dangerous
tool call outright) without a code change to the harness itself. Today jaros-code has exactly the
right SEAM for this -- `harness.coding_loop.Runtime.apply` is the ONE real gate -> executor ->
decision-log choke point every tool call already passes through (EXT-045 proved this by hanging a
streaming `on_event` hook off the same seam) -- but there is no user-facing way to configure a hook
at all.

This spec closes that gap the same way EXT-042 (`JCODE.md`) and EXT-046 (`skills`) closed their
own product-surface gaps: a small, deterministic, execution-plane module (`harness/hooks.py`) that
loads a user's `.jcode/hooks.json` (project) and/or `~/.jcode/hooks.json` (user) config -- pure
inert JSON data, mapping an event name to a list of `{command, matcher}` entries -- and a thin,
additive wiring of that config into the ONE existing choke point (`Runtime.apply`) plus the two
CLI lifecycle boundaries (`JcodeCli.__init__` for `SessionStart`, session-end for `Stop`). No new
reasoning mechanism is invented: hook FIRING is a pure dictionary lookup + glob match (which
configured hook, if any, applies to this event/tool), and every hook's shell command runs through
the SAME gated `shell.exec` Decision path (denylist + timeout + process-tree-kill) every other
tool call already uses -- hooks are user-authorized extensions, but they NEVER bypass the security
gates that already exist.

This converges PRIME-001 on three tenets at once. **Tenet 1 (two-plane discipline):** hooks are
pure execution-plane config consumed at the clerk's existing `validate()`/`execute()` seam -- no
model call is ever involved in deciding whether/which hook fires, and the model never authors or
approves a hook (the user does, by editing the JSON file). **Tenet 3 (honesty):** a `PreToolUse`
hook that exits non-zero genuinely BLOCKS the tool call -- the clerk refuses it exactly like a
gate rejection, never a silent best-effort "try anyway." A hook can never bypass the denylist/
timeout/tree-kill safety envelope, because it runs through the identical `shell.exec` Decision
path (via a fresh, hooks-DISABLED `Runtime`, so firing a hook can never recursively re-trigger
hook firing). **Tenet 5 (Claude-Code-like UX):** this is direct product-surface parity -- a
developer can author repeatable lifecycle automation for THIS repo without waiting on a
jaros-code code change, precisely what row #16 asks for. Per Tenet 3, the Product-Parity
Checklist (EXT-041) is only flipped for row #16 once the four lifecycle events, the config
loader, block-on-nonzero, and gated execution are ALL genuinely built and test-covered -- the
honest residual (richer stream narration of hook activity, an ask/allow/deny permission UX
overlapping row #17) is named, not hidden.
