"""EXT-056 REQ-1 (TASK-1): tests for the ADT differential oracle core (`harness/adt_oracle.py`).

All fixtures below are tiny, offline, single-file Python CLI programs written to a temp dir -- no
docker, no network, nothing skipped. `verify()` never raises (Tenet 3): every path here proves that
directly, including the two "good"/"buggy" LRU fixtures used to prove the differential drive itself
actually catches the classic `_move_to_head` pointer bug with a localized first-divergence witness.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from harness import adt_oracle

# #EXT-056-REQ-1 Start

_GOOD_LRU_CLI = '''\
import sys
from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.data = OrderedDict()

    def get(self, key):
        if key not in self.data:
            return None
        self.data.move_to_end(key)
        return self.data[key]

    def put(self, key, value):
        if key in self.data:
            self.data.move_to_end(key)
        self.data[key] = value
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)


def main():
    capacity = int(sys.argv[1])
    cache = LRUCache(capacity)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "put":
            key, value = parts[1], parts[2]
            cache.put(key, value)
            print("ok")
        elif cmd == "get":
            key = parts[1]
            value = cache.get(key)
            print("none" if value is None else value)


if __name__ == "__main__":
    main()
'''

# The classic `_move_to_head` pointer bug: the stub never actually relinks the accessed/updated
# node, so nothing is ever protected from the next eviction -- eviction silently degrades to plain
# insertion order (FIFO-like) instead of real recency order. Authored independently of the
# reference model in `harness/adt_oracle.py` (a different implementation strategy -- doubly-linked
# list + dict, not `OrderedDict`), matching this task's acceptance criterion for a held-out-style
# differential check.
_BUGGY_LRU_CLI = '''\
import sys


class Node:
    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key=None, value=None):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


class BuggyLRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.map = {}
        self.head = Node()
        self.tail = Node()
        self.head.next = self.tail
        self.tail.prev = self.head

    def _remove(self, node):
        node.prev.next = node.next
        node.next.prev = node.prev

    def _add_to_head(self, node):
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node

    def _move_to_head(self, node):
        # BUG: intended to detach + re-insert `node` at the head so it becomes the
        # most-recently-used entry -- this stub never relinks anything, so it is silently a
        # no-op and recency order never actually changes on get/update.
        pass

    def get(self, key):
        if key not in self.map:
            return None
        node = self.map[key]
        self._move_to_head(node)
        return node.value

    def put(self, key, value):
        if key in self.map:
            node = self.map[key]
            node.value = value
            self._move_to_head(node)
            return
        node = Node(key, value)
        self.map[key] = node
        self._add_to_head(node)
        if len(self.map) > self.capacity:
            lru_node = self.tail.prev
            self._remove(lru_node)
            del self.map[lru_node.key]


def main():
    capacity = int(sys.argv[1])
    cache = BuggyLRUCache(capacity)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "put":
            key, value = parts[1], parts[2]
            cache.put(key, value)
            print("ok")
        elif cmd == "get":
            key = parts[1]
            value = cache.get(key)
            print("none" if value is None else value)


if __name__ == "__main__":
    main()
'''


# A correct heapq-based priority-queue CLI, authored independently of the reference model in
# `harness/adt_oracle.py` (TASK-4): push/pop/peek with a monotonic insertion counter for stable
# tie-break ordering, driven with NO extra argv (the priority-queue CLI convention -- unlike LRU's
# `<capacity>` argv).
_GOOD_PQ_CLI = '''\
import heapq
import sys


class PriorityQueue:
    def __init__(self):
        self.heap = []
        self.counter = 0

    def push(self, priority, item):
        heapq.heappush(self.heap, (priority, self.counter, item))
        self.counter += 1

    def pop(self):
        if not self.heap:
            return None
        _, _, item = heapq.heappop(self.heap)
        return item

    def peek(self):
        if not self.heap:
            return None
        _, _, item = self.heap[0]
        return item


def main():
    pq = PriorityQueue()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "push":
            priority, item = int(parts[1]), parts[2]
            pq.push(priority, item)
            print("ok")
        elif cmd == "pop":
            value = pq.pop()
            print("none" if value is None else value)
        elif cmd == "peek":
            value = pq.peek()
            print("none" if value is None else value)


if __name__ == "__main__":
    main()
'''

# The classic tie-break bug: among EQUAL priorities, this stub prefers the MOST-recently-pushed
# item (LIFO-among-ties) instead of the correct stable FIFO-among-ties ordering. Authored
# independently of the reference model (a different implementation strategy -- a flat list scanned
# on every pop/peek, not a heap), matching this task's acceptance criterion for a held-out-style
# differential check.
_BUGGY_PQ_CLI = '''\
import sys


class BuggyPriorityQueue:
    def __init__(self):
        self.items = []  # list of (priority, insertion_index, item)
        self.counter = 0

    def push(self, priority, item):
        self.items.append((priority, self.counter, item))
        self.counter += 1

    def _select_index(self):
        # BUG: ties are broken by the LARGEST insertion index (most-recently-pushed wins)
        # instead of the smallest (stable FIFO-among-ties) -- silently inverts tie-break order.
        best_idx = None
        for i, (priority, counter, _item) in enumerate(self.items):
            if best_idx is None:
                best_idx = i
                continue
            b_priority, b_counter, _b_item = self.items[best_idx]
            if priority < b_priority or (priority == b_priority and counter > b_counter):
                best_idx = i
        return best_idx

    def pop(self):
        if not self.items:
            return None
        idx = self._select_index()
        _, _, item = self.items.pop(idx)
        return item

    def peek(self):
        if not self.items:
            return None
        idx = self._select_index()
        return self.items[idx][2]


def main():
    pq = BuggyPriorityQueue()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "push":
            priority, item = int(parts[1]), parts[2]
            pq.push(priority, item)
            print("ok")
        elif cmd == "pop":
            value = pq.pop()
            print("none" if value is None else value)
        elif cmd == "peek":
            value = pq.peek()
            print("none" if value is None else value)


if __name__ == "__main__":
    main()
'''


# A correct ttl-store CLI, authored independently of the reference model in
# `harness/adt_oracle.py` (TASK-5): a plain dict of `key -> (value, expiry_tick)` plus a VIRTUAL
# clock `now` that advances ONLY via the explicit `tick` command (never wall-clock/`time.time()`/
# `sleep`), driven with NO extra argv (like priority-queue, unlike LRU's `<capacity>`).
_GOOD_TTL_CLI = '''\
import sys


class TtlStore:
    def __init__(self):
        self.data = {}
        self.now = 0

    def set(self, key, value, ttl):
        self.data[key] = (value, self.now + int(ttl))

    def get(self, key):
        if key not in self.data:
            return None
        value, expiry = self.data[key]
        if self.now < expiry:
            return value
        return None

    def tick(self):
        self.now += 1


def main():
    store = TtlStore()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "set":
            key, value, ttl = parts[1], parts[2], int(parts[3])
            store.set(key, value, ttl)
            print("ok")
        elif cmd == "get":
            key = parts[1]
            value = store.get(key)
            print("none" if value is None else value)
        elif cmd == "tick":
            store.tick()
            print("ok")


if __name__ == "__main__":
    main()
'''

# The classic off-by-one expiry bug: the liveness check uses `now <= expiry` instead of the correct
# `now < expiry`, so every key silently survives ONE virtual tick longer than it should -- including
# the immediate-expiry (`ttl=0`) boundary, which this bug makes NOT immediately expire. Authored
# independently of the reference model (the same dict-based strategy, but with the inverted
# boundary condition), matching this task's acceptance criterion for a localized, held-out-style
# differential check.
_BUGGY_TTL_CLI = '''\
import sys


class BuggyTtlStore:
    def __init__(self):
        self.data = {}
        self.now = 0

    def set(self, key, value, ttl):
        self.data[key] = (value, self.now + int(ttl))

    def get(self, key):
        if key not in self.data:
            return None
        value, expiry = self.data[key]
        # BUG: off-by-one -- should be `self.now < expiry`, this lets a key survive one extra tick
        # (and makes ttl=0 NOT immediately expired, since now(0) <= expiry(0) is True).
        if self.now <= expiry:
            return value
        return None

    def tick(self):
        self.now += 1


def main():
    store = BuggyTtlStore()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "set":
            key, value, ttl = parts[1], parts[2], int(parts[3])
            store.set(key, value, ttl)
            print("ok")
        elif cmd == "get":
            key = parts[1]
            value = store.get(key)
            print("none" if value is None else value)
        elif cmd == "tick":
            store.tick()
            print("ok")


if __name__ == "__main__":
    main()
'''


def _write_cli(tmp_path: Path, source: str, name: str = "main.py") -> Path:
    root = tmp_path / name.replace(".py", "_root")
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(source, encoding="utf-8")
    return root


def _run_emitted_check(root: Path, check: dict) -> bool:
    """Runs an :func:`adt_oracle.acceptance_check` emission the SAME way
    ``system_builder._run_check`` drives it in production: write ``check["code"]`` to a standalone
    script inside ``root`` and execute it as its OWN subprocess (no import of this harness module
    is available there, proving the emitted script is truly self-contained). Returns True iff the
    subprocess exits 0 (the script's own ``assert`` on the first divergence is what fails it)."""
    script = root / "_test_acceptance_check.py"
    script.write_text(check["code"], encoding="utf-8", newline="\n")
    try:
        result = subprocess.run(
            [sys.executable, str(script)], cwd=str(root),
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    finally:
        try:
            script.unlink()
        except OSError:
            pass


# --- (a) classify -------------------------------------------------------------------------------

def test_classify_returns_lru_for_lru_shaped_spec_and_mods():
    spec = (
        "Build a fixed-capacity least-recently-used (LRU) cache. get(key) returns the value for "
        "key if present, else it is a miss. put(key, value) inserts or updates the value for key; "
        "if this would exceed capacity, the least-recently-used entry is evicted first."
    )
    mods = ["get", "put", "capacity"]
    assert adt_oracle.classify(spec, mods) == "lru"


def test_classify_returns_none_for_non_adt_build():
    spec = (
        "Write a simple command-line notes app that lets a user add, list, and delete text notes."
    )
    mods = ["add", "list", "delete", "main"]
    assert adt_oracle.classify(spec, mods) is None


def test_classify_never_raises_on_malformed_input():
    assert adt_oracle.classify(None, None) is None
    assert adt_oracle.classify("", []) is None
    assert adt_oracle.classify(123, [None, 4.5, object()]) is None  # type: ignore[arg-type]


# --- (b) _seeded_ops determinism -----------------------------------------------------------------

def test_seeded_ops_deterministic_across_same_seed():
    first = adt_oracle._seeded_ops("lru", 1234, 24)
    second = adt_oracle._seeded_ops("lru", 1234, 24)
    assert first == second
    assert len(first) == 24


def test_seeded_ops_differs_across_different_seeds():
    a = adt_oracle._seeded_ops("lru", 1234, 24)
    b = adt_oracle._seeded_ops("lru", 5678, 24)
    assert a != b


def test_seeded_ops_empty_for_unimplemented_class():
    # TASK-7 makes "fifo" the FIFTH and FINAL implemented class -- all 5 SUPPORTED_CLASSES now
    # have a reference model (see the "fifo (TASK-7)" section further down in this same file for
    # its coverage), so an unimplemented class must now be a class outside SUPPORTED_CLASSES
    # entirely; it must still yield an empty (never fabricated) sequence.
    assert adt_oracle._seeded_ops("stack", 1234, 24) == []


# --- (c)/(d) verify: differential drive + first-divergence ---------------------------------------

def test_verify_passes_correct_ordereddict_lru_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_LRU_CLI)
    result = adt_oracle.verify(root, "main.py", "lru")
    assert result.applicable is True
    assert result.cls == "lru"
    assert result.ok is True
    assert result.first_divergence is None


def test_verify_fails_buggy_move_to_head_fixture_with_localized_divergence(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_LRU_CLI)
    result = adt_oracle.verify(root, "main.py", "lru")
    assert result.applicable is True
    assert result.cls == "lru"
    assert result.ok is False
    assert result.first_divergence is not None
    divergence = result.first_divergence
    assert set(divergence.keys()) == {"index", "op", "args", "expected", "actual"}
    assert isinstance(divergence["index"], int) and divergence["index"] >= 0
    # the diverging op is a get (the pointer bug only manifests as a wrong get result once an
    # unprotected key gets evicted out of turn)
    assert divergence["op"] == "get"
    assert divergence["expected"] != divergence["actual"]


# --- never-raises / no-op guarantees --------------------------------------------------------------

def test_verify_never_raises_and_is_inconclusive_for_non_adt_class():
    result = adt_oracle.verify(".", "main.py", None)
    assert result.applicable is False
    assert result.ok is True
    assert result.first_divergence is None


def test_verify_never_raises_on_missing_root_or_entry(tmp_path):
    missing_root = tmp_path / "does-not-exist"
    result = adt_oracle.verify(missing_root, "main.py", "lru")
    assert result.applicable is False
    assert result.ok is True

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    result2 = adt_oracle.verify(empty_root, "main.py", "lru")
    assert result2.applicable is False
    assert result2.ok is True


def test_verify_never_raises_on_completely_malformed_input():
    result = adt_oracle.verify(None, None, "lru")
    assert result.applicable is False
    assert result.ok is True
    assert result.first_divergence is None


def test_verify_inconclusive_for_crashing_cli_never_raises(tmp_path):
    root = _write_cli(tmp_path, "raise RuntimeError('boom')\n")
    result = adt_oracle.verify(root, "main.py", "lru")
    # a crashing CLI is a real divergence (expected 'ok' from the reference, nothing/garbage from
    # the built CLI) -- either way, verify must not raise and must return a well-formed AdtResult.
    assert isinstance(result, adt_oracle.AdtResult)
    assert result.ok in (True, False)


# --- priority-queue (TASK-4): classify, reference ordering, verify PASS/FAIL --------------------

def test_classify_returns_priority_queue_for_pq_shaped_spec_and_mods():
    spec = (
        "Build a priority queue backed by a min-heap. push(priority, item) inserts an item at "
        "the given priority. pop() removes and returns the item with the highest priority "
        "(the numerically smallest priority value wins); peek() returns the same item without "
        "removing it."
    )
    mods = ["push", "pop", "peek", "priority"]
    assert adt_oracle.classify(spec, mods) == "priority-queue"
    assert adt_oracle.classify_confident(spec, mods) == "priority-queue"


def test_classify_does_not_return_priority_queue_for_non_pq_spec():
    spec = (
        "Write a simple command-line notes app that lets a user add, list, and delete text notes."
    )
    mods = ["add", "list", "delete", "main"]
    assert adt_oracle.classify(spec, mods) != "priority-queue"
    assert adt_oracle.classify_confident(spec, mods) != "priority-queue"


def test_classify_confident_does_not_return_priority_queue_on_method_token_overlap_alone():
    # a plain task queue that only ever says "push"/"pop"/"peek" (no "priority queue"/"min-heap"/
    # "max-heap" wording) must NOT be classified -- the conservative gate requires the spec text
    # itself to name the ADT, never method-token coincidence alone.
    spec = "Build a simple stack CLI: push(item) and pop() and peek() on top of a list."
    mods = ["push", "pop", "peek"]
    assert adt_oracle.classify_confident(spec, mods) is None


def test_pq_seeded_ops_deterministic_across_same_seed():
    # unlike `lru` (whose sequence length is exactly `n`), the pq sequence guarantees the
    # mandatory drain-to-empty + trailing pop/peek boundary probes (see `_pq_seeded_ops`'s
    # docstring), so its length can exceed `n` -- what must hold is BYTE-IDENTICAL determinism
    # across two calls with the same seed, not an exact length.
    first = adt_oracle._seeded_ops("priority-queue", 1234, 24)
    second = adt_oracle._seeded_ops("priority-queue", 1234, 24)
    assert first == second
    assert len(first) >= 24


def test_priority_queue_reference_pops_priority_then_insertion_order_including_ties():
    ref = adt_oracle._priority_queue_reference()
    ref.push(5, "low-priority-first-in")
    ref.push(1, "high-priority-a")
    ref.push(1, "high-priority-b")  # tie with the item above -- must come out AFTER it (FIFO)
    ref.push(3, "mid-priority")

    assert ref.peek() == "high-priority-a"
    assert ref.pop() == "high-priority-a"
    assert ref.peek() == "high-priority-b"
    assert ref.pop() == "high-priority-b"
    assert ref.pop() == "mid-priority"
    assert ref.pop() == "low-priority-first-in"
    assert ref.pop() is None
    assert ref.peek() is None


def test_verify_passes_correct_heapq_pq_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_PQ_CLI)
    result = adt_oracle.verify(root, "main.py", "priority-queue")
    assert result.applicable is True
    assert result.cls == "priority-queue"
    assert result.ok is True
    assert result.first_divergence is None


