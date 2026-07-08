"""EXT-056 REQ-1 (TASK-1 + TASK-2): the ADT differential oracle core, wired into build acceptance.

**The gap this closes (Tenet 1/3):** ``bestofk_generality_measure.py`` / the roadmap evidence
behind EXT-056 measured best-of-k as net-negative on the creation suite because selection
early-exits on a self-derived acceptance proxy that is BLIND to semantic-ordering (dequeue order,
LRU eviction order, TTL expiry). A built system can print plausible-looking output on every command
and still be semantically WRONG in exactly the way an eviction/ordering bug manifests -- and no
check that only asks "did it crash" or "does stdout contain a substring" can ever catch that. This
module closes that gap the same way ``harness/datastore_oracle.py`` (EXT-039 REQ-1) closes the
hollow-persistence gap: by NEVER trusting the built CLI's own stdout in isolation, instead driving a
deterministic, seeded operation sequence through BOTH an independently-authored textbook reference
model and the built CLI, and reporting the first point where they disagree as a concrete, localized
witness.

Four deterministic stages, pure stdlib, **NO model call anywhere**:

  1. ``classify(spec, mods)`` -- fingerprint method/command names + spec keywords against a table
     for ``lru`` / ``priority-queue`` / ``ttl-store`` / ``fifo`` / ``ring-buffer``; returns exactly
     one id when unambiguous, else ``None`` (a non-ADT build is a clean no-op).
  2. a reference model (``_lru_reference`` -- the beachhead ADT this task builds; the other four are
     future tasks) authored ONLY from the VISIBLE, declared LRU contract -- e.g. the
     ``lru-cache-cli`` convention already used elsewhere in this codebase
     (``harness/system_suite.py``'s ``HARDER_SLICE``: ``python main.py <capacity>``, then
     ``put <key> <value>`` -> ``ok`` / ``get <key>`` -> value or ``none``, one command per stdin
     line) -- NEVER from any eval's hidden test (Tenet 3, no oracle leak).
  3. ``_seeded_ops`` -- a ``random.Random(seed)``-driven (never the global RNG) op sequence that
     stresses LRU boundaries: capacity eviction, re-access reordering, repeated keys, misses. The
     same seed always reproduces the identical sequence (byte-replayable).
  4. ``verify`` -- applies every op to the reference model AND drives the built CLI (routed through
     the existing sandboxed, scrubbed-environment runner ``harness.system_suite._run_cli`` -- reused,
     never reimplemented) and compares the two op-by-op. On the FIRST disagreement it stops and
     returns the op index, op name + args, expected value, and actual value as the localized
     witness. All ops agreeing is an honest ``ok=True``.

**NEVER RAISES**, mirroring ``datastore_oracle.py``'s discipline exactly: any internal error
(unclassifiable/unsupported ADT class, a missing entrypoint, a crashing CLI, a malformed argument)
is always an honest ``_inconclusive`` result (``applicable=False, ok=True``) -- a pure no-op, never a
fabricated failure and never an uncaught exception.

**TASK-2 additions (this same module):** a shared ``_build_sequence`` helper (the sequence-building
block `verify` already used, factored out so it has exactly ONE implementation); a CONSERVATIVE
``classify_confident`` that only returns a class when the spec text itself named the ADT (never on
method-token overlap alone -- avoids a false-not-done on an ordinary get/put store); and
``acceptance_check``, which bakes the SAME seeded command lines + reference-model-computed expected
values into a standalone script for ``harness.system_builder``'s deterministic acceptance minimum
(composed by UNION -- see ``_minimum_acceptance`` / ``_compose_acceptance_checklist`` -- so it can
only ever ADD a way to fail, never manufacture a false pass).

**TASK-4 additions (this same module):** a second reference model, ``_priority_queue_reference``
(``heapq`` + a monotonic insertion counter for stable tie-break), plus a ``priority-queue``-specific
seeded-op generator wired into the existing ``_seeded_ops`` / ``_build_sequence`` dispatch and the
existing ``verify`` / ``acceptance_check`` drive paths -- so the oracle now checks a SECOND ADT
class (unblocking held-out validation on ``{lru, priority-queue}`` while ``{ttl-store,
ring-buffer}`` stay held out). The driving CLI convention for ``priority-queue`` (authored ONLY
from the visible push/pop/peek contract, never a hidden test): invoked as ``python <entry>`` (no
extra argv, unlike LRU's ``<capacity>``), then one command per stdin line -- ``push <priority>
<item>`` -> ``ok``; ``pop`` -> the highest-priority item (numerically SMALLEST priority value wins,
ties broken by insertion order / stable FIFO-among-ties) or ``none`` on empty; ``peek`` -> the same
value ``pop`` would return, without removing it, or ``none`` on empty. The LRU reference/drive path
is completely unchanged by this addition.

**TASK-5 additions (this same module):** a THIRD reference model, ``_ttl_store_reference`` -- a
plain ``dict`` of ``key -> (value, expiry_tick)`` plus a VIRTUAL clock ``now`` (an integer op
counter) that advances ONLY via an explicit ``tick`` op -- NEVER ``time.time()`` / ``sleep`` -- so a
seeded ttl-store run is byte-replayable exactly like the LRU/priority-queue paths. Wired into the
existing ``_seeded_ops`` / ``_build_sequence`` dispatch and the existing ``verify`` /
``acceptance_check`` drive paths -- the oracle now checks a THIRD ADT class. The driving CLI
convention for ``ttl-store`` (authored ONLY from the visible set/get/ttl contract, matching the
existing ``kv-store-ttl-cli`` task's command grammar in ``harness/system_suite.py``, extended with
the explicit virtual-clock ``tick`` op that grammar has no equivalent for): invoked as
``python <entry>`` (no extra argv, like priority-queue), then one command per stdin line --
``set <key> <value> <ttl>`` -> ``ok`` (stores ``value`` under ``key`` with expiry tick
``now + ttl``; ``ttl=0`` means already-expired, matching the ``kv-store-ttl-cli`` convention's
immediate-expiry boundary -- no special-casing needed since ``now < now + 0`` is simply False);
``get <key>`` -> the stored value if ``now < expiry`` else ``none`` (absent or expired); ``tick`` ->
``ok`` (advances the virtual clock by exactly one step -- the ONLY way ``now`` ever advances). The
LRU and priority-queue reference/drive paths are completely unchanged by this addition.

**TASK-6 additions (this same module):** a FOURTH reference model, ``_ring_buffer_reference`` -- a
``collections.deque(maxlen=capacity)``-backed textbook fixed-capacity circular buffer, authored
ONLY from the visible push/pop/peek contract (never a hidden test): ``push(item)`` appends ``item``;
once the buffer holds ``capacity`` items, the NEXT ``push`` OVERWRITES the single OLDEST item
(wrap-around) -- exactly what ``deque(maxlen=...).append`` already does, so this reference needed no
extra bookkeeping to get wrap-around right. Wired into the existing ``_seeded_ops`` /
``_build_sequence`` dispatch and the existing ``verify`` / ``acceptance_check`` drive paths -- the
oracle now checks a FOURTH ADT class, completing the 4 canonical ADTs this module set out to cover.
The driving CLI convention for ``ring-buffer`` (authored ONLY from the visible push/pop/peek
contract, mirroring LRU's ``<capacity>`` argv convention rather than priority-queue/ttl-store's
no-argv convention, since a ring buffer -- like LRU -- is inherently capacity-bounded): invoked as
``python <entry> <capacity>``, then one command per stdin line -- ``push <item>`` -> ``ok``; ``pop``
-> the oldest item (FIFO order), removing it, or ``none`` on empty; ``peek`` -> the same oldest item
WITHOUT removing it, or ``none`` on empty. The LRU/priority-queue/ttl-store reference/drive paths are
completely unchanged by this addition.

**Not done here (future tasks, see ``.jarify/EXT-056/design.md``):** a reference model for ``fifo``.
"""

