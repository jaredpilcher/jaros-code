# Intent

Claude Code feels ALIVE while it works: you see each tool call land as it happens, and a
statusline tells you at a glance what model is serving, what kind of problem it just routed, that
it cost nothing, and how long the last turn took. `docs/GAP-MAP.md`'s Product-surface parity row
#24 names this gap explicitly: jcode's REPL prints only the FINAL result of a turn — a `/agent`
or `/fix` run that takes tens of seconds looks identical to a hang until it suddenly prints
everything at once — and there is no at-a-glance status surface at all.

This spec closes that gap WITHOUT inventing a new observability mechanism. jaros-code already
records every accepted `Decision` to the Jaros hash-chain the instant it is accepted
(`harness.coding_loop.Runtime.apply` → `jaros.state.record_decision`) — that IS the tool-event
stream Claude Code's UI narrates from. EXT-045 adds a thin, optional `on_event` hook at that exact
seam so a concise `→ call` / `✓ result` line can be printed to stdout AS EACH DECISION IS APPLIED,
plus a `statusline()` function that renders `model · problem-class · $0 · latency` from state the
CLI already tracks (the active model label, the last routed action, and the wall-clock latency of
the last turn). Both are pure presentation over already-produced data — no new judgement, no
model call, no second logging mechanism.

This converges PRIME-001 in two ways. First, it directly advances Tenet 5 (Claude-Code-like UX):
a legible, live terminal feel is exactly the "familiar, transparent terminal feel" the tenet names,
and closes Product-Parity Checklist row #24 honestly (streaming + statusline + `/help`
discoverability delivered; a live in-flight spinner, `/export`, tab-completion, and themes remain
honestly deferred, not inflated). Second, it reinforces Tenet 1 (two-plane discipline) and Tenet 3
(honesty): the streaming narration is presentation over the SAME deterministic-execution-plane
data that is already durably logged — it adds no new non-determinism, no new model call, and (per
Tenet 5's own subordination) never overrides a higher tenet: it is suppressed under
`--output-format json` (EXT-043) so the machine-composable surface stays byte-clean, and a plain
run with none of it enabled remains byte-identical to before this spec.
