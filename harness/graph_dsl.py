"""EXT-058 TASK-5: the governed graph-DSL machinery + the first verified leaf (``ttl-store``).

Promotes the throwaway go/no-go prototype (``.jaros-data/dsl_probe.py`` + ``.jaros-data/dsl_gate2.py``,
both gates PASSED 2026-07-07, no oracle leak) into governed harness code -- PRIME-001 (h.1)'s explicit
**graph DSL**: nodes are verified leaf-classes, edges are typed connectors, and the pipeline splits at a
clean seam -- NL->DSL is reasoning (a later task); **DSL->system is deterministic construction**, which
is what this module implements.

SCOPE (deliberately narrow, per TASK-5): the DETERMINISTIC DSL machinery (parse/validate/structural
signature/equivalence) plus a verified leaf-library seeded with exactly ONE leaf, ``ttl-store`` -- the
class Gate 2 proved beats free-form generation 3/3 vs 0/3 on the hard ``kv-store-ttl-cli`` task. NL->DSL
emission and multi-leaf composition are later tasks (REQ-2/REQ-3's DAG-composer half); only the
single-leaf ``dsl_to_system`` slice of REQ-3 is implemented here.

Ported verbatim (same logic, no reinvention):
  - ``parse_dsl`` / ``validate_dsl`` / ``signature`` / ``equiv`` / ``VOCAB`` <- ``.jaros-data/dsl_probe.py``
  - ``TTL_STORE_LEAF`` template + the emit logic (now ``dsl_to_system``) <- ``.jaros-data/dsl_gate2.py``

Pure stdlib, **NEVER RAISES anywhere in this module** -- malformed input (not a dict, missing/extra
keys, an unknown node class, a dangling edge) always degrades to an honest empty/False/None result,
never an uncaught exception (mirrors ``harness/adt_oracle.py`` / ``harness/datastore_oracle.py``'s
discipline). No model call anywhere in this module.

Honesty (Tenet 3, no oracle leak): ``TTL_STORE_LEAF`` is authored from the ttl-store CONTRACT (the
VISIBLE set/get/delete-with-TTL semantics any caller could read off the class name), never from any
task's hidden ``checks`` -- it passes ``kv-store-ttl-cli`` because it correctly implements the general
contract, exactly like the ADT oracle's reference models (``harness/adt_oracle.py``).

Tenet 1 (two-plane / gated writes): ``dsl_to_system`` routes its single host write through
``harness.system_builder._jailed_write`` -- the SAME chokepoint ``build_system``/``modify_system``
already use -- so a supplied ``runtime`` performs the write as a real, gated, hash-chain-logged
``code.write_file`` Decision, while ``runtime=None`` (the default, used by the offline eval path)
keeps the existing raw ``Path.write_text`` behavior. No new write path is introduced.
"""

from __future__ import annotations

from pathlib import Path

from harness.system_builder import _extract_json, _jailed_write

# #EXT-058-REQ-3 Start
# TASK-5: v0 graph-DSL vocabulary, ported unchanged from `.jaros-data/dsl_probe.py`'s go/no-go
# probe (Gate 1: valid 7/7, right-core-block 7/7, stable round-trip 7/7) -- the five verified ADT
# leaves (EXT-056), common CLI/system primitives seen across the creation suite, and a `custom`
# escape hatch for irreducible novel logic (per design.md's "limit of the bet").
VOCAB = {
    # verified data-structure leaves (the ADT oracle's 5)
    "lru", "priority-queue", "ttl-store", "fifo", "ring-buffer",
    # common CLI/system primitives seen across the creation suite
    "kv-store", "calculator", "parser", "aggregator", "text-transform", "state-machine",
    "validator", "rate-limiter", "pub-sub", "graph", "stack", "codec", "datastore", "cli-tool",
    # escape hatch for irreducible novel logic
    "custom",
}


def parse_dsl(text: "str | None") -> "dict | None":
    """Deterministic, never-raises: pull the outermost ``{...}`` JSON object out of ``text``
    (reusing ``harness.system_builder._extract_json`` -- the same robust model-output JSON
    extraction ``build_system``'s plan parsing already relies on, no reinvention) and return it
    as a dict, or ``None`` when nothing parseable is found. Makes no model call; ``text`` is
    typically a small local model's NL->DSL completion, but this function itself never calls one."""
    g = _extract_json(text or "", "{", "}")
    return g if isinstance(g, dict) else None


def validate_dsl(g: "dict | None") -> "list[str]":
    """Deterministic, never-raises structural validation: every node needs an ``id`` and a
    ``class`` drawn from ``VOCAB``; every edge's ``from``/``to`` must reference a listed node id.
    Returns a list of human-readable defect strings (empty list = valid). Ported unchanged from
    the probe's ``validate_dsl``."""
    d: "list[str]" = []
    if not isinstance(g, dict):
        return ["not an object"]
    nodes = g.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return ["no nodes"]
    ids = []
    for n in nodes:
        if not isinstance(n, dict) or not n.get("id"):
            d.append("node missing id")
            continue
        ids.append(n["id"])
        if n.get("class") not in VOCAB:
            d.append(f"unknown class {n.get('class')!r}")
    for e in (g.get("edges") or []):
        if not isinstance(e, dict):
            d.append("bad edge")
            continue
        if e.get("from") not in ids or e.get("to") not in ids:
            d.append(f"edge refers to unknown node {e.get('from')}->{e.get('to')}")
    return d


