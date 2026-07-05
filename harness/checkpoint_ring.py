"""Fine-grained checkpoint / rewind (EXT-049).

Extends the existing WHOLE-RUN checkpoint (EXT-009 REQ-7: `/agent` snapshots the repo once before
it starts; `/undo` restores that one snapshot) with a bounded RING of PER-EDIT checkpoints -- one
entry per accepted write/edit Decision, captured at the same `harness.coding_loop.Runtime.apply`
seam that already logs every accepted Decision to the Jaros hash-chain (`record_decision`). This
module is pure, deterministic, in-memory bookkeeping (Tenet 1: two-plane discipline) -- no model
call, no new Decision type, no disk I/O of its own. The one genuine host effect a rewind performs
(restoring a file's prior content) is dispatched elsewhere, through a real `code.write_file`
Decision via `Runtime.apply` (see `harness.cli.JcodeCli.cmd_rewind`) -- never a raw
`Path.write_text` here.

`/undo` (EXT-009) is completely unaffected by this module; `/rewind` is the finer-grained
superset described in EXT-049 REQ-2/3.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field


# #EXT-049-REQ-1 Start
@dataclass(frozen=True)
class CheckpointEntry:
    """One ring entry: the content of a SINGLE file immediately BEFORE an accepted write/edit
    Decision was applied to it.

    ``existed`` is False when the Decision CREATED ``path`` (it did not exist before) -- in that
    case ``before_content`` is None (there is no prior content to restore to; the toolbelt has no
    delete-file Decision type, so a creation cannot be fully undone -- see EXT-049 design.md).
    """

    id: str
    decision_type: str
    path: str
    existed: bool
    before_content: "str | None"
    source: str = ""
    ts: float = field(default_factory=time.time)

    def summary(self) -> str:
        age = max(0.0, time.time() - self.ts)
        state = "existed" if self.existed else "newly created"
        return f"{self.decision_type} {self.path} ({state}, {age:.0f}s ago)"


class CheckpointRing:
    """Bounded ring of `CheckpointEntry` (default last 10) -- the OLDEST entry is evicted first
    once the ring is full. A deliberate, documented limit (Tenet 3: never silently unbounded), not
    a bug."""

    def __init__(self, maxlen: int = 10) -> None:
        self._d: "deque[CheckpointEntry]" = deque(maxlen=maxlen)

    def __len__(self) -> int:
        return len(self._d)

    @property
    def maxlen(self) -> int:
        return self._d.maxlen

    def record(self, decision_type: str, path: str, existed: bool,
               before_content: "str | None", source: str = "") -> CheckpointEntry:
        """Append a new checkpoint entry (evicting the oldest if the ring is already full)."""
        entry = CheckpointEntry(
            id=uuid.uuid4().hex[:8], decision_type=decision_type, path=path,
            existed=existed, before_content=before_content, source=source)
        self._d.append(entry)
        return entry

    def entries_oldest_first(self) -> "list[CheckpointEntry]":
        return list(self._d)

    def entries_newest_first(self) -> "list[CheckpointEntry]":
        return list(reversed(self._d))

    def by_id(self, checkpoint_id: str) -> "CheckpointEntry | None":
        """Exact match first, then a unique short-id PREFIX match; `None` on no match."""
        if not checkpoint_id:
            return None
        for e in self._d:
            if e.id == checkpoint_id:
                return e
        for e in self._d:
            if e.id.startswith(checkpoint_id):
                return e
        return None

    def position_from_newest(self, checkpoint_id: str) -> "int | None":
        """1-indexed steps-back position of a checkpoint id (1 = most recent), or `None` if the id
        (exact or unique prefix) is not found in the ring."""
        entry = self.by_id(checkpoint_id)
        if entry is None:
            return None
        for i, e in enumerate(self.entries_newest_first(), start=1):
            if e.id == entry.id:
                return i
        return None

    def last_n(self, n: int) -> "list[CheckpointEntry]":
        """The `n` most recent entries, NEWEST FIRST -- so restoring them in this order undoes
        the latest edit first, then the one before it, etc."""
        if n <= 0:
            return []
        return self.entries_newest_first()[:n]

    def drop_last_n(self, n: int) -> None:
        """Consume (remove) the `n` most recent entries -- called after a successful rewind so a
        repeated `/rewind` steps further back rather than redoing the same entries."""
        for _ in range(min(max(n, 0), len(self._d))):
            self._d.pop()
# #EXT-049-REQ-1 End
