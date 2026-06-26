# Intent

This spec exists to give jaros-code the Claude-Code-like operator experience that Tenet 5
of PRIME-001 calls for: a familiar, transparent terminal harness — slash commands, a
status line naming the local model, a streaming transcript — continually studied against
Claude Code and moved toward parity. But the CLI is never only cosmetic: it is a real
wiring surface whose commands invoke the actual single-purpose agents and deterministic
tools (navigator, commander, fs.grep/list/read, py.symbols, the fix loop), so they are
exercised rather than orphaned, and every command routes its Decision through the same
gate and executor — the CLI never bypasses the two planes. Its deeper aim is that the
user should not have to know which agent or tool to invoke: a plain-language request is
classified by an `orchestrator` agent into an action and dispatched automatically, and a
`planner` agent can turn a request into an inert ordered plan that a deterministic
executor runs step by step. The model decides *what* the user wants; the deterministic
CLI decides *how*. UX serves the tenets above it and never overrides correctness,
reproducibility, or the small-local-model-only constraint.
