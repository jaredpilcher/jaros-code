# Implementation Tasks

### [TASK-1] Per-edit checkpoint ring, Runtime seam capture, `/rewind` + `/checkpoints`

Add `harness/checkpoint_ring.py` (bounded `CheckpointEntry`/`CheckpointRing`); wire an opt-in
`checkpoint_ring` capture into `harness.coding_loop.Runtime.apply` (the same seam EXT-047/EXT-048
extended); wire the ring into `harness.cli.JcodeCli`'s primary Runtime and add `/rewind <n>` /
`/checkpoints` REPL commands, restoring THROUGH a `code.write_file` Decision (never a raw
`Path.write_text`); flip `docs/GAP-MAP.md`/`harness/product_parity.py` row #20 to `works`.

#### Steps
1. Create `harness/checkpoint_ring.py`: `@dataclass(frozen=True) CheckpointEntry(id, decision_type,
   path, existed, before_content, source, ts)` and `CheckpointRing(maxlen=10)` backed by a
   `collections.deque(maxlen=...)`, with `record(...)`, `__len__`, `entries_oldest_first()`,
   `entries_newest_first()`, `by_id(checkpoint_id)`, `position_from_newest(checkpoint_id)`,
   `last_n(n)`, `drop_last_n(n)`.
2. In `harness/coding_loop.py`: add an optional `checkpoint_ring: "object | None" = None` parameter
   to `Runtime.__init__` (stored `self._checkpoint_ring`). In `apply()`, immediately before
   `outcome = executor.apply(...)`: if `self._checkpoint_ring is not None` and `decision.type` is
   in the existing `_ROOT_JAILED_DECISION_TYPES` set and `decision.payload` has a string `path`,
   read that path's current content (`os.path.isfile` + `Path.read_text`, defensive `try/except`)
   as the pre-edit snapshot. After `outcome.applied` is confirmed `True` (and the existing
   `_TOOL_USAGE`/`_WIRING_USAGE` bookkeeping), record the captured snapshot into
   `self._checkpoint_ring` via `.record(...)`.
3. In `harness/cli.py`: `JcodeCli.__init__` constructs `self._checkpoint_ring = CheckpointRing()`
   and passes `checkpoint_ring=self._checkpoint_ring` into `self.rt = Runtime(...)`'s construction.
   Add `cmd_checkpoints(self, _arg)` (lists the ring newest-first: position/type/path/existed/age,
   or an honest empty message) and `cmd_rewind(self, arg)`:
   - no `arg` -> delegates to `cmd_checkpoints`.
   - `arg` parseable as a positive integer `N` -> steps-back count.
   - otherwise -> resolve `arg` as a checkpoint id via `self._checkpoint_ring.position_from_newest`;
     unknown id -> an honest error, never a crash.
   - validate the resolved `N` is within `[1, len(ring)]`; out of range (including an empty ring)
     -> an honest error message, no side effect.
   - for each of `self._checkpoint_ring.last_n(N)` (newest first): if `entry.existed`, build a
     `code.write_file` Decision (`{"path": entry.path, "content": entry.before_content}`) and apply
     it via `self._write_runtime().apply(decision)` (mirroring `cmd_init`'s `runtime=code.write_file`
     idiom) — catch a gate/executor `RuntimeError` and report it honestly per-file rather than
     aborting the whole rewind; if `not entry.existed`, skip the write and report that the creation
     cannot be fully undone (no delete tool).
   - on completion, `self._checkpoint_ring.drop_last_n(N)`.
   - Document `/rewind <n>` and `/checkpoints` in the module docstring's command list (near the
     existing `/undo`/`/diff` lines).
4. Update `harness/product_parity.py` row `id=20` (Fine-grained checkpoint / rewind): flip `state`
   to `"works"`; `current_state` names what is genuinely delivered (bounded per-edit checkpoint
   ring captured at the `Runtime.apply` hash-chain seam, `/checkpoints`, `/rewind <n>`/`/rewind
   <id>` restoring through a real `code.write_file` Decision) and what remains deferred (the ring is
   wired only into the CLI's primary Runtime, not every internal `Runtime()` construction site so
   `/agent`'s own edits aren't yet ring-tracked; no delete-file Decision type, so a file's CREATION
   cannot be fully undone; conversation-level rewind out of scope); `next_lever` names only that
   residual gap. Mirror the same honest update into `docs/GAP-MAP.md` row #20's
   `State`/`Current honest state`/`Next lever` columns.
5. Update `tests/test_ext041_product_parity.py`: add `20` to the `works == [...]` pin (kept
   sorted) and update `n_total`/`n_works` (and the derived `n_partial + n_missing`) assertions to
   match the new works-count.
6. Write `tests/test_ext049_checkpoint.py` (deterministic, no live gemma): `CheckpointRing`
   bounds/eviction (recording past `maxlen` drops the oldest); `Runtime.apply` populating exactly
   one entry per accepted write/edit Decision, with the correct pre-edit `before_content`/`existed`,
   and NOT populating one for a rejected Decision or a read-only type; `/rewind <n>` restoring
   prior content THROUGH a `code.write_file` Decision (assert the Decision/gate path fired — e.g.
   via the hash-chain `DecisionLog` or a Runtime spy — not just that the bytes on disk changed);
   `/rewind` on an out-of-range `n` (including an empty ring) returning an honest error and making
   no filesystem change; `/undo` (EXT-009) still works unaffected by this spec; the EXT-037
   path-jail still refuses a restore whose path would escape the project root; a no-checkpoints
   state (`/checkpoints`/`/rewind` on a fresh CLI) being a clean, non-raising no-op.

#### Implements
- [REQ-1] `CheckpointEntry` / `CheckpointRing` — bounded per-edit checkpoint bookkeeping
- [REQ-2] Runtime.apply captures a pre-edit checkpoint at the existing hash-chain seam
- [REQ-3] `/rewind <n>` and `/checkpoints` — restore THROUGH a `code.write_file` Decision
- [REQ-4] Honest Product-Parity Checklist update