from __future__ import annotations

import heapq
import random
import re
import sys
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# #EXT-056-REQ-1 Start
# TASK-1: reuse (not reimplement) the existing sandboxed, scrubbed-environment CLI runner every
# other black-box/differential check in this codebase already goes through (EXT-037/REQ-7).
from harness.system_suite import _run_cli

SUPPORTED_CLASSES = ("lru", "priority-queue", "ttl-store", "fifo", "ring-buffer")

# Classes this module has actually built a reference model + seeded-op generator + CLI convention
# for: "lru" (TASK-1), "priority-queue" (TASK-4), "ttl-store" (TASK-5), and "ring-buffer" (TASK-6).
# The remaining id in SUPPORTED_CLASSES ("fifo") is recognized by `classify` (so a build can be
# correctly fingerprinted) but `verify` honestly reports it as inconclusive until a later task adds
# its reference model -- never a fabricated pass/fail for a class this module cannot yet check.
_IMPLEMENTED_CLASSES = ("lru", "priority-queue", "ttl-store", "ring-buffer")


@dataclass
class AdtResult:
    """Result of :func:`verify`. ``applicable`` is False for a non-ADT build or any internal error
    (a pure no-op -- contributes nothing to acceptance). ``cls`` is the classified ADT id (or
    ``None``). ``ok`` is True when every seeded op agreed between the reference model and the built
    CLI (or when the oracle is inconclusive -- inconclusive is never a failure). ``first_divergence``
    is populated only when ``ok=False``, with keys ``index`` (int), ``op`` (str), ``args`` (list),
    ``expected`` (the reference model's value), and ``actual`` (the built CLI's observed value).
    ``detail`` is always a short, honest, human-readable summary."""

    applicable: bool
    cls: "str | None"
    ok: bool
    first_divergence: "dict | None"
    detail: str = ""


def _inconclusive(detail: str) -> AdtResult:
    """The single no-op result shape every internal error/unsupported-class/non-ADT path returns:
    ``applicable=False`` (adds nothing to acceptance) and ``ok=True`` (never a fabricated failure)."""
    return AdtResult(applicable=False, cls=None, ok=True, first_divergence=None, detail=detail)


# --- STAGE 1: classify -----------------------------------------------------------------------

# Spec-text keyword fingerprints per canonical ADT. Phrases (containing a space or hyphen) are
# matched as plain substrings; single tokens are matched as whole words (`\b`-bounded) so e.g. the
# token "ttl" never spuriously matches inside an unrelated longer word.
_KEYWORDS: "dict[str, tuple[str, ...]]" = {
    "lru": ("lru", "least recently used", "least-recently-used"),
    "priority-queue": ("priority queue", "priority-queue", "min-heap", "max-heap", "heapq"),
    "ttl-store": ("ttl", "time-to-live", "time to live", "expire", "expiry", "expiration"),
    "fifo": ("fifo", "first-in-first-out", "first in first out"),
    "ring-buffer": ("ring buffer", "ring-buffer", "circular buffer", "circular-buffer"),
}

# Method/command-name token fingerprints, matched (whole-word) against each entry of `mods`.
_METHOD_TOKENS: "dict[str, tuple[str, ...]]" = {
    "lru": ("get", "put", "capacity", "lru"),
    "priority-queue": ("push", "pop", "peek", "priority", "enqueue"),
    "ttl-store": ("set", "get", "expire", "ttl"),
    "fifo": ("enqueue", "dequeue", "fifo"),
    "ring-buffer": ("push", "pop", "overwrite", "ring"),
}