def test_verify_fails_buggy_tie_break_pq_fixture_with_localized_divergence(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_PQ_CLI)
    result = adt_oracle.verify(root, "main.py", "priority-queue")
    assert result.applicable is True
    assert result.cls == "priority-queue"
    assert result.ok is False
    assert result.first_divergence is not None
    divergence = result.first_divergence
    assert set(divergence.keys()) == {"index", "op", "args", "expected", "actual"}
    assert isinstance(divergence["index"], int) and divergence["index"] >= 0
    # the deliberate tie-break stress block (three same-priority pushes then an immediate peek)
    # is always the FIRST thing `_pq_seeded_ops` generates, so a broken tie-break must surface
    # right there -- the diverging op is that peek, not some later random-mixing op.
    assert divergence["op"] == "peek"
    assert divergence["expected"] != divergence["actual"]


def test_verify_never_raises_on_missing_root_or_entry_for_priority_queue(tmp_path):
    missing_root = tmp_path / "does-not-exist-pq"
    result = adt_oracle.verify(missing_root, "main.py", "priority-queue")
    assert result.applicable is False
    assert result.ok is True


# --- priority-queue acceptance_check: same emitted-script drive, no import of this module ------

def test_acceptance_check_code_passes_against_correct_pq_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_PQ_CLI)
    check = adt_oracle.acceptance_check("main.py", "priority-queue")
    assert check is not None
    assert "priority-queue" in check["name"]
    assert _run_emitted_check(root, check) is True


