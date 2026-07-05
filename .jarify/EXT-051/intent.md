# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #22 names a gap Claude Code closes but jcode does
not: **context management for long sessions**. Claude Code lets a user pull an arbitrary file's
content straight into the conversation with `@path`, and lets a long-running session shrink itself
back down with `/compact` once it grows unwieldy. jcode already has the deeper machinery this needs
(a bounded recent-transcript view and an over-budget auto-condensation summarizer, EXT-036
REQ-12/REQ-15) but exposes neither of the two USER-FACING surfaces row #22 asks for: there is no
way to reference a file by name inside a plain request, and no manual command to shrink a session
that has grown long.

This spec closes that gap with two small, deterministic, execution-plane additions that both reuse
machinery this codebase already built rather than inventing new mechanisms: (1) `harness/atrefs.py`
is a pure string-composition module that finds `@path`/`@dir/` tokens in a plain-language request
and inlines the referenced content, read through the SAME gated `fs.read`/`fs.list` tools `/read`
and `/ls` already use — never a raw `open()`; (2) `harness/session.py` gains `compact_session()`,
which reuses the EXISTING `_summarize_turns()` narrow-model-call summarizer that `condense()`
(REQ-15) already built, but — unlike `condense()`'s transient routing VIEW — actually mutates and
persists the session's transcript, because `/compact` is a user-invoked, durable shrink, not a
per-turn routing convenience.

This converges PRIME-001 on two tenets. **Tenet 1 (two-plane discipline):** `@`-expansion and
`/compact` are both deterministic string/state operations with no model judgement of their own —
the only model call anywhere in this spec is `_summarize_turns()`, which already existed and is
reused, not duplicated; every file read goes through the existing gated tool path, never a raw
host read. **Tenet 5 (Claude-Code-like UX):** this is direct product-surface parity — a user can
pull a file into context with `@path` and manually shrink a long session with `/compact`, exactly
what row #22 names. Per Tenet 3 (honesty), row #22 is only flipped from `partial` to `works` once
both surfaces are genuinely built, wired through the existing routing chain, and test-covered; the
residual gap (no context-usage meter, no auto-compact-on-threshold trigger, no `@path` expansion
inside `JCODE.md` itself) is named, not hidden.
