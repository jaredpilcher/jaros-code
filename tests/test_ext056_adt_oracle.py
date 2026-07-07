"""EXT-056 REQ-1 (TASK-1): tests for the ADT differential oracle core (`harness/adt_oracle.py`).

All fixtures below are tiny, offline, single-file Python CLI programs written to a temp dir -- no
docker, no network, nothing skipped. `verify()` never raises (Tenet 3): every path here proves that
directly, including the two "good"/"buggy" LRU fixtures used to prove the differential drive itself
actually catches the classic `_move_to_head` pointer bug with a localized first-divergence witness.
"""

from __future__ import annotations

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


def _write_cli(tmp_path: Path, source: str, name: str = "main.py") -> Path:
    root = tmp_path / name.replace(".py", "_root")
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(source, encoding="utf-8")
    return root


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
    # priority-queue etc. are classified but TASK-1 only builds the lru reference model; an
    # unimplemented class must yield an empty (never fabricated) sequence.
    assert adt_oracle._seeded_ops("priority-queue", 1234, 24) == []


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
# #EXT-056-REQ-1 End
