"""EXT-056 REQ-1 (TASK-2): wires the ADT differential oracle (`harness/adt_oracle.py`, TASK-1)
into `harness.system_builder`'s DETERMINISTIC MINIMUM acceptance checklist -- composed by UNION
(`_compose_acceptance_checklist`), so the oracle can only ever ADD a way to FAIL a build
(`done` True->False), never manufacture a false-done. This file proves the FOUR load-bearing
properties TASK-2 calls for:
  (a) an EXPLICIT LRU spec's minimum checklist INCLUDES the adt differential-oracle check;
  (b) a non-ADT spec, AND a plain get/put store spec that never says "lru"/"least recently
      used", both leave the checklist UNCHANGED (conservative no-op -- no false-not-done);
  (c) the emitted check `code`, run through the REAL `_minimum_acceptance` + `_run_check`
      machinery (no shortcuts), PASSES against a correct OrderedDict LRU fixture and FAILS
      against the classic `_move_to_head` pointer-bug fixture;
  (d) UNION-SAFETY: `_compose_acceptance_checklist` for a non-ADT spec is BYTE-IDENTICAL to
      what it would be with the oracle wiring disabled entirely -- the minimum is never made
      SPARSER, only ever stricter.

OFFLINE -- no live model; the (a)/(b)/(d) checks need no `llm` at all (pure deterministic
derivation), and (d) uses a canned `llm` only because `_compose_acceptance_checklist` requires
one (its own model-proposal path is exercised elsewhere, not the concern of this file).
"""

from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness import adt_oracle
from harness.system_builder import (
    _compose_acceptance_checklist,
    _minimum_acceptance,
    _run_check,
)

# #EXT-056-REQ-1 Start

# --- fixtures --------------------------------------------------------------------------------

LRU_SPEC = (
    "Build a fixed-capacity LRU (least-recently-used) cache CLI in main.py: `python main.py "
    "<capacity>` then reads commands from stdin -- 'get <key>' returns the value or 'none', "
    "'put <key> <value>' inserts or updates the value and evicts the least-recently-used entry "
    "once the cache exceeds capacity."
)
LRU_MODS = [
    {"name": "main.py", "responsibility": "LRU cache CLI", "imports": [],
     "exports": [{"name": "get", "signature": "def get(key):"},
                 {"name": "put", "signature": "def put(key, value):"}]},
]
LRU_PLAN = {"entrypoint": "main.py", "modules": LRU_MODS, "acceptance": "lru semantics"}

NOTES_SPEC = (
    "Write a simple command-line notes app that lets a user 'add' and 'list' text notes."
)
NOTES_MODS = [
    {"name": "main.py", "responsibility": "notes CLI", "imports": [],
     "exports": [{"name": "add_note", "signature": "def add_note(text):"},
                 {"name": "list_notes", "signature": "def list_notes():"}]},
]
NOTES_PLAN = {"entrypoint": "main.py", "modules": NOTES_MODS, "acceptance": "add/list notes"}

# a plain bounded key/value store: shares get/put COMMAND TOKENS with the LRU class but its
# spec text never names "lru" / "least recently used" -- the conservative gate this task adds
# must NOT classify this as `lru` even though the un-gated `classify()` would (proven below).
PLAIN_GETPUT_SPEC = (
    "Build a fixed-capacity key-value store CLI in main.py: `python main.py <capacity>` then "
    "reads commands from stdin -- 'get <key>' returns the value or 'none', 'put <key> <value>' "
    "inserts or updates the value for key."
)

# The good/buggy LRU CLI fixtures below mirror `tests/test_ext056_adt_oracle.py`'s (a smaller,
# self-contained copy so this file stays independent of that one's private constants).

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

# The classic `_move_to_head` pointer bug: accessing/updating a key never actually protects it
# from the next eviction, so recency order silently degrades to plain insertion order.
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
        # BUG: never actually relinks anything -- a silent no-op.
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


def _adt_check_names(checks: "list[dict]") -> "list[str]":
    return [c["name"] for c in checks if "differential-oracle" in c.get("name", "")]


# --- (a) explicit LRU spec -> the minimum checklist INCLUDES the adt check -------------------

def test_minimum_acceptance_includes_adt_check_for_explicit_lru_spec():
    checks = _minimum_acceptance(LRU_SPEC, LRU_MODS, LRU_PLAN)
    adt_names = _adt_check_names(checks)
    assert len(adt_names) == 1
    assert "lru" in adt_names[0]