def _contains(haystack: str, needle: str) -> bool:
    """Whole-word match for a single token, plain substring match for a multi-word phrase. Never
    raises -- an empty/None haystack or needle is simply "not found"."""
    if not haystack or not needle:
        return False
    if " " in needle or "-" in needle:
        return needle in haystack
    try:
        return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None
    except Exception:
        return needle in haystack


def classify_confident(spec: "str", mods: "list[str] | None") -> "str | None":
    """CONSERVATIVE variant of :func:`classify` (TASK-2, REQ-1): returns a class ONLY when that
    class also scored at least one KEYWORD hit in ``spec`` (the ×2 signal -- i.e. the spec text
    EXPLICITLY names the ADT), never on method/command-token overlap alone. This is the ×2 signal
    already present in :func:`classify`'s own scoring table, promoted to a hard gate: a plain
    bounded key/value store whose spec only says "get" and "put" (with capacity) but never says
    "lru" / "least recently used" scores on method tokens alone and must NOT be classified here --
    that overlap is coincidental (many non-LRU stores also expose get/put), not evidence the build
    actually implements LRU semantics. This is the classifier the ACCEPTANCE-CHECK wiring uses
    (:func:`acceptance_check` / ``system_builder._minimum_acceptance``): under-assert rather than
    risk a false-not-done on a build that merely shares command-name tokens with an ADT. Never
    raises."""
    try:
        cls_id = classify(spec, mods)
        if not cls_id:
            return None
        text = (spec or "").lower()
        if any(_contains(text, kw) for kw in _KEYWORDS.get(cls_id, ())):
            return cls_id
        return None
    except Exception:
        return None


def classify(spec: "str", mods: "list[str] | None") -> "str | None":
    """Fingerprint ``spec`` (free text) + ``mods`` (a flat list of method/command-name strings, e.g.
    ``["get", "put", "capacity"]``) against the canonical-ADT table. Each keyword hit in ``spec``
    scores 2; each distinct method-token that appears (whole-word) in any entry of ``mods`` scores 1.
    Returns the single class with the strictly-highest score, or ``None`` when nothing matched at
    all (a non-ADT build) or the top score is tied across more than one class (an ambiguous
    fingerprint deliberately classifies to ``None`` rather than guessing). Never raises."""
    try:
        text = (spec or "").lower()
        names = [str(m).lower() for m in (mods or []) if m is not None]
        scores: "dict[str, int]" = {}
        for cls_id in SUPPORTED_CLASSES:
            score = 0
            for kw in _KEYWORDS.get(cls_id, ()):
                if _contains(text, kw):
                    score += 2
            for token in _METHOD_TOKENS.get(cls_id, ()):
                if any(_contains(name, token) for name in names):
                    score += 1
            if score > 0:
                scores[cls_id] = score
        if not scores:
            return None
        best = max(scores.values())
        winners = [c for c, s in scores.items() if s == best]
        return winners[0] if len(winners) == 1 else None
    except Exception:
        return None


# --- STAGE 2: reference model (LRU -- the beachhead ADT for TASK-1) --------------------------

class _LruReferenceModel:
    """A ~20-line ``OrderedDict``-backed textbook LRU reference, authored ONLY from the visible LRU
    contract (never from any hidden test): ``get(key)`` returns the stored value if present (and
    marks the key as most-recently-used), or ``None`` on a miss; ``put(key, value)`` inserts or
    updates ``key`` (marking it most-recently-used) and, once the cache exceeds ``capacity`` distinct
    keys, evicts the single least-recently-used entry."""

    def __init__(self, capacity: int):
        self.capacity = max(1, int(capacity))
        self._data: "OrderedDict[Any, Any]" = OrderedDict()

    def get(self, key: Any) -> Any:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: Any, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)


def _lru_reference(capacity: int) -> _LruReferenceModel:
    """Factory for a fresh :class:`_LruReferenceModel` at the given ``capacity``."""
    return _LruReferenceModel(capacity)


# --- STAGE 2b: reference model (priority-queue -- TASK-4's 2nd implemented ADT) ---------------

class _PriorityQueueReferenceModel:
    """A ``heapq``-backed textbook priority-queue reference, authored ONLY from the visible
    push/pop/peek contract (never from any hidden test): ``push(priority, item)`` inserts ``item``
    at the given ``priority``; ``pop()`` removes and returns the item with the numerically
    SMALLEST ``priority`` value (the convention used throughout this module: a SMALLER priority
    number is a HIGHER priority -- e.g. "priority 1" outranks "priority 5", the same convention
    Python's own ``heapq`` and most task-scheduler textbooks use), breaking ties between EQUAL
    priorities by INSERTION order (stable FIFO-among-ties) via a monotonic counter that only ever
    increases; ``peek()`` returns the same value ``pop()`` would return, without removing it. Both
    ``pop()`` and ``peek()`` return ``None`` on an empty queue."""

    def __init__(self):
        self._heap: "list[tuple[Any, int, Any]]" = []
        self._counter = 0

    def push(self, priority: Any, item: Any) -> None:
        heapq.heappush(self._heap, (priority, self._counter, item))
        self._counter += 1

    def pop(self) -> Any:
        if not self._heap:
            return None
        _, _, item = heapq.heappop(self._heap)
        return item

    def peek(self) -> Any:
        if not self._heap:
            return None
        _, _, item = self._heap[0]
        return item


def _priority_queue_reference() -> _PriorityQueueReferenceModel:
    """Factory for a fresh :class:`_PriorityQueueReferenceModel`."""
    return _PriorityQueueReferenceModel()


# --- STAGE 2c: reference model (ttl-store -- TASK-5's 3rd implemented ADT) --------------------