def signature(g: "dict | None"):
    """Structural signature ignoring ids/params: the sorted node-class multiset + sorted
    class->class edges. Two graphs with the same signature pick the same building blocks wired
    the same way -- this is what ``equiv`` compares, and what a later DSL-diff (declarative
    modification) would key off. Ported unchanged from the probe's ``signature``; never raises
    (returns ``None`` for non-dict input)."""
    if not isinstance(g, dict):
        return None
    id2cls = {n.get("id"): n.get("class") for n in (g.get("nodes") or []) if isinstance(n, dict)}
    node_classes = tuple(sorted(c for c in id2cls.values() if c))
    edges = tuple(sorted(
        (id2cls.get(e.get("from")), id2cls.get(e.get("to")))
        for e in (g.get("edges") or []) if isinstance(e, dict)))
    return (node_classes, edges)


def equiv(g1: "dict | None", g2: "dict | None") -> bool:
    """Two graphs are equivalent iff they share the same structural ``signature`` (and neither
    is malformed). Ported unchanged from the probe's ``equiv``; never raises."""
    s1, s2 = signature(g1), signature(g2)
    return s1 is not None and s1 == s2
# #EXT-058-REQ-3 End


# #EXT-058-REQ-1 Start
# TASK-5: the verified leaf-library (REQ-1's "first governed slice") -- a registry of class name
# -> a VERIFIED single-file CLI template. Seeded with exactly one earned member, `ttl-store`
# (Gate 2, 2026-07-07: DSL-path 3/3 vs free-form 0/3 on `kv-store-ttl-cli`), per the earned-
# membership rule (a class is admitted only on measured, held-out per-class passing -- never by
# top-down declaration). `kv-store` maps to the SAME template: a key-value store with TTL expiry
# IS a ttl-store under this vocabulary (see `.jaros-data/dsl_gate2.py`'s `LEAF_TEMPLATES`), not a
# distinct leaf -- no duplication.
#
# HONESTY (Tenet 3, no oracle leak): authored from the ttl-store CONTRACT alone -- set/get/delete
# with integer-second TTL, a `ttl<=0` key treated as already expired, `ok`/value-or-`none` replies,
# one command per stdin line -- never from `kv-store-ttl-cli`'s (or any task's) hidden `checks`.
TTL_STORE_LEAF = '''\
import sys
import time


def main():
    store = {}  # key -> (value, expiry_epoch)  ; expiry <= now means expired
    for line in sys.stdin:
        parts = line.split()
        if not parts:
            continue
        cmd = parts[0]
        if cmd == "set" and len(parts) == 4:
            key, value, ttl = parts[1], parts[2], int(parts[3])
            expiry = 0.0 if ttl <= 0 else time.time() + ttl
            store[key] = (value, expiry)
            print("ok")
        elif cmd == "get" and len(parts) == 2:
            entry = store.get(parts[1])
            if entry is not None and time.time() < entry[1]:
                print(entry[0])
            else:
                print("none")
        elif cmd == "delete" and len(parts) == 2:
            store.pop(parts[1], None)
            print("ok")


if __name__ == "__main__":
    main()
'''

LEAF_LIBRARY = {
    "ttl-store": TTL_STORE_LEAF,
    "kv-store": TTL_STORE_LEAF,  # kv-store-with-ttl IS a ttl-store; same verified template
}
# #EXT-058-REQ-1 End


# #EXT-058-REQ-3 Start
# TASK-5: the single-leaf DSL->system deterministic path (REQ-3's scope for this task: single
# known-class node only -- multi-node composition is a later task's composer). Routes its one
# host write through `system_builder._jailed_write`, the SAME gated chokepoint
# `build_system`/`modify_system` already use (Tenet 1): a supplied `runtime` performs a real,
# gated, hash-chain-logged `code.write_file` Decision; `runtime=None` (default) keeps the existing
# raw-write eval-path convention, matching `system_builder`'s own pattern exactly (no new path).
def dsl_to_system(graph: "dict | None", root: "Path | str", runtime: "object | None" = None) -> bool:
    """Deterministic, never-raises: for a graph with exactly ONE node whose ``class`` is a known
    leaf in ``LEAF_LIBRARY``, write that leaf's verified template to ``root/main.py`` and return
    ``True``. Returns ``False`` for a multi-node graph, an unknown/missing class, malformed input,
    or a rejected/failed write -- never for the composer to fall back to (a later task), so a
    caller can safely try the deterministic DSL path first and degrade to free-form generation on
    ``False``. Makes no model call."""
    try:
        if not isinstance(graph, dict):
            return False
        nodes = graph.get("nodes")
        if not isinstance(nodes, list) or len(nodes) != 1:
            return False
        node = nodes[0]
        if not isinstance(node, dict):
            return False
        template = LEAF_LIBRARY.get(node.get("class"))
        if not template:
            return False
        err = _jailed_write(Path(root), "main.py", template, runtime=runtime)
        return err is None
    except Exception:  # pragma: no cover - defensive, mirrors module-wide never-raises discipline
        return False
# #EXT-058-REQ-3 End