def test_composed_checklist_includes_adt_check_for_explicit_lru_spec():
    # the union-composed checklist (what build_system actually scores against) still carries
    # the minimum's adt check through untouched, even with a canned llm in the mix.
    class _EmptyLlm:
        def complete(self, request):
            class _Resp:
                text = "[]"
            return _Resp()

    composed = _compose_acceptance_checklist(LRU_SPEC, LRU_MODS, _EmptyLlm(), LRU_PLAN)
    assert _adt_check_names(composed)


# --- (b) conservative no-op: non-ADT spec, and a plain get/put spec with no "lru" keyword ----

def test_minimum_acceptance_excludes_adt_check_for_non_adt_notes_spec():
    checks = _minimum_acceptance(NOTES_SPEC, NOTES_MODS, NOTES_PLAN)
    assert _adt_check_names(checks) == []


def test_minimum_acceptance_excludes_adt_check_for_plain_getput_spec_without_lru_keyword():
    # sanity: the UN-gated classify() DOES fire on command-token overlap alone -- proving the
    # conservative gate (classify_confident) is the thing actually doing the work below, not
    # an accident of classify() itself failing to match.
    assert adt_oracle.classify(PLAIN_GETPUT_SPEC, ["get", "put", "main.py"]) == "lru"
    assert adt_oracle.classify_confident(PLAIN_GETPUT_SPEC, ["get", "put", "main.py"]) is None

    checks = _minimum_acceptance(PLAIN_GETPUT_SPEC, LRU_MODS, LRU_PLAN)
    assert _adt_check_names(checks) == []


# --- (c) the emitted check code, run through the REAL wiring, passes/fails correctly ---------

def test_adt_check_code_passes_against_correct_lru_fixture(tmp_path):
    root = tmp_path / "good_lru_cli"
    root.mkdir()
    (root / "main.py").write_text(_GOOD_LRU_CLI, encoding="utf-8", newline="\n")

    checks = _minimum_acceptance(LRU_SPEC, LRU_MODS, LRU_PLAN)
    adt_check = next(c for c in checks if "differential-oracle" in c["name"])
    assert _run_check(root, adt_check) is True


def test_adt_check_code_fails_against_buggy_move_to_head_fixture(tmp_path):
    root = tmp_path / "buggy_lru_cli"
    root.mkdir()
    (root / "main.py").write_text(_BUGGY_LRU_CLI, encoding="utf-8", newline="\n")

    checks = _minimum_acceptance(LRU_SPEC, LRU_MODS, LRU_PLAN)
    adt_check = next(c for c in checks if "differential-oracle" in c["name"])
    assert _run_check(root, adt_check) is False


# --- (d) UNION-SAFETY: a non-ADT spec's composed checklist is byte-identical to before --------

def test_union_safety_composed_checklist_unaffected_for_non_adt_spec(monkeypatch):
    class _EmptyLlm:
        def complete(self, request):
            class _Resp:
                text = "[]"
            return _Resp()

    llm = _EmptyLlm()
    with_oracle = _compose_acceptance_checklist(NOTES_SPEC, NOTES_MODS, llm, NOTES_PLAN)

    # simulate "before this task's wiring" by disabling the oracle's classifier entirely (the
    # `if adt_cls:` branch in `_minimum_acceptance` then never fires, exactly as if the
    # `# #EXT-056-REQ-1` block were absent) and recompute from scratch.
    monkeypatch.setattr(adt_oracle, "classify_confident", lambda spec, mods: None)
    without_oracle = _compose_acceptance_checklist(NOTES_SPEC, NOTES_MODS, llm, NOTES_PLAN)

    assert with_oracle == without_oracle
    assert _adt_check_names(with_oracle) == []


def test_union_safety_composed_checklist_unaffected_for_explicit_lru_spec_when_disabled(monkeypatch):
    # the mirror check: WITH the oracle enabled the LRU spec's composed checklist is strictly
    # LARGER (adds a way to fail) than with it disabled -- the union only ever grows the bar.
    class _EmptyLlm:
        def complete(self, request):
            class _Resp:
                text = "[]"
            return _Resp()

    llm = _EmptyLlm()
    with_oracle = _compose_acceptance_checklist(LRU_SPEC, LRU_MODS, llm, LRU_PLAN)
    monkeypatch.setattr(adt_oracle, "classify_confident", lambda spec, mods: None)
    without_oracle = _compose_acceptance_checklist(LRU_SPEC, LRU_MODS, llm, LRU_PLAN)

    assert len(with_oracle) == len(without_oracle) + 1
    disabled_names = {c["name"] for c in without_oracle}
    assert all(c["name"] in disabled_names for c in with_oracle if "differential-oracle" not in c["name"])
# #EXT-056-REQ-1 End
