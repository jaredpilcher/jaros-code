# EXT-049 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #20 names Claude Code's fine-grained checkpoint /
rewind surface: an automatic checkpoint before EACH edit, and a `/rewind <n>` that can step back
any number of edits, not just the single most-recent one. jaros-code already has a WHOLE-RUN
checkpoint (EXT-009 REQ-7): `/agent` takes one `_snapshot(".")` before it starts and `/undo`
restores it. That mechanism is coarse (one snapshot per `/agent` invocation, restored via a raw
`Path.write_text` in `harness/multi_file.py::_restore`) and gives no visibility into individual
edits.

The fix must not build a second, competing history store. It must reuse the ONE seam that already
makes every accepted Decision durable — `harness.coding_loop.Runtime.apply` (gate -> executor ->
`record_decision` onto the hash-chain `DecisionLog`) — the same seam EXT-047 (hooks) and EXT-048
(permission rules) already extended additively. And because a checkpoint RESTORE is itself a
host-project file write, it must be performed through a real `code.write_file` Decision via
`Runtime.apply`, never a raw `Path.write_text` (the standing product-surface-writes-are-Decisions
rule) — mirroring `harness/jcode_md.py::init_jcode_md`'s `runtime=code.write_file` idiom.

## Mechanism

```
  RUNTIME.APPLY SEAM (harness/coding_loop.py -- EXISTING, additively extended)
  +-------------------------------------------------------------------------------------+
  | apply(decision):                                                                     |
  |   [root-jail stamp -- EXT-037, unchanged]                                            |
  |   [plan-mode withholding -- EXT-048, unchanged]                                      |
  |   [PreToolUse hooks -- EXT-047, unchanged]                                            |
  |   gated = validate_decision(decision)          <- THE HARD GATE, unchanged           |
  |   if not gated.ok: raise RuntimeError(...)                                           |
  |   [permission-rule check -- EXT-048, unchanged]                                      |
  |                                                                                       |
  |   # #EXT-049-REQ-1: capture the PRE-EDIT content of the file this Decision is about   |
  |   # to change -- a plain READ (not a gated side effect), a no-op unless a             |
  |   # `checkpoint_ring` was supplied to this Runtime (default None).                    |
  |   if self._checkpoint_ring and decision.type in _ROOT_JAILED_DECISION_TYPES:          |
  |     path = decision.payload.get("path")                                              |
  |     existed = os.path.isfile(path); before = read(path) if existed else None         |
  |                                                                                       |
  |   outcome = executor.apply(decision, on_accept=record_decision, log=...)  <- unchanged|
  |   if outcome.applied and <captured above>:                                            |
  |     self._checkpoint_ring.record(decision.type, path, existed, before, decision.source)|
  |   [PostToolUse hooks -- EXT-047, unchanged]                                            |
  +--------------------------------------+----------------------------------------------+
                                           ^
                                           | an opt-in `checkpoint_ring` object, wired ONLY into
                                           | the CLI's primary Runtime (`self.rt`) so direct
                                           | edit commands (`/patch`, ...) populate it
  CHECKPOINT RING (harness/checkpoint_ring.py -- NEW module, pure in-memory bookkeeping)
  +-------------------------------------------------------------------------------------+
  | CheckpointEntry(id, decision_type, path, existed, before_content, source, ts)        |
  | CheckpointRing(maxlen=10):                                                          |
  |   record(...) -> CheckpointEntry     (append; oldest evicted once full)             |
  |   entries_newest_first() / entries_oldest_first()                                    |
  |   by_id(id) / position_from_newest(id)   (1 = most recent)                          |
  |   last_n(n)         -> the n most recent entries, NEWEST FIRST                        |
  |   drop_last_n(n)    -> consume them (a repeated /rewind steps further back)          |
  +--------------------------------------+----------------------------------------------+
                                           | consulted by:
                                           v
  CLI (harness/cli.py::JcodeCli)
  +-------------------------------------------------------------------------------------+
  | __init__: self._checkpoint_ring = CheckpointRing()                                   |
  |           self.rt = Runtime(..., checkpoint_ring=self._checkpoint_ring)              |
  |                                                                                       |
  | cmd_checkpoints(_arg): lists the ring, newest first, index/type/path/existed/age      |
  |                                                                                       |
  | cmd_rewind(arg):                                                                     |
  |   no arg              -> same listing as cmd_checkpoints                              |
  |   integer N           -> steps-back count                                            |
  |   else                -> treat as a checkpoint id -> position_from_newest(id)         |
  |   out of range [1, len(ring)] -> an HONEST error, never a silent no-op                |
  |   for each of the last N entries (newest first):                                     |
  |     existed=True  -> code.write_file Decision {path, content: before_content}         |
  |                      applied via self._write_runtime()  <- REAL Decision, gated,      |
  |                      root-jailed (EXT-037), hash-chain-logged -- NEVER raw write_text |
  |     existed=False -> cannot un-create (no delete tool) -- reported honestly, left     |
  |                      as-is (Tenet 3: no fabricated success)                           |
  |   drop_last_n(N) on the ring afterward (consumed)                                     |
  |                                                                                       |
  | cmd_undo / cmd_diff (EXT-009) -- UNTOUCHED, still keyed off self._agent_snapshot       |
  +-------------------------------------------------------------------------------------+
```