def test_acceptance_check_code_fails_against_buggy_pq_fixture(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_PQ_CLI)
    check = adt_oracle.acceptance_check("main.py", "priority-queue")
    assert check is not None
    assert _run_emitted_check(root, check) is False


# --- ttl-store (TASK-5): classify, reference expiry, verify PASS/FAIL ---------------------------

def test_classify_returns_ttl_store_for_ttl_shaped_spec_and_mods():
    spec = (
        "Build a key-value store with time-to-live (TTL) semantics. set(key, value, ttl) stores "
        "a value that will expire after ttl ticks have passed. get(key) returns the value if it "
        "has not expired, else none."
    )
    mods = ["set", "get", "ttl"]
    assert adt_oracle.classify(spec, mods) == "ttl-store"
    assert adt_oracle.classify_confident(spec, mods) == "ttl-store"


def test_classify_does_not_return_ttl_store_for_non_ttl_spec():
    spec = (
        "Write a simple command-line notes app that lets a user add, list, and delete text notes."
    )
    mods = ["add", "list", "delete", "main"]
    assert adt_oracle.classify(spec, mods) != "ttl-store"
    assert adt_oracle.classify_confident(spec, mods) != "ttl-store"


def test_classify_confident_does_not_return_ttl_store_on_method_token_overlap_alone():
    # a plain set/get key-value store that never says "ttl"/"time-to-live"/"expire" wording must
    # NOT be classified -- the conservative gate requires the spec text itself to name the ADT,
    # never method-token coincidence alone (even though bare `classify` may score this as
    # ttl-store via the shared "set"/"get" command tokens -- exactly the false-positive
    # `classify_confident` exists to guard against).
    spec = "Build a simple key-value store: set(key, value) stores a value, get(key) returns it."
    mods = ["set", "get"]
    assert adt_oracle.classify_confident(spec, mods) is None


