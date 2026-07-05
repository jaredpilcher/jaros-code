# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #20 names a gap Claude Code closes but jcode does
not: **fine-grained checkpoint / rewind.** Claude Code auto-checkpoints before EACH edit and lets
a developer `/rewind` code (or conversation, or both) to any recent point, not just the single
most-recent action. jaros-code today has only a WHOLE-RUN checkpoint (EXT-009 REQ-7: `/agent`
snapshots the repo once before it starts, and `/undo` restores that one snapshot) — there is no
per-edit granularity and no way to step back N edits or inspect what changed at each step. Row #20
is `partial`/`probed`.

This spec closes that gap by EXTENDING, not replacing, EXT-009's mechanism: a bounded ring of
per-edit checkpoints keyed to the same seam that already makes every accepted Decision durable —
`harness.coding_loop.Runtime.apply`, the ONE gate -> executor -> hash-chain-log choke point every
write/edit tool call already passes through (EXT-047's hooks and EXT-048's permission rules were
both wired at this exact seam; this spec follows the same precedent). No new parallel history
store is invented: a checkpoint is a lightweight, in-memory record of one file's content
immediately before one accepted write/edit Decision, captured at the seam that is already the
system's single source of truth for "what happened." `/undo` (EXT-009) keeps working exactly as
before; `/rewind <n>` is the finer-grained superset the row asks for.

This converges PRIME-001 on three tenets at once. **Tenet 1 (two-plane discipline):** deciding
WHAT to capture is a pure, deterministic bookkeeping rule (no model judgement — every write-type
Decision gets a checkpoint, full stop), and RESTORING a file is itself a host side effect, so it
MUST go through a real `code.write_file` Decision via `Runtime.apply` — never a raw
`Path.write_text` — exactly the standing product-surface-writes-are-Decisions rule this session
reinforced. **Tenet 3 (honesty):** the ring is bounded (oldest evicted first) and reports its own
limits plainly — a checkpoint for a file that did not exist before its Decision (a creation) has
no prior content to restore, and since the toolbelt has no delete tool, `/rewind` says so honestly
rather than pretending to fully undo a file's creation; an out-of-range `/rewind <n>` is an honest
error, never a silent no-op or a fabricated success. **Tenet 5 (Claude-Code-like UX):** `/rewind
<n>` and `/checkpoints` are direct product-surface parity for row #20, giving a developer the same
finer-grained safety net Claude Code's checkpoints provide, on top of jcode's existing `/undo`.