class _TtlStoreReferenceModel:
    """A ``dict``-backed textbook TTL-store reference, authored ONLY from the visible set/get/ttl
    contract (never from any hidden test): ``set(key, value, ttl)`` stores ``value`` under ``key``
    with an expiry TICK of ``now + ttl`` (a ``ttl`` of 0 means the key is ALREADY expired -- since
    ``now < now + 0`` is simply False, a ``get`` immediately after a ``ttl=0`` ``set``, with zero
    ticks advanced, honestly reports a miss with no special-casing needed, matching the
    ``kv-store-ttl-cli`` convention's immediate-expiry boundary); ``get(key)`` returns the stored
    value if ``key`` is present AND still live (``now < expiry``), else ``None`` (absent or
    expired); ``tick()`` advances the VIRTUAL clock ``now`` by exactly one step -- the ONLY way
    ``now`` ever advances (NEVER wall-clock / ``time.time()`` / ``sleep``, so a seeded op sequence
    stays byte-replayable). Overwriting an existing key via a second ``set`` REPLACES its expiry
    relative to the CURRENT ``now`` -- the ttl countdown restarts from the moment of the overwrite,
    not the original ``set``."""

    def __init__(self):
        self._data: "dict[Any, tuple[Any, int]]" = {}
        self._now = 0

    def set(self, key: Any, value: Any, ttl: int) -> None:
        self._data[key] = (value, self._now + max(0, int(ttl)))

    def get(self, key: Any) -> Any:
        if key not in self._data:
            return None
        value, expiry = self._data[key]
        return value if self._now < expiry else None

    def tick(self) -> None:
        self._now += 1


def _ttl_store_reference() -> _TtlStoreReferenceModel:
    """Factory for a fresh :class:`_TtlStoreReferenceModel`."""
    return _TtlStoreReferenceModel()


# --- STAGE 2d: reference model (ring-buffer -- TASK-6's 4th implemented ADT) -------------------

class _RingBufferReferenceModel:
    """A ``collections.deque(maxlen=capacity)``-backed textbook fixed-capacity circular-buffer
    reference, authored ONLY from the visible push/pop/peek contract (never a hidden test):
    ``push(item)`` appends ``item`` to the buffer; once the buffer already holds ``capacity``
    items, the NEXT ``push`` OVERWRITES the single OLDEST item (wrap-around) -- this is exactly
    ``deque(maxlen=...).append``'s own built-in behavior (appending past ``maxlen`` silently drops
    the item at the OPPOSITE end), so this reference needed no extra bookkeeping to get wrap-around
    right; ``pop()`` removes and returns the OLDEST item (FIFO order, ``popleft``), or ``None`` on
    an empty buffer; ``peek()`` returns the same oldest item WITHOUT removing it, or ``None`` on an
    empty buffer."""

    def __init__(self, capacity: int):
        self.capacity = max(1, int(capacity))
        self._data: "deque[Any]" = deque(maxlen=self.capacity)

    def push(self, item: Any) -> None:
        self._data.append(item)

    def pop(self) -> Any:
        if not self._data:
            return None
        return self._data.popleft()

    def peek(self) -> Any:
        if not self._data:
            return None
        return self._data[0]


def _ring_buffer_reference(capacity: int) -> _RingBufferReferenceModel:
    """Factory for a fresh :class:`_RingBufferReferenceModel` at the given ``capacity``."""
    return _RingBufferReferenceModel(capacity)


# --- STAGE 3: seeded, boundary-stressing op sequence ------------------------------------------

_LRU_CAPACITY = 3
_LRU_KEYS = ("a", "b", "c", "d", "e")  # more keys than capacity -> guarantees eviction pressure

# TASK-4: priority-queue seed constants. `_PQ_TIE_PRIORITY` seeds a deliberate tie-break block;
# `_PQ_PRIORITY_POOL` deliberately repeats values so ties keep recurring throughout the random
# mixing phase, not just up front.
_PQ_TIE_PRIORITY = 2
_PQ_PRIORITY_POOL = (1, 2, 2, 3, 4, 4, 5)
_PQ_ITEM_PREFIX = "item"

# TASK-5: ttl-store seed constants. `_TTL_KEY_POOL` is a small key pool reused across the random
# mixing phase (so overwrite/re-read pressure recurs); `_TTL_TTL_POOL` deliberately includes 0 (the
# immediate-expiry boundary) alongside varied positive ttls so that boundary keeps recurring
# throughout the sequence, not just in the fixed prelude.
_TTL_KEY_POOL = ("a", "b", "c", "d", "e")
_TTL_TTL_POOL = (0, 1, 1, 2, 3, 5)

# TASK-6: ring-buffer seed constants. `_RING_CAPACITY` reuses `_LRU_CAPACITY`'s value -- ring-buffer
# shares LRU's capacity-bounded `<capacity>`-argv CLI convention (unlike priority-queue/ttl-store,
# which take no extra argv), so `acceptance_check`'s single `capacity` default parameter (not
# per-class) stays correct for both without any extra plumbing. `_RING_ITEM_PREFIX` names the
# synthetic items `push`ed during the seeded sequence.
_RING_CAPACITY = _LRU_CAPACITY
_RING_ITEM_PREFIX = "r"


