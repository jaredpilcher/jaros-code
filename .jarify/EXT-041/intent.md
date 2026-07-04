# Intent

This spec exists to give jaros-code's new **product-surface parity axis** its own scoreboard. The
owner/supervisor directive (2026-07-04) sharpened PRIME-001's bar: parity with Claude Code is not
only "does the model solve the task as well" (the daily-driver / SWE-bench / routed-triple
instruments already measure that) — it is **the WHOLE Claude Code CLI product**, everything a
developer actually experiences at the terminal. PRIME-001's intent names this explicitly: sessions
(continue/resume/fork), headless + Unix composability, an instruction-memory hierarchy, user
extensibility (custom commands/skills, hooks, subagents), an MCP client, permission rules + modes,
checkpoint/rewind, interrupt-and-steer, long-session context management, background runs, terminal
UX, an install/health story, and eventually multimodal input — recorded as the **Product-surface
parity rows (#12-27) of `docs/GAP-MAP.md`**, with their instrument named as **the Product-Parity
Checklist**: "feature-by-feature scoring (works/partial/missing) against the official docs,
re-synced from those docs monthly because Claude Code is a moving target. The capability
scoreboard measures how WELL it solves; this checklist measures whether the PRODUCT is actually
there. Both must converge; neither substitutes for the other."

This spec builds exactly that checklist as a deterministic execution-plane instrument (no model
calls — the row states are transcribed facts about the repo, not a judgement any agent makes) and
wires it into the REPL as `/parity` so the honest baseline percentage is visible at a glance,
alongside `/status`. It converges toward the Prime Directive by making the "whole product, not
just the model's task-solving" bar **measurable and trend-able** — Tenet 3 (reproducible & honest)
applies here as much as to any capability eval: the checklist must report the TRUE current state
(today, mostly `missing`/`partial`) rather than an inflated one, because the only value of a
baseline is that it is honest enough to converge from. Because Claude Code itself keeps shipping
new surface, the checklist carries a `LAST_SYNCED` marker and a standing duty (documented here, not
automated) to re-audit the official docs monthly and grow the row list — an instrument that goes
stale silently would misreport parity as Claude Code moves out from under it.