def test_ttl_seeded_ops_deterministic_across_same_seed():
    # like priority-queue (and unlike plain `lru`), the ttl-store sequence has a fixed boundary
    # prelude ahead of the random mixing phase (see `_ttl_seeded_ops`'s docstring), so its length
    # can exceed `n` -- what must hold is BYTE-IDENTICAL determinism across two calls with the
    # same seed, not an exact length.
    first = adt_oracle._seeded_ops("ttl-store", 1234, 24)
    second = adt_oracle._seeded_ops("ttl-store", 1234, 24)
    assert first == second
    assert len(first) >= 24


def test_ttl_store_reference_expires_at_correct_virtual_tick():
    # NO real sleep anywhere -- the virtual clock only ever advances via an explicit `tick()` call.
    ref = adt_oracle._ttl_store_reference()
    ref.set("k", "v1", 2)
    assert ref.get("k") == "v1"   # now=0 < expiry=2 -> live
    ref.tick()                     # now=1
    assert ref.get("k") == "v1"   # now=1 < expiry=2 -> still live
    ref.tick()                     # now=2
    assert ref.get("k") is None   # now=2 < expiry=2 is False -> expired

    # ttl=0 is the immediate-expiry boundary: expired with NO tick needed at all.
    ref.set("z", "v0", 0)
    assert ref.get("z") is None

    # a key that was never set at all is a clean miss.
    assert ref.get("never-set") is None

    # overwriting an existing key RESETS the ttl relative to the CURRENT virtual `now`, not the
    # original `set` time.
    ref2 = adt_oracle._ttl_store_reference()
    ref2.set("k", "v1", 1)
    ref2.tick()                    # now=1; the ORIGINAL ttl=1 would already be expired here
    ref2.set("k", "v2", 1)         # overwrite: new expiry = now(1) + 1 = 2
    assert ref2.get("k") == "v2"  # now=1 < expiry=2 -> the overwrite kept it alive
    ref2.tick()                    # now=2
    assert ref2.get("k") is None  # now=2 < expiry=2 is False -> expired on its OWN schedule


