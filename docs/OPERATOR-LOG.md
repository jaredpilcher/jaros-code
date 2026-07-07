# Operator Log

A short, dated log of changes to the **operator** — the Claude Code CLI session driving this
repo's autonomous work — as distinct from the **project's own model**. These are not the same
thing: PRIME-001 tenet 2 (small-model-only, zero paid inference) governs what `jaros-code`
itself uses for reasoning (Gemma 4 2B `e2b` via llama.cpp on the Jetson) and is unaffected by
anything in this file. This log exists purely so a future session/reader can see when and why
the *assistant* running the CLI changed.

## 2026-07-06 — operator switched Opus 4.8 → Sonnet 5 mid-session

Owner switched the Claude Code CLI operator model from Claude Opus 4.8 to Claude Sonnet 5
partway through an active autonomous session (the daily-driver parity-instrument growth work
was in flight at the time of the switch). Work continued without interruption to the standing
mandates (jaros-code project goals, Jarify governance, the sacred zero-false-done property,
gemma-only $0 inference for the project itself).

No change to PRIME-001 or any tenet. No change to which model `jaros-code` uses for its own
reasoning (still Gemma 4 2B `e2b` exclusively). This is an operator-side note only.
