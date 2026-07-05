# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #17 names a gap Claude Code closes but jcode does
not: **user-configurable permission rules + REPL modes.** In Claude Code, a developer can drop a
settings file mapping a tool-pattern to `allow`/`ask`/`deny`, and cycle the session through
`plan` (propose only, no side effects), `default`, and `acceptEdits` modes -- deterministic,
user-authored policy layered ON TOP OF the product's built-in safety envelope, never a way
around it. Today jaros-code has hard, non-configurable gates (egress/destructive-op denylist,
secret-guard, path-jail) but no user-facing rules layer and no mode concept at all -- row #17 is
`partial`/`lever-named`.

This spec closes that gap the same way EXT-046 (skills) and EXT-047 (hooks) closed their own
product-surface gaps: a small, deterministic, execution-plane module (`harness/permissions.py`)
that loads a user's `.jcode/permissions.json` (project) and/or `~/.jcode/permissions.json` (user)
config -- pure inert JSON data mapping `{tool, arg, action}` rules -- plus a thin, additive wiring
of a `mode` + those rules into the ONE existing choke point (`harness.coding_loop.Runtime.apply`,
the same gate -> executor -> decision-log seam EXT-047's hooks already extended) and a `/mode`
REPL command. No new reasoning mechanism is invented: deciding which rule applies is a pure
first-match glob lookup, never a model judgement, and the model never authors or approves a
permission rule (the user does, by editing the JSON file) or picks a mode (the user does, via
`/mode`).

This converges PRIME-001 on three tenets at once. **Tenet 1 (two-plane discipline):** permission
rules and modes are pure execution-plane config consumed at the clerk's existing seam -- no model
call is ever involved in deciding allow/ask/deny or in choosing a mode. **Tenet 3 (honesty, THE
central design constraint of this spec):** the built-in HARD gates (egress, destructive-ops,
secrets, path-jail) are enforced FIRST and unconditionally; a user's `allow` rule can only ever
NARROW what already passed those gates -- it can never widen, weaken, or bypass them. This is
proven by an explicit test, not asserted by intent alone. An `ask` action that has no interactive
prompt available (a headless/one-shot run) degrades to a safe deny rather than hanging --
never-hang is as much a Tenet-3 honesty property as never-silently-fabricating a result. **Tenet 5
(Claude-Code-like UX):** `/mode [plan|default|acceptEdits]` and a `permissions.json` convention are
direct product-surface parity, exactly what row #17 asks for. Per Tenet 3, the Product-Parity
Checklist (EXT-041) is only flipped for row #17 once the rules loader, the safety invariant, and
the mode cycle are ALL genuinely built and test-covered; any residual gap (e.g. a `bypassPermissions`
mode, a settings-hierarchy precedence UI) is named honestly, not hidden.