def test_verify_passes_correct_ttl_store_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_TTL_CLI)
    result = adt_oracle.verify(root, "main.py", "ttl-store")
    assert result.applicable is True
    assert result.cls == "ttl-store"
    assert result.ok is True
    assert result.first_divergence is None


def test_verify_fails_buggy_off_by_one_expiry_ttl_fixture_with_localized_divergence(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_TTL_CLI)
    result = adt_oracle.verify(root, "main.py", "ttl-store")
    assert result.applicable is True
    assert result.cls == "ttl-store"
    assert result.ok is False
    assert result.first_divergence is not None
    divergence = result.first_divergence
    assert set(divergence.keys()) == {"index", "op", "args", "expected", "actual"}
    assert isinstance(divergence["index"], int) and divergence["index"] >= 0
    # the immediate-expiry boundary (a ttl=0 `set` immediately followed by a `get`, with NO tick
    # in between) is always the FIRST thing `_ttl_seeded_ops` generates, so the off-by-one
    # `now <= expiry` bug must surface right there -- the diverging op is that get, not some
    # later random-mixing op.
    assert divergence["op"] == "get"
    assert divergence["args"] == ["a"]
    assert divergence["expected"] == "none"
    assert divergence["actual"] != "none"


def test_verify_never_raises_on_missing_root_or_entry_for_ttl_store(tmp_path):
    missing_root = tmp_path / "does-not-exist-ttl"
    result = adt_oracle.verify(missing_root, "main.py", "ttl-store")
    assert result.applicable is False
    assert result.ok is True


# --- ttl-store acceptance_check: same emitted-script drive, no import of this module -------------

def test_acceptance_check_code_passes_against_correct_ttl_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_TTL_CLI)
    check = adt_oracle.acceptance_check("main.py", "ttl-store")
    assert check is not None
    assert "ttl-store" in check["name"]
    assert _run_emitted_check(root, check) is True


def test_acceptance_check_code_fails_against_buggy_ttl_fixture(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_TTL_CLI)
    check = adt_oracle.acceptance_check("main.py", "ttl-store")
    assert check is not None
    assert _run_emitted_check(root, check) is False