- **No new reasoning mechanism.** Deciding what to capture is unconditional bookkeeping tied to
  Decision TYPE (the existing `_ROOT_JAILED_DECISION_TYPES` set: `code.write_file`,
  `code.apply_patch`, `code.search_replace`) — never a model judgement.
- **The capture is a plain read, not a gated effect** (Tenet 1's rule is about HOST WRITES; a
  `Path.read_text` to remember prior content changes nothing on disk). The RESTORE, by contrast,
  is a write and therefore goes through `Runtime.apply` via a real `code.write_file` Decision,
  inheriting the hard gate, EXT-037's root-jail, and the hash-chain log for free.
- **Bounded + evicting.** `CheckpointRing(maxlen=10)` (a `collections.deque`) keeps memory bounded;
  the oldest entry is silently dropped once the ring is full — a deliberate, documented limit, not
  a bug.
- **Opt-in, backward compatible.** `Runtime.__init__`'s new `checkpoint_ring` parameter defaults to
  `None` — every existing caller (`_git_tool`, `_write_runtime`, every pre-EXT-049 test) behaves
  byte-identically; only `JcodeCli.self.rt` (the Runtime backing direct edit commands like
  `/patch`) is wired with a ring.
- **Honest about its own limits.** A checkpoint whose Decision CREATED a file (`existed=False`) has
  no prior content to restore to; since the toolbelt has no delete tool, `/rewind` reports this
  plainly instead of silently doing nothing or fabricating a delete.
- **`/undo` (EXT-009) is completely unaffected** — it still uses `self._agent_snapshot` /
  `harness.multi_file._restore` exactly as before; `/rewind` is an additional, finer-grained
  capability, not a replacement.

## Two-plane / honesty

`harness/checkpoint_ring.py` is pure deterministic execution-plane bookkeeping (Tenet 1): no LLM
call, no new Decision TYPE. The one genuinely new host effect — restoring a file's prior content —
is dispatched as a real `code.write_file` Decision through `Runtime.apply` (via
`JcodeCli._write_runtime()`, the same root-anchored-Runtime helper `cmd_init`/`cmd_remember`
already use), so it is gated, root-jailed, and hash-chain-logged exactly like every other
product-surface write. Per Tenet 3, `harness/product_parity.py` row `id=20` is flipped to `"works"`
only because the ring, `/rewind`, and `/checkpoints` are genuinely delivered and test-covered;
`current_state` honestly names the one residual limit (creation cannot be fully undone — no delete
tool) rather than hiding it.

## Backward compatibility (no regression)

- `Runtime.__init__`'s new `checkpoint_ring` parameter defaults to `None` — every existing call
  site that doesn't pass it (every pre-EXT-049 test, `_git_tool`, `_write_runtime`) is byte-
  identical: the new capture code in `apply()` is only reachable
  `if self._checkpoint_ring is not None`.
- `/undo` and `/diff` (EXT-009) are not modified in this spec.
- A fresh `JcodeCli` with zero edits made yields an empty ring — `/checkpoints` and `/rewind`
  degrade to an honest "nothing to rewind yet" message, never an exception.

## Out of scope (this task)

Restoring across an ENTIRE conversation (Claude Code's "rewind conversation" mode) — this spec
covers CODE checkpoints only, matching EXT-009's existing code-only `/undo`; wiring the ring into
every internal `Runtime()` construction site (`spec_loop.py`, `intent_loop.py`, ...) so `/agent`'s
internal edits also populate the fine-grained ring — `/agent` keeps its existing whole-run
`/undo` snapshot, and wiring the ring more broadly is a natural next lever, named honestly in
`docs/GAP-MAP.md` rather than silently left out; a delete-file Decision type (would let `/rewind`
fully undo a file creation) — not built this spec, named as the residual gap.