def _pq_seeded_ops(seed: int, n: int) -> "list[tuple[str, tuple]]":
    """Deterministic, boundary-stressing op sequence for ``priority-queue`` (TASK-4), generated
    with ``random.Random(seed)`` (NEVER the global RNG) so the same ``seed`` always reproduces the
    byte-identical sequence. Stresses three boundaries: (1) TIE-BREAK ordering -- three ``push``es
    at the SAME priority up front, immediately followed by a ``peek`` and a ``pop``, so a broken
    stable-FIFO-among-ties implementation is caught before any later random mixing could mask it;
    (2) varied priorities (including further ties drawn from ``_PQ_PRIORITY_POOL``) mixed with
    ``push``/``pop``/``peek`` at random; (3) the EMPTY-queue boundary -- the sequence always ends
    by draining the queue completely and then issuing one more ``pop`` and one more ``peek``
    against the now-empty queue (both must yield ``None``)."""
    rng = random.Random(seed)
    ops: "list[tuple[str, tuple]]" = []
    size = 0
    item_idx = 0

    def _push(priority: int) -> None:
        nonlocal item_idx, size
        item = f"{_PQ_ITEM_PREFIX}{item_idx}"
        item_idx += 1
        size += 1
        ops.append(("push", (priority, item)))

    def _pop() -> None:
        nonlocal size
        if size > 0:
            size -= 1
        ops.append(("pop", ()))

    def _peek() -> None:
        ops.append(("peek", ()))

    # (1) deliberate tie-break stress up front: three same-priority pushes in a fixed order, then
    # an immediate peek + pop -- both must surface the FIRST-inserted tied item, proving stable
    # FIFO-among-ties ordering before any random mixing below could mask a broken tie-break.
    for _ in range(3):
        _push(_PQ_TIE_PRIORITY)
    _peek()
    _pop()

    # (2) random mixed push/pop/peek stress across varied (and further tied) priorities.
    remaining = max(0, n - len(ops) - 2)
    for _ in range(remaining):
        roll = rng.random()
        if roll < 0.5 or size == 0:
            _push(rng.choice(_PQ_PRIORITY_POOL))
        elif roll < 0.8:
            _pop()
        else:
            _peek()

    # (3) guaranteed empty-boundary stress: drain whatever remains, then probe pop+peek on empty.
    while size > 0:
        _pop()
    _pop()
    _peek()

    return ops


def _ttl_seeded_ops(seed: int, n: int) -> "list[tuple[str, tuple]]":
    """Deterministic, boundary-stressing op sequence for ``ttl-store`` (TASK-5), generated with
    ``random.Random(seed)`` (NEVER the global RNG, and the virtual clock never touches wall-clock
    time either) so the same ``seed`` always reproduces the byte-identical sequence. Stresses four
    boundaries in a fixed prelude before any random mixing (so a broken implementation is caught
    before later ops could mask it): (1) the IMMEDIATE-EXPIRY boundary -- a ``set`` with ``ttl=0``
    followed immediately by a ``get`` with NO ``tick`` in between, which must already read as
    expired; (2) the exact-tick expiry boundary -- a ``set`` with ``ttl=1``, a ``get`` BEFORE any
    ``tick`` (must still be live), one ``tick``, then a ``get`` AFTER (must now read as expired);
    (3) OVERWRITE-RESETS-TTL -- a key is set, ticked once, then overwritten with a fresh ttl; the
    overwritten value must survive the tick that would have expired the ORIGINAL ttl, then expire
    exactly on its own new schedule; (4) a ``get`` on a key that was never set (a clean miss). The
    remainder mixes random ``set``/``get``/``tick`` ops across a small key pool with a ttl pool that
    keeps re-including ``0`` (further immediate-expiry hits throughout, not just up front)."""
    rng = random.Random(seed)
    ops: "list[tuple[str, tuple]]" = []

    # (1) immediate-expiry boundary: ttl=0 must already be expired with NO tick in between.
    ops.append(("set", ("a", "v-a0", 0)))
    ops.append(("get", ("a",)))

    # (2) alive-before / expired-after a single virtual tick, right at the expiry boundary.
    ops.append(("set", ("b", "v-b0", 1)))
    ops.append(("get", ("b",)))
    ops.append(("tick", ()))
    ops.append(("get", ("b",)))

    # (3) overwrite-resets-ttl: the countdown restarts from the CURRENT `now`, not the original
    # `set` time.
    ops.append(("set", ("c", "v-c0", 1)))
    ops.append(("tick", ()))
    ops.append(("set", ("c", "v-c1", 1)))
    ops.append(("get", ("c",)))
    ops.append(("tick", ()))
    ops.append(("get", ("c",)))

    # (4) get on a never-set key -> a clean miss.
    ops.append(("get", ("never-set",)))

    # (5) random mixed set/get/tick stress across a small key pool with a ttl pool that keeps
    # re-including 0, so the expiry boundary keeps recurring throughout the sequence.
    remaining = max(0, n - len(ops))
    for i in range(remaining):
        roll = rng.random()
        if roll < 0.45:
            key = rng.choice(_TTL_KEY_POOL)
            ttl = rng.choice(_TTL_TTL_POOL)
            ops.append(("set", (key, f"v-{key}-{i}", ttl)))
        elif roll < 0.85:
            key = rng.choice(_TTL_KEY_POOL)
            ops.append(("get", (key,)))
        else:
            ops.append(("tick", ()))

    return ops