# A correct ring-buffer CLI, authored independently of the reference model in
# `harness/adt_oracle.py` (TASK-6): a manual circular array (head index + size counter) rather than
# the reference's `collections.deque(maxlen=...)` strategy -- a different implementation approach
# that must still agree on every observable, matching this task's acceptance criterion for a
# held-out-style differential check. Driven with a `<capacity>` argv (like LRU, unlike
# priority-queue/ttl-store).
_GOOD_RING_CLI = '''\
import sys


class RingBuffer:
    def __init__(self, capacity):
        self.capacity = capacity
        self.buf = [None] * capacity
        self.head = 0
        self.size = 0

    def push(self, item):
        tail = (self.head + self.size) % self.capacity
        self.buf[tail] = item
        if self.size < self.capacity:
            self.size += 1
        else:
            # at capacity: this push overwrites the oldest slot (which is exactly `tail` here,
            # since tail wraps back onto head once size == capacity) -- advance head past it.
            self.head = (self.head + 1) % self.capacity

    def pop(self):
        if self.size == 0:
            return None
        item = self.buf[self.head]
        self.head = (self.head + 1) % self.capacity
        self.size -= 1
        return item

    def peek(self):
        if self.size == 0:
            return None
        return self.buf[self.head]


def main():
    capacity = int(sys.argv[1])
    rb = RingBuffer(capacity)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "push":
            item = parts[1]
            rb.push(item)
            print("ok")
        elif cmd == "pop":
            value = rb.pop()
            print("none" if value is None else value)
        elif cmd == "peek":
            value = rb.peek()
            print("none" if value is None else value)


if __name__ == "__main__":
    main()
'''

# The classic wrong-wrap-order bug: at capacity, this stub overwrites the NEWEST slot (the item
# just added) instead of evicting the OLDEST -- the true oldest item is never evicted at all, it
# just sits there forever while the most-recent slot keeps getting clobbered on every subsequent
# push. Authored independently of the reference model (a plain list, not a circular array),
# matching this task's acceptance criterion for a localized, held-out-style differential check.
_BUGGY_RING_CLI = '''\
import sys


class BuggyRingBuffer:
    def __init__(self, capacity):
        self.capacity = capacity
        self.items = []

    def push(self, item):
        if len(self.items) < self.capacity:
            self.items.append(item)
        else:
            # BUG: overwrites the NEWEST item (the last slot) instead of evicting the OLDEST (the
            # first slot) -- the true oldest item is never evicted, it just sits there forever.
            self.items[-1] = item

    def pop(self):
        if not self.items:
            return None
        return self.items.pop(0)

    def peek(self):
        if not self.items:
            return None
        return self.items[0]


def main():
    capacity = int(sys.argv[1])
    rb = BuggyRingBuffer(capacity)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "push":
            item = parts[1]
            rb.push(item)
            print("ok")
        elif cmd == "pop":
            value = rb.pop()
            print("none" if value is None else value)
        elif cmd == "peek":
            value = rb.peek()
            print("none" if value is None else value)


if __name__ == "__main__":
    main()
'''


# --- ring-buffer (TASK-6): classify, reference wrap-around, verify PASS/FAIL --------------------

def test_classify_returns_ring_buffer_for_ring_buffer_shaped_spec_and_mods():
    spec = (
        "Build a fixed-capacity ring buffer (circular buffer). push(item) appends item to the "
        "buffer; once the buffer is full, the next push overwrites the oldest item. pop() removes "
        "and returns the oldest item, or none if empty. peek() returns the oldest item without "
        "removing it."
    )
    mods = ["push", "pop", "peek", "ring"]
    assert adt_oracle.classify(spec, mods) == "ring-buffer"
    assert adt_oracle.classify_confident(spec, mods) == "ring-buffer"


def test_classify_does_not_return_ring_buffer_for_non_ring_spec():
    spec = (
        "Write a simple command-line notes app that lets a user add, list, and delete text notes."
    )
    mods = ["add", "list", "delete", "main"]
    assert adt_oracle.classify(spec, mods) != "ring-buffer"
    assert adt_oracle.classify_confident(spec, mods) != "ring-buffer"


def test_classify_confident_does_not_return_ring_buffer_on_method_token_overlap_alone():
    # a plain stack that only ever says "push"/"pop" (no "ring buffer"/"circular buffer" wording)
    # must NOT be classified -- the conservative gate requires the spec text itself to name the
    # ADT, never method-token coincidence alone (push/pop/overwrite/ring tokens are shared with an
    # ordinary stack or queue).
    spec = "Build a simple stack CLI: push(item) adds to the top, pop() removes the top item."
    mods = ["push", "pop"]
    assert adt_oracle.classify_confident(spec, mods) is None


def test_ring_buffer_seeded_ops_deterministic_across_same_seed():
    # like priority-queue/ttl-store (and unlike plain `lru`), the ring-buffer sequence has a fixed
    # boundary prelude ahead of the random mixing phase (see `_ring_buffer_seeded_ops`'s
    # docstring), so its length can exceed `n` -- what must hold is BYTE-IDENTICAL determinism
    # across two calls with the same seed, not an exact length.
    first = adt_oracle._seeded_ops("ring-buffer", 1234, 24)
    second = adt_oracle._seeded_ops("ring-buffer", 1234, 24)
    assert first == second
    assert len(first) >= 24


