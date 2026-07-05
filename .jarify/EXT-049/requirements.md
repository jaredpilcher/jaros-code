---
id: EXT-049
title: Fine-grained checkpoint / rewind
status: covered
priority: medium
---

# EXT-049 — Fine-grained checkpoint / rewind

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #20 — a bounded per-edit
checkpoint ring, keyed to the same `harness.coding_loop.Runtime.apply` seam that already
hash-chain-logs every accepted Decision (EXT-047/EXT-048's seam), plus `/rewind <n>` and
`/checkpoints` REPL commands. Extends, does not replace, the existing whole-run checkpoint +
`/undo` (EXT-009 REQ-7).

### [REQ-1] `CheckpointEntry` / `CheckpointRing` — bounded per-edit checkpoint bookkeeping

A new deterministic module `harness/checkpoint_ring.py` defines an immutable `CheckpointEntry`
(one file's content immediately before one accepted write/edit Decision) and a bounded
`CheckpointRing` that records entries in a fixed-size ring (oldest evicted first once full).

#### Acceptance Criteria
- [x] `CheckpointEntry` carries `id` (a short unique string), `decision_type`, `path`, `existed`
      (bool — did `path` exist before this Decision), `before_content` (`str | None`, only
      meaningful when `existed` is `True`), `source`, and a timestamp.
- [x] `CheckpointRing(maxlen=10)` (default 10) exposes `record(...)`, `__len__`,
      `entries_oldest_first()`, `entries_newest_first()`, `by_id(checkpoint_id)`,
      `position_from_newest(checkpoint_id)` (1 = most recent, `None` if not found), `last_n(n)`
      (the `n` most recent entries, NEWEST FIRST), and `drop_last_n(n)` (consumes/removes them).
- [x] Recording more than `maxlen` entries evicts the OLDEST entry first (a `collections.deque`
      with `maxlen` or equivalent) — the ring never grows unbounded.
- [x] `by_id`/`position_from_newest` accept either an exact id or a unique id PREFIX (short-id
      convenience), returning `None`/`None` on no match rather than raising.

### [REQ-2] Runtime.apply captures a pre-edit checkpoint at the existing hash-chain seam

`harness.coding_loop.Runtime.__init__` gains an optional `checkpoint_ring` parameter (default
`None`). When set, `Runtime.apply` captures the PRE-EDIT content of the file a write/edit Decision
(`code.write_file`, `code.apply_patch`, `code.search_replace`) is about to change, and — only after
the Decision is genuinely accepted (`outcome.applied`) — records it into the ring.

#### Acceptance Criteria
- [x] `Runtime(checkpoint_ring=None)` (the default) is a complete no-op — behaves byte-identically
      to every pre-EXT-049 caller (`_git_tool`, `_write_runtime`, every existing test).
- [x] With a `checkpoint_ring` supplied, an accepted `code.write_file`/`code.apply_patch`/
      `code.search_replace` Decision whose payload has a `path` string produces exactly ONE new
      `CheckpointEntry` in the ring, carrying the file's content as it was IMMEDIATELY BEFORE this
      Decision executed (or `existed=False, before_content=None` if the file did not exist yet).
- [x] A Decision the hard gate REJECTS (`validate_decision` fails, or the executor refuses) never
      produces a checkpoint entry — only genuinely accepted Decisions are recorded.
- [x] Capturing the pre-edit content is a plain file READ (`Path.read_text`/`os.path.isfile`), not
      a gated Decision — reads are not the side effect this spec's Decision-routing rule applies to
      (only the RESTORE write, in REQ-3, is).
- [x] A read-only Decision type (e.g. `fs.read`) or a write Decision with no `path` key in its
      payload never produces a checkpoint entry, and never raises even if `checkpoint_ring` is set.

### [REQ-3] `/rewind <n>` and `/checkpoints` — restore THROUGH a `code.write_file` Decision

`JcodeCli` wires a `CheckpointRing` into its primary Runtime (`self.rt`) and exposes
`/checkpoints` (list the ring) and `/rewind <n>` (restore the workspace `n` steps back, or to a
specific checkpoint id). The restore write is dispatched as a real `code.write_file` Decision via
`Runtime.apply` (through `self._write_runtime()`) — NEVER a raw `Path.write_text`.

#### Acceptance Criteria
- [x] `JcodeCli.__init__` constructs `self._checkpoint_ring = CheckpointRing()` and passes
      `checkpoint_ring=self._checkpoint_ring` into `self.rt`'s `Runtime(...)` construction, so
      edits made via `self.rt` (e.g. `/patch`) populate the ring.
- [x] `cmd_checkpoints(_arg)` lists every ring entry (newest first: 1-indexed position, decision
      type, path, `existed`/created, age) or an honest "no checkpoints yet" message when empty.
- [x] `cmd_rewind(arg)` with no argument returns the SAME listing as `cmd_checkpoints`.
- [x] `cmd_rewind("<integer N>")`: restores the last `N` ring entries (processed newest-first). For
      each entry with `existed=True`, the restore is a `code.write_file` Decision
      (`{"path": entry.path, "content": entry.before_content}`) applied via
      `self._write_runtime().apply(...)` — proven by a test that asserts the Decision path is used
      (e.g. via a spy/hash-chain-log assertion), not merely that the file's bytes changed. For an
      entry with `existed=False` (this Decision CREATED the file), the restore honestly reports
      that the creation cannot be fully undone (no delete tool) and leaves the file as-is — no
      fabricated success.
- [x] `cmd_rewind("<n>")` with `n` outside `[1, len(ring)]` (including `n=0`, negative, or the ring
      empty) returns an honest error message — never raises, never silently no-ops as success.
- [x] `cmd_rewind("<checkpoint-id>")` (a non-integer argument): resolves the id (exact or prefix)
      via `position_from_newest`, then behaves exactly as `cmd_rewind("<that position>")`; an
      unknown id is an honest error.
- [x] After a successful `cmd_rewind`, the restored entries are consumed (`drop_last_n`) so a
      subsequent `/rewind 1` steps further back rather than redoing the same restore.
- [x] A restore whose path would escape the project root (EXT-037 path-jail) is refused by the
      gate exactly like any other write Decision — the rejection is reported honestly, not
      swallowed.
- [x] `/undo` and `/diff` (EXT-009 REQ-7) are UNCHANGED and continue to work exactly as before —
      `self._agent_snapshot`-based whole-run undo is untouched by this spec.
- [x] `/help`'s command list documents `/rewind <n>` and `/checkpoints`.

### [REQ-4] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=20` (Fine-grained checkpoint / rewind) is flipped to `"works"`
ONLY because the checkpoint ring, `/rewind`, and `/checkpoints` are genuinely delivered and
test-covered; `current_state` honestly names what is delivered and what remains deferred (the ring
is wired only into the CLI's primary Runtime, not every internal `Runtime()` construction site;
creation cannot be fully undone since there is no delete-file Decision type; this spec covers CODE
checkpoints only, not conversation rewind). `docs/GAP-MAP.md` row #20 is updated to match.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=20` `state` is `"works"`, with `current_state` naming
      exactly what is delivered and what remains deferred, and `next_lever` naming only the
      residual gap.
- [x] `docs/GAP-MAP.md` row #20's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [x] `tests/test_ext041_product_parity.py`'s `works == [...]` pin and the `n_works`/aggregate-
      bound assertions include row #20 (if that test asserts a specific set/count).