def _ring_buffer_seeded_ops(seed: int, n: int) -> "list[tuple[str, tuple]]":
    """Deterministic, boundary-stressing op sequence for ``ring-buffer`` (TASK-6), generated with
    ``random.Random(seed)`` (NEVER the global RNG) so the same ``seed`` always reproduces the
    byte-identical sequence. Stresses four boundaries in a fixed prelude before any random mixing
    (so a broken implementation is caught before later ops could mask it): (1) FILL-TO-CAPACITY --
    exactly ``_RING_CAPACITY`` pushes, followed by a ``peek`` that must surface the very FIRST item
    pushed (the oldest); (2) WRAP-AROUND -- one more push while already at capacity, which must
    OVERWRITE the single oldest item, followed by a ``peek`` that must now surface the SECOND item
    pushed (not the first, which was just evicted, and not a stale/duplicated value) -- this is the
    single most load-bearing probe in the whole sequence, since a "wrong-wrap-order" bug (evicting
    the newest instead of the oldest, or not evicting at all) manifests as exactly this peek
    returning the wrong item; (3) DRAIN -- pop every remaining item in FIFO order; (4)
    DRAIN-PAST-EMPTY -- one more ``pop`` and one more ``peek`` against the now-empty buffer, both of
    which must yield ``None``. The remainder mixes random ``push``/``pop``/``peek`` ops, so
    wrap-around pressure keeps recurring throughout the sequence, not just in the fixed prelude."""
    rng = random.Random(seed)
    ops: "list[tuple[str, tuple]]" = []
    item_idx = 0
    size = 0  # tracks current occupancy; a push at capacity does NOT grow it further (wrap-around)

    def _push() -> None:
        nonlocal item_idx, size
        item = f"{_RING_ITEM_PREFIX}{item_idx}"
        item_idx += 1
        ops.append(("push", (item,)))
        size = min(_RING_CAPACITY, size + 1)

    def _pop() -> None:
        nonlocal size
        if size > 0:
            size -= 1
        ops.append(("pop", ()))

    def _peek() -> None:
        ops.append(("peek", ()))

    # (1) fill exactly to capacity, then peek -- must surface the FIRST item pushed (the oldest).
    for _ in range(_RING_CAPACITY):
        _push()
    _peek()

    # (2) wrap-around: one more push while already at capacity must OVERWRITE the oldest item; the
    # follow-up peek must now surface the SECOND item pushed, never the (just-evicted) first.
    _push()
    _peek()

    # (3) drain everything that remains, in FIFO order.
    while size > 0:
        _pop()

    # (4) drain-past-empty boundary: pop + peek on an empty buffer must both yield none.
    _pop()
    _peek()

    # (5) random interleaved push/pop/peek mixing, so wrap-around pressure keeps recurring.
    remaining = max(0, n - len(ops))
    for _ in range(remaining):
        roll = rng.random()
        if roll < 0.55 or size == 0:
            _push()
        elif roll < 0.8:
            _pop()
        else:
            _peek()

    return ops


def _seeded_ops(cls: str, seed: int, n: int) -> "list[tuple[str, tuple]]":
    """Deterministic op sequence for ``cls``, generated with ``random.Random(seed)`` (NEVER the
    global RNG) so the same ``seed`` always reproduces the byte-identical sequence. For ``lru``:
    first fills the cache to exactly ``_LRU_CAPACITY`` (so early ops are never vacuous misses), then
    mixes ``put``/``get`` across a key pool larger than capacity to stress capacity eviction,
    re-access reordering (a ``get`` protects a key from the next eviction), repeated keys, and
    misses (a ``get`` on an absent/evicted key). For ``priority-queue`` (TASK-4): delegates to
    :func:`_pq_seeded_ops` (tie-break, varied-priority mixing, and empty-boundary stress -- see its
    docstring). For ``ttl-store`` (TASK-5): delegates to :func:`_ttl_seeded_ops` (immediate-expiry,
    exact-tick-expiry, and overwrite-resets-ttl boundary stress, driven by an explicit VIRTUAL
    ``tick`` op -- never wall-clock -- see its docstring). For ``ring-buffer`` (TASK-6): delegates to
    :func:`_ring_buffer_seeded_ops` (fill-to-capacity, wrap-around-overwrites-the-oldest, drain, and
    drain-past-empty boundary stress -- see its docstring). Returns ``[]`` for any class this module
    has not yet built a reference model for (no fabricated sequence for an unimplemented class)."""
    if cls not in _IMPLEMENTED_CLASSES:
        return []
    if cls == "priority-queue":
        return _pq_seeded_ops(seed, n)
    if cls == "ttl-store":
        return _ttl_seeded_ops(seed, n)
    if cls == "ring-buffer":
        return _ring_buffer_seeded_ops(seed, n)
    rng = random.Random(seed)
    keys = list(_LRU_KEYS)
    ops: "list[tuple[str, tuple]]" = []
    for i in range(_LRU_CAPACITY):
        ops.append(("put", (keys[i % len(keys)], f"v{i}")))
    for i in range(max(0, n - _LRU_CAPACITY)):
        key = rng.choice(keys)
        if rng.random() < 0.5:
            ops.append(("put", (key, f"v{_LRU_CAPACITY + i}")))
        else:
            ops.append(("get", (key,)))
    return ops