def test_ring_buffer_reference_wrap_around_overwrites_oldest_correctly():
    ref = adt_oracle._ring_buffer_reference(3)
    ref.push("r0")
    ref.push("r1")
    ref.push("r2")
    assert ref.peek() == "r0"  # buffer full; oldest is r0

    # one more push at capacity must overwrite the OLDEST item (r0), never r1/r2.
    ref.push("r3")
    assert ref.peek() == "r1"  # r0 is gone; r1 is now the oldest

    assert ref.pop() == "r1"
    assert ref.pop() == "r2"
    assert ref.pop() == "r3"
    assert ref.pop() is None   # drain-past-empty
    assert ref.peek() is None  # peek on empty


def test_verify_passes_correct_ring_buffer_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_RING_CLI)
    result = adt_oracle.verify(root, "main.py", "ring-buffer")
    assert result.applicable is True
    assert result.cls == "ring-buffer"
    assert result.ok is True
    assert result.first_divergence is None


def test_verify_fails_buggy_wrong_wrap_order_ring_fixture_with_localized_divergence(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_RING_CLI)
    result = adt_oracle.verify(root, "main.py", "ring-buffer")
    assert result.applicable is True
    assert result.cls == "ring-buffer"
    assert result.ok is False
    assert result.first_divergence is not None
    divergence = result.first_divergence
    assert set(divergence.keys()) == {"index", "op", "args", "expected", "actual"}
    assert isinstance(divergence["index"], int) and divergence["index"] >= 0
    # the wrap-around boundary probe (a peek immediately following the capacity-triggering push)
    # is always near the START of `_ring_buffer_seeded_ops`'s fixed prelude, so a wrong-wrap-order
    # bug must surface right there -- the diverging op is that peek, not some later random-mixing
    # op.
    assert divergence["op"] == "peek"
    assert divergence["expected"] == "r1"
    assert divergence["actual"] == "r0"


def test_verify_never_raises_on_missing_root_or_entry_for_ring_buffer(tmp_path):
    missing_root = tmp_path / "does-not-exist-ring"
    result = adt_oracle.verify(missing_root, "main.py", "ring-buffer")
    assert result.applicable is False
    assert result.ok is True


# --- ring-buffer acceptance_check: same emitted-script drive, no import of this module ----------

def test_acceptance_check_code_passes_against_correct_ring_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_RING_CLI)
    check = adt_oracle.acceptance_check("main.py", "ring-buffer")
    assert check is not None
    assert "ring-buffer" in check["name"]
    assert _run_emitted_check(root, check) is True


def test_acceptance_check_code_fails_against_buggy_ring_fixture(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_RING_CLI)
    check = adt_oracle.acceptance_check("main.py", "ring-buffer")
    assert check is not None
    assert _run_emitted_check(root, check) is False


# A correct deque-based fifo CLI, authored independently of the reference model in
# `harness/adt_oracle.py` (TASK-7): enqueue/dequeue/peek with strict first-in-first-out ordering.
# Driven with NO extra argv (the fifo CLI convention -- like priority-queue/ttl-store, unlike LRU's
# `<capacity>` argv, since a plain FIFO queue is unbounded).
_GOOD_FIFO_CLI = '''\
import sys
from collections import deque


class Fifo:
    def __init__(self):
        self.data = deque()

    def enqueue(self, item):
        self.data.append(item)

    def dequeue(self):
        if not self.data:
            return None
        return self.data.popleft()

    def peek(self):
        if not self.data:
            return None
        return self.data[0]


def main():
    q = Fifo()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "enqueue":
            item = parts[1]
            q.enqueue(item)
            print("ok")
        elif cmd == "dequeue":
            value = q.dequeue()
            print("none" if value is None else value)
        elif cmd == "peek":
            value = q.peek()
            print("none" if value is None else value)


if __name__ == "__main__":
    main()
'''

# The classic LIFO-instead-of-FIFO bug: this stub is really a STACK -- `dequeue`/`peek` operate on
# the LAST-added (most-recently-enqueued) item instead of the FIRST-added (oldest) one. Authored
# independently of the reference model (a plain list used as a stack, not a deque), matching this
# task's acceptance criterion for a localized, held-out-style differential check.
_BUGGY_FIFO_CLI = '''\
import sys


class BuggyFifo:
    def __init__(self):
        self.items = []

    def enqueue(self, item):
        self.items.append(item)

    def dequeue(self):
        if not self.items:
            return None
        # BUG: pops the LAST-added item (LIFO/stack order) instead of the FIRST-added (FIFO).
        return self.items.pop()

    def peek(self):
        if not self.items:
            return None
        # BUG: same LIFO mistake -- shows the most-recently-enqueued item, not the oldest.
        return self.items[-1]


def main():
    q = BuggyFifo()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "enqueue":
            item = parts[1]
            q.enqueue(item)
            print("ok")
        elif cmd == "dequeue":
            value = q.dequeue()
            print("none" if value is None else value)
        elif cmd == "peek":
            value = q.peek()
            print("none" if value is None else value)


if __name__ == "__main__":
    main()
'''