def _build_sequence(cls: str, seed: int, n: int,
                     capacity: int) -> "tuple[list[str], list[str]]":
    """Shared sequence-builder (TASK-2, REQ-1): generates the seeded op sequence for ``cls`` via
    :func:`_seeded_ops`, applies every op IN ORDER to a fresh reference model (``lru`` and
    ``ring-buffer`` -- TASK-6 -- both use ``capacity``; ``priority-queue`` -- TASK-4 -- and
    ``ttl-store`` -- TASK-5 -- ignore it, the reference queue/store is unbounded), and returns
    ``(cmd_lines, expected_lines)`` -- the exact stdin command lines to drive a CLI with, and the
    reference model's expected output line for each, in the same order.
    Deterministic (same ``cls``/``seed``/``n``/``capacity`` -> byte-identical output). This is the
    ONE place the reference logic lives; both :func:`verify` (in-process differential drive) and
    :func:`acceptance_check` (bakes the same fixed lines into a standalone emitted script) call it
    -- never a second, drifting copy of the op-to-command/expected-value mapping. Returns
    ``([], [])`` for any class this module has no reference model for (never fabricates a
    sequence). Never raises internally; an unexpected op shape also yields ``([], [])`` rather than
    a partial/malformed sequence."""
    if cls not in _IMPLEMENTED_CLASSES:
        return [], []
    ops = _seeded_ops(cls, seed, n)
    if not ops:
        return [], []
    cmd_lines: "list[str]" = []
    expected_lines: "list[str]" = []
    if cls == "priority-queue":
        pq_reference = _priority_queue_reference()
        for op, args in ops:
            if op == "push":
                priority, item = args
                pq_reference.push(priority, item)
                cmd_lines.append(f"push {priority} {item}")
                expected_lines.append("ok")
            elif op == "pop":
                value = pq_reference.pop()
                cmd_lines.append("pop")
                expected_lines.append("none" if value is None else str(value))
            elif op == "peek":
                value = pq_reference.peek()
                cmd_lines.append("peek")
                expected_lines.append("none" if value is None else str(value))
            else:
                return [], []
        return cmd_lines, expected_lines
    if cls == "ttl-store":
        ttl_reference = _ttl_store_reference()
        for op, args in ops:
            if op == "set":
                key, value, ttl = args
                ttl_reference.set(key, value, ttl)
                cmd_lines.append(f"set {key} {value} {ttl}")
                expected_lines.append("ok")
            elif op == "get":
                (key,) = args
                value = ttl_reference.get(key)
                cmd_lines.append(f"get {key}")
                expected_lines.append("none" if value is None else str(value))
            elif op == "tick":
                ttl_reference.tick()
                cmd_lines.append("tick")
                expected_lines.append("ok")
            else:
                return [], []
        return cmd_lines, expected_lines
    if cls == "ring-buffer":
        ring_reference = _ring_buffer_reference(capacity)
        for op, args in ops:
            if op == "push":
                (item,) = args
                ring_reference.push(item)
                cmd_lines.append(f"push {item}")
                expected_lines.append("ok")
            elif op == "pop":
                value = ring_reference.pop()
                cmd_lines.append("pop")
                expected_lines.append("none" if value is None else str(value))
            elif op == "peek":
                value = ring_reference.peek()
                cmd_lines.append("peek")
                expected_lines.append("none" if value is None else str(value))
            else:
                return [], []
        return cmd_lines, expected_lines
    reference = _lru_reference(capacity)
    for op, args in ops:
        if op == "put":
            key, value = args
            reference.put(key, value)
            cmd_lines.append(f"put {key} {value}")
            expected_lines.append("ok")
        elif op == "get":
            (key,) = args
            value = reference.get(key)
            cmd_lines.append(f"get {key}")
            expected_lines.append("none" if value is None else str(value))
        else:
            return [], []
    return cmd_lines, expected_lines


# --- STAGE 4: differential drive + first-divergence -------------------------------------------

def verify(root: Any, entry: Any, cls: "str | None", *, seed: int = 1234,
           timeout: float = 20) -> AdtResult:
    """Build the reference model for ``cls``, generate its seeded op sequence, apply every op to
    the reference AND drive the same ops through the built CLI at ``root/entry`` (via
    ``harness.system_suite._run_cli``, sandboxed + scrubbed-environment), then compare the two
    op-by-op. On the FIRST disagreement, returns an :class:`AdtResult` with ``ok=False`` and a
    populated ``first_divergence`` (``index``/``op``/``args``/``expected``/``actual``). When every
    op agrees, returns ``ok=True``. When ``cls`` is unclassified/unsupported, or anything about the
    build/drive is malformed (missing root/entrypoint, bad seed, an unexpected exception anywhere in
    this function), returns an honest :func:`_inconclusive` result instead -- ``verify`` NEVER
    raises.

    TASK-1 implements the driving CLI convention used elsewhere in this codebase for the LRU class
    (``harness/system_suite.py``'s ``lru-cache-cli`` HARDER_SLICE task): invoked as
    ``python <entry> <capacity>``, then one command per stdin line (``put <key> <value>`` ->
    ``ok``; ``get <key>`` -> the value or ``none``), one output line per command in the same order.
    TASK-4 adds the ``priority-queue`` convention: invoked as ``python <entry>`` (no extra argv),
    then one command per stdin line (``push <priority> <item>`` -> ``ok``; ``pop`` -> the
    highest-priority item or ``none`` on empty; ``peek`` -> the same without removing it). TASK-5
    adds the ``ttl-store`` convention: invoked as ``python <entry>`` (no extra argv), then one
    command per stdin line (``set <key> <value> <ttl>`` -> ``ok``; ``get <key>`` -> the value if
    live else ``none``; ``tick`` -> ``ok``, advancing the VIRTUAL clock by exactly one step --
    NEVER wall-clock). TASK-6 adds the ``ring-buffer`` convention, mirroring LRU's capacity-bounded
    argv (unlike priority-queue/ttl-store's no-argv convention): invoked as
    ``python <entry> <capacity>``, then one command per stdin line (``push <item>`` -> ``ok``, and at
    capacity OVERWRITES the single oldest item; ``pop`` -> the oldest item, FIFO order, removing it,
    or ``none`` on empty; ``peek`` -> the same oldest item without removing it, or ``none`` on
    empty).
    """
    try:
        if not cls or cls not in _IMPLEMENTED_CLASSES:
            return _inconclusive(
                f"class {cls!r} is not yet implemented by this task (implemented: "
                f"{_IMPLEMENTED_CLASSES!r}) -- no-op, not a failure"
            )
        try:
            root_path = Path(root)
        except (TypeError, ValueError) as exc:
            return _inconclusive(f"invalid root {root!r}: {exc}")
        if not root_path.exists() or not root_path.is_dir():
            return _inconclusive(f"root does not exist: {root_path}")

        entry_name = str(entry) if entry else ""
        if not entry_name:
            return _inconclusive("no entry filename supplied")
        entry_path = root_path / entry_name
        if not entry_path.is_file():
            return _inconclusive(f"entrypoint not found: {entry_path}")

        ops = _seeded_ops(cls, seed, 24)
        if not ops:
            return _inconclusive(f"no seeded ops generated for class {cls!r}")

        # TASK-4/TASK-5/TASK-6: the LRU and ring-buffer classes both drive
        # `python <entry> <capacity>` (both are inherently capacity-bounded); priority-queue and
        # ttl-store (neither has a capacity concept) drive `python <entry>` with no extra argv.
        # `capacity` is only ever consumed by the lru/ring-buffer branches of `_build_sequence` --
        # passing it through unused for the other classes is harmless, but the CLI argv must NOT
        # include it for them.
        capacity = (_LRU_CAPACITY if cls == "lru"
                    else _RING_CAPACITY if cls == "ring-buffer" else 0)
        cli_args = ([str(_LRU_CAPACITY)] if cls == "lru"
                    else [str(_RING_CAPACITY)] if cls == "ring-buffer" else [])

        # TASK-2: sequence-building now lives in the shared `_build_sequence` helper (reused
        # verbatim by `acceptance_check` below) -- `verify` only drives + compares.
        cmd_lines, expected_lines = _build_sequence(cls, seed, 24, capacity)
        if not cmd_lines or len(cmd_lines) != len(ops):
            return _inconclusive(f"sequence build failed or mismatched for class {cls!r}")

        stdin = "\n".join(cmd_lines) + "\n"
        py_exe = sys.executable or "python"
        cli_ok, out = _run_cli(py_exe, entry_path, cli_args, stdin, root_path, timeout)
        actual_lines = out.splitlines()

        for idx, (op_args, expected) in enumerate(zip(ops, expected_lines)):
            op, args = op_args
            actual = actual_lines[idx] if idx < len(actual_lines) else None
            if actual != expected:
                detail = (f"first divergence at op[{idx}] {op}{tuple(args)!r}: expected "
                           f"{expected!r}, got {actual!r}")
                if not cli_ok:
                    detail += " (the built CLI also exited non-zero)"
                return AdtResult(
                    applicable=True, cls=cls, ok=False,
                    first_divergence={
                        "index": idx, "op": op, "args": list(args),
                        "expected": expected, "actual": actual,
                    },
                    detail=detail,
                )

        return AdtResult(
            applicable=True, cls=cls, ok=True, first_divergence=None,
            detail=f"ok: all {len(ops)} seeded {cls} ops agreed with the reference model",
        )
    except Exception as exc:  # never raise -- an honest inconclusive result instead
        return _inconclusive(f"verify failed unexpectedly: {exc}")


# --- STAGE 5: acceptance-checklist emission (TASK-2) -------------------------------------------

def acceptance_check(entry: "str", cls: "str | None", *, seed: int = 1234,
                      capacity: int = _LRU_CAPACITY) -> "dict | None":
    """Builds ONE deterministic-minimum acceptance-checklist entry (TASK-2, REQ-1) for
    ``harness.system_builder``: ``None`` when ``cls`` is not (yet) an implemented class (a clean
    no-op -- never a fabricated check for an ADT this module has no reference model for). Computes
    the seeded ``(cmd_lines, expected_lines)`` ONCE, in-process, via :func:`_build_sequence`
    (reusing the SAME tested reference model + seeded-op generator :func:`verify` uses -- the
    reference logic lives only in this module, never a second, drifting copy) and bakes those
    FIXED command lines + reference-computed expected values into a STANDALONE script: the
    checklist runner (``system_builder._run_check``) writes a check's ``code`` to
    ``root/_s2s_acceptance_check.py`` and executes it as its own subprocess in the built system's
    directory, so the emitted script cannot ``import`` this harness module -- it only drives the
    built CLI (``subprocess.run([sys.executable, entry, str(capacity)], input=...)`` for ``lru`` and
    TASK-6's ``ring-buffer`` -- both inherently capacity-bounded;
    ``subprocess.run([sys.executable, entry], input=...)`` -- no ``capacity`` argv -- for TASK-4's
    ``priority-queue`` and TASK-5's ``ttl-store``) and compares its stdout, line by line, against
    the baked-in expected values, asserting on the FIRST divergence. NO ORACLE LEAK: every expected
    value came from the reference model computed here, never from any hidden test. Returns
    ``{"name", "code"}`` (the shape every other acceptance check in this codebase uses -- see
    ``system_builder._no_crash_subprocess_check`` / ``_roundtrip_acceptance_check``). Never raises
    -- any internal error returns ``None`` (adds nothing to the checklist, exactly like the
    unimplemented-class case)."""
    try:
        if not cls or cls not in _IMPLEMENTED_CLASSES:
            return None
        cmd_lines, expected_lines = _build_sequence(cls, seed, 24, capacity)
        if not cmd_lines:
            return None
        entry_name = str(entry) if entry else ""
        if not entry_name:
            return None
        # TASK-4/TASK-5/TASK-6: priority-queue and ttl-store have no capacity argv (unlike lru and
        # TASK-6's ring-buffer, both inherently capacity-bounded) -- keep the lru argv line
        # byte-identical to before, only branch the argv expression itself.
        argv_src = ("[sys.executable, entry, str(capacity)]" if cls in ("lru", "ring-buffer")
                    else "[sys.executable, entry]")
        code = (
            "import subprocess, sys\n"
            f"entry = {entry_name!r}\n"
            f"capacity = {capacity!r}\n"
            f"cmd_lines = {cmd_lines!r}\n"
            f"expected_lines = {expected_lines!r}\n"
            f"result = subprocess.run({argv_src},\n"
            "                        input='\\n'.join(cmd_lines) + '\\n',\n"
            "                        capture_output=True, text=True, timeout=20)\n"
            "actual_lines = result.stdout.splitlines()\n"
            "for i, exp in enumerate(expected_lines):\n"
            "    act = actual_lines[i] if i < len(actual_lines) else None\n"
            f'    assert act == exp, f"ADT {cls} divergence at op[{{i}}]: expected {{exp!r}}, '
            'got {act!r}"\n'
        )
        return {
            "name": f"minimum: {cls} differential-oracle (seeded ops vs textbook reference)",
            "code": code,
        }
    except Exception:
        return None
# #EXT-056-REQ-1 End