# --- fifo (TASK-7): classify, reference FIFO order, verify PASS/FAIL ----------------------------

def test_classify_returns_fifo_for_fifo_shaped_spec_and_mods():
    spec = (
        "Build a first-in-first-out (FIFO) queue. enqueue(item) adds item to the back of the "
        "queue. dequeue() removes and returns the oldest item, or none if empty. peek() returns "
        "the oldest item without removing it."
    )
    mods = ["enqueue", "dequeue", "peek"]
    assert adt_oracle.classify(spec, mods) == "fifo"
    assert adt_oracle.classify_confident(spec, mods) == "fifo"


def test_classify_does_not_return_fifo_for_non_fifo_spec():
    spec = (
        "Write a simple command-line notes app that lets a user add, list, and delete text notes."
    )
    mods = ["add", "list", "delete", "main"]
    assert adt_oracle.classify(spec, mods) != "fifo"
    assert adt_oracle.classify_confident(spec, mods) != "fifo"


def test_classify_confident_does_not_return_fifo_on_method_token_overlap_alone():
    # a plain queue that only ever says "enqueue"/"dequeue" (no "fifo"/"first-in-first-out"/
    # "first in first out" wording) must NOT be classified -- the conservative gate requires the
    # spec text itself to name the ADT, never method-token coincidence alone.
    spec = "Build a simple queue: enqueue(item) adds an item, dequeue() removes and returns one."
    mods = ["enqueue", "dequeue"]
    assert adt_oracle.classify_confident(spec, mods) is None


def test_fifo_seeded_ops_deterministic_across_same_seed():
    first = adt_oracle._seeded_ops("fifo", 1234, 24)
    second = adt_oracle._seeded_ops("fifo", 1234, 24)
    assert first == second
    assert len(first) >= 24


def test_fifo_reference_dequeues_in_fifo_order():
    ref = adt_oracle._fifo_reference()
    ref.enqueue("f0")
    ref.enqueue("f1")
    ref.enqueue("f2")

    assert ref.peek() == "f0"  # oldest item first, never the newest
    assert ref.dequeue() == "f0"
    assert ref.peek() == "f1"
    assert ref.dequeue() == "f1"
    assert ref.dequeue() == "f2"
    assert ref.dequeue() is None  # drain-past-empty
    assert ref.peek() is None    # peek on empty


def test_verify_passes_correct_fifo_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_FIFO_CLI)
    result = adt_oracle.verify(root, "main.py", "fifo")
    assert result.applicable is True
    assert result.cls == "fifo"
    assert result.ok is True
    assert result.first_divergence is None


def test_verify_fails_buggy_lifo_fifo_fixture_with_localized_divergence(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_FIFO_CLI)
    result = adt_oracle.verify(root, "main.py", "fifo")
    assert result.applicable is True
    assert result.cls == "fifo"
    assert result.ok is False
    assert result.first_divergence is not None
    divergence = result.first_divergence
    assert set(divergence.keys()) == {"index", "op", "args", "expected", "actual"}
    assert isinstance(divergence["index"], int) and divergence["index"] >= 0
    # the fill-then-peek boundary probe (a peek immediately following the fixed fill of 3
    # enqueues) is always at the START of `_fifo_seeded_ops`'s fixed prelude, so a LIFO-instead-of-
    # FIFO bug must surface right there -- the diverging op is that peek, not some later
    # random-mixing op.
    assert divergence["op"] == "peek"
    assert divergence["expected"] == "f0"
    assert divergence["actual"] == "f2"


def test_verify_never_raises_on_missing_root_or_entry_for_fifo(tmp_path):
    missing_root = tmp_path / "does-not-exist-fifo"
    result = adt_oracle.verify(missing_root, "main.py", "fifo")
    assert result.applicable is False
    assert result.ok is True


# --- fifo acceptance_check: same emitted-script drive, no import of this module -----------------

def test_acceptance_check_code_passes_against_correct_fifo_fixture(tmp_path):
    root = _write_cli(tmp_path, _GOOD_FIFO_CLI)
    check = adt_oracle.acceptance_check("main.py", "fifo")
    assert check is not None
    assert "fifo" in check["name"]
    assert _run_emitted_check(root, check) is True


def test_acceptance_check_code_fails_against_buggy_fifo_fixture(tmp_path):
    root = _write_cli(tmp_path, _BUGGY_FIFO_CLI)
    check = adt_oracle.acceptance_check("main.py", "fifo")
    assert check is not None
    assert _run_emitted_check(root, check) is False
# #EXT-056-REQ-1 End
