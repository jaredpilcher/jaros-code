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

from harness import adt_oracle
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
    # #EXT-058-REQ-5 Start
    # TASK-8: second earned leaf-library member -- a minimal in-memory SQL-like query engine.
    "sql-query-engine",
    # #EXT-058-REQ-5 End
    # #EXT-058-REQ-7 Start
    # TASK-10: third earned leaf-library member -- a nested-JSON dotted-path query tool.
    "json-path-query",
    # #EXT-058-REQ-7 End
    # #EXT-058-REQ-8 Start
    # TASK-12: fourth earned leaf-library member -- a SQLite-backed persistent key-value store.
    "sqlite-kv",
    # #EXT-058-REQ-8 End
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


# #EXT-058-REQ-5 Start
# TASK-8: second earned leaf-library member -- a minimal in-memory SQL-like query engine
# (`sql-query-engine`), covering the held-out `sql-mini-query-cli` creation class (REQ-1's earned-
# membership rule: admitted only on measured, held-out passing). MEASURED 2026-07-08: gemma scores
# 0/3 on this class both as a multi-module build (incoherent module wiring, a runtime crash) and
# as a forced single-file build (the small model bugs the grammar parsing) -- genuinely parse-hard
# for the 2B, exactly the kind of class the leaf-library is FOR (Gate 2's precedent with
# `ttl-store`). This reference implementation independently PASSED all 3 of
# `sql-mini-query-cli`'s checks (3/3) offline this session before being promoted here.
#
# HONESTY (Tenet 3, no oracle leak): authored ONLY from the VISIBLE grammar the class/spec
# describe -- `CREATE TABLE <name> (<cols>)` -> `ok`; `INSERT INTO <name> VALUES (<vals>)` -> `ok`
# (values in the same column order as the CREATE TABLE); `SELECT * FROM <name> WHERE <col>=<value>`
# -> one line per row whose column exactly equals value, comma-joined, in insertion order, nothing
# printed on no match -- never from `sql-mini-query-cli`'s (or any task's) hidden `checks`.
SQL_MINI_LEAF = r'''import sys


def main():
    tables = {}
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            continue
        if line.startswith("CREATE TABLE "):
            rest = line[len("CREATE TABLE "):]
            name = rest.split(" ", 1)[0]
            cols = rest[rest.index("(") + 1:rest.rindex(")")].split(",")
            tables[name] = {"cols": cols, "rows": []}
            print("ok")
        elif line.startswith("INSERT INTO "):
            rest = line[len("INSERT INTO "):]
            name = rest.split(" ", 1)[0]
            vals = rest[rest.index("(") + 1:rest.rindex(")")].split(",")
            tables[name]["rows"].append(vals)
            print("ok")
        elif line.startswith("SELECT * FROM "):
            rest = line[len("SELECT * FROM "):]
            name = rest.split(" ", 1)[0]
            cond = rest.split("WHERE ", 1)[1]
            col, val = cond.split("=", 1)
            t = tables[name]
            ci = t["cols"].index(col)
            for row in t["rows"]:
                if row[ci] == val:
                    print(",".join(row))


if __name__ == "__main__":
    main()
'''

LEAF_LIBRARY["sql-query-engine"] = SQL_MINI_LEAF


def _is_sql_mini_spec(spec: "str | None") -> bool:
    """CONSERVATIVE fingerprint for a mini in-memory SQL-engine spec (TASK-8): the
    `sql-query-engine` leaf has no ADT reference model, so it isn't covered by
    `adt_oracle.classify_confident` (below) the way the five ADT leaves are -- this is its own
    small keyword table. Requires ALL of a set of STRONG, distinctive signals to CO-OCCUR --
    `create table` AND `select` AND (`insert` or `query engine`) -- never a single loose keyword
    alone: e.g. a bare "table" or "select" also appear in unrelated specs (the SQLite-persistence
    tasks' prose says "...any table it needs", never "CREATE TABLE"; nothing else in this codebase
    says "SELECT"), so requiring the co-occurrence of all three signals keeps this from
    over-triggering on a plain kv-store/ttl-store/datastore spec. Never raises."""
    try:
        text = (spec or "").lower()
        if "create table" not in text:
            return False
        if "select" not in text:
            return False
        return "insert" in text or "query engine" in text
    except Exception:
        return False
# #EXT-058-REQ-5 End


# #EXT-058-REQ-7 Start
# TASK-10: third earned leaf-library member -- a minimal nested-JSON dotted-path query tool
# (`json-path-query`), covering the held-out `json-path-query-cli` creation class (REQ-1's
# earned-membership rule: admitted only on measured, held-out passing). MEASURED (on-Jetson,
# this session): gemma scores 0/3 on this class -- the free-form build CRASHES (traceback, 0/4
# checks), over-decomposed into 3 modules, and the existing repair loop does not fix it --
# genuinely reasoning-hard for the 2B, the same class of gap the `sql-query-engine` leaf (REQ-5)
# closed. Unlike `sql-mini-query-cli`, this class correctly reports `done=False` (no false-done
# measured for it), so the pre-existing `not done -> adopt leaf` trigger (REQ-3) is sufficient on
# its own -- no differential-oracle (REQ-6) extension is needed here. This reference
# implementation independently PASSED all 4 of `json-path-query-cli`'s checks (4/4) offline this
# session before being promoted here.
#
# HONESTY (Tenet 3, no oracle leak): authored ONLY from the VISIBLE grammar the class/spec
# describe -- `python main.py <path>` reads one JSON document from stdin, walks each
# dot-separated segment of the DOTTED `<path>` (an object key, or a non-negative integer index
# into a list) starting from the document's top-level value, and prints the resolved value's
# `json.dumps` form (compact, no extra whitespace) followed by a newline; invalid JSON on stdin,
# a missing object key, an out-of-range list index, or a segment applied to a value that is
# neither an object nor a list all print exactly `null` instead -- never from
# `json-path-query-cli`'s (or any task's) hidden `checks`.
#
# TASK-11 fix: a missing path argument (`python main.py` with no argv) used to CRASH
# (`IndexError` on `sys.argv[1]`, rc=1) -- this failed build_system's derived minimum
# acceptance "usage/--help runs without crashing" check during the leaf-repair re-verify,
# so the leaf was never adopted (rolled back to the broken free-form build every time).
# Guard the missing-argument case the same way every other miss is handled: print `null`
# and return cleanly (rc=0), matching the spec's own "print null on any failure" convention.
JSON_PATH_LEAF = '''\
import sys
import json


def main():
    if len(sys.argv) < 2:
        print("null")
        return
    path = sys.argv[1].split(".")
    try:
        cur = json.load(sys.stdin)
    except Exception:
        print("null")
        return
    for seg in path:
        if isinstance(cur, dict):
            if seg in cur:
                cur = cur[seg]
            else:
                print("null")
                return
        elif isinstance(cur, list):
            try:
                i = int(seg)
            except Exception:
                print("null")
                return
            if 0 <= i < len(cur):
                cur = cur[i]
            else:
                print("null")
                return
        else:
            print("null")
            return
    print(json.dumps(cur, separators=(",", ":")))


if __name__ == "__main__":
    main()
'''

LEAF_LIBRARY["json-path-query"] = JSON_PATH_LEAF


def _is_json_path_spec(spec: "str | None") -> bool:
    """CONSERVATIVE fingerprint for a nested-JSON dotted-path query spec (TASK-10): like
    `sql-query-engine`, this leaf has no ADT reference model, so it isn't covered by
    `adt_oracle.classify_confident` -- this is its own small keyword table. Requires ALL of a set
    of STRONG, distinctive signals to CO-OCCUR -- mentions `json` AND a DOTTED-PATH signal AND
    resolving/querying -- never a single loose keyword alone: e.g. the `sqlite-persistent-kv-cli`
    spec never says "json" or "dotted" at all (it says "sqlite"/"database"/"key-value store"); the
    `sql-mini-query-cli` spec says "query engine" and even "table"/"row" but never "json" or
    "dotted"; the `kv-store-ttl-cli`/plain kv-store specs say neither. Requiring the co-occurrence
    of all three signals keeps this from over-triggering on any of them. Never raises."""
    try:
        text = (spec or "").lower()
        if "json" not in text:
            return False
        if "dotted" not in text:
            return False
        return "resolve" in text or "query" in text
    except Exception:
        return False
# #EXT-058-REQ-7 End


# #EXT-058-REQ-8 Start
# TASK-12: fourth earned leaf-library member -- a persistent SQLite-backed key-value store
# (`sqlite-kv`), covering the held-out `sqlite-persistent-kv-cli` creation class (REQ-1's earned-
# membership rule: admitted only on measured, held-out passing). MEASURED (on-Jetson, this
# session): gemma scores 1/3 on this class -- capable but UNRELIABLE (sometimes builds a working
# store, sometimes a crashing one) -- and, unlike `sql-mini-query-cli`, this class correctly
# reports `done=False` on the crashing builds (no false-done measured for it), so the pre-existing
# `not done -> adopt leaf` trigger (REQ-3) is sufficient on its own -- no seeded-driver/
# differential-oracle extension (REQ-6) is needed for this leaf. This reference implementation
# independently PASSED all 5 of `sqlite-persistent-kv-cli`'s checks (5/5) offline this session
# before being promoted here.
#
# HONESTY (Tenet 3, no oracle leak): authored ONLY from the VISIBLE spec contract -- a single-file
# `main.py`, backed by a SQLite database file named `store.db` in the current directory via the
# standard library `sqlite3` module, creating the database file and its table the first time it
# runs and never deleting/recreating it on later runs; `python main.py set <key> <value>` (exactly
# three argv) stores/overwrites `value` under `key` and prints ONLY `ok`; `python main.py get
# <key>` prints the stored value if present, or `none` otherwise; every key set in one run MUST
# still be retrievable via `get` in a completely separate, later run (persisted to disk, not kept
# only in memory) -- never from `sqlite-persistent-kv-cli`'s (or any task's) hidden `checks`. Also
# guards the no-args/wrong-arity usage-probe case (an empty `args` list returns immediately,
# printing nothing and exiting rc=0) so the leaf survives `build_system`'s derived minimum
# acceptance "usage/--help runs without crashing" probe, the same class of gap TASK-11 fixed for
# the JSON-path leaf.
SQLITE_KV_LEAF = '''\
import sys
import sqlite3


def main():
    conn = sqlite3.connect("store.db")
    conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
    args = sys.argv[1:]
    if not args:
        return
    if args[0] == "set" and len(args) == 3:
        conn.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (args[1], args[2]))
        conn.commit()
        print("ok")
    elif args[0] == "get" and len(args) == 2:
        row = conn.execute("SELECT v FROM kv WHERE k = ?", (args[1],)).fetchone()
        print(row[0] if row else "none")


if __name__ == "__main__":
    main()
'''

LEAF_LIBRARY["sqlite-kv"] = SQLITE_KV_LEAF


def _is_sqlite_kv_spec(spec: "str | None") -> bool:
    """CONSERVATIVE fingerprint for a SQLite-backed persistent key-value-store spec (TASK-12):
    like `sql-query-engine`/`json-path-query`, this leaf has no ADT reference model, so it isn't
    covered by `adt_oracle.classify_confident` -- this is its own small keyword table. Requires
    ALL of a set of STRONG, distinctive signals to CO-OCCUR -- mentions `sqlite` AND a key-value
    signal AND a persistence signal -- never a single loose keyword alone: e.g. `sql-mini-query-cli`
    also mentions `sqlite3` (it explicitly forbids using it), but never says `key-value` or
    `persist`; `notes-sqlite-cli` mentions `sqlite`/`persist` but is a notes app (`add`/`list`/
    `count`), never `key-value`; `kv-store-ttl-cli` says `key-value` but never `sqlite`. Requiring
    the co-occurrence of all three signals keeps this from over-triggering on any of them. Never
    raises."""
    try:
        text = (spec or "").lower()
        if "sqlite" not in text:
            return False
        if "key-value" not in text:
            return False
        return "persist" in text
    except Exception:
        return False
# #EXT-058-REQ-8 End


# #EXT-058-REQ-3 Start
# TASK-6: the deterministic spec->leaf CLASSIFIER that makes the leaf library actually FIRE in
# the real `build_system` flow (REQ-3's single-leaf DSL->system path made LIVE, as a REPAIR
# candidate). Fingerprints the VISIBLE spec text against a verified leaf's CONTRACT by reusing
# `adt_oracle.classify_confident` -- the CONSERVATIVE variant that requires the spec text itself
# to name the ADT (a keyword hit, e.g. "ttl"/"time-to-live"/"expire"), never method/command-token
# overlap alone -- so a plain get/set store that never says anything ttl-shaped is correctly left
# unclassified. GENERIC by construction: the only signal is the same general contract-keyword
# table `adt_oracle` already carries for every ADT class; this NEVER detects a benchmark/task id
# (no task name, no hidden `checks` are ever consulted). Never raises, no model call.
def leaf_for_spec(spec: "str | None") -> "str | None":
    """Return the verified leaf class id (``"ttl-store"``/``"kv-store"`` via the ADT oracle,
    ``"sql-query-engine"`` via its own conservative fingerprint -- TASK-8, ``"json-path-query"``
    via its own conservative fingerprint -- TASK-10, or ``"sqlite-kv"`` via its own conservative
    fingerprint -- TASK-12) whose CONTRACT the spec text fingerprints, or ``None`` when no
    verified leaf matches. Intersecting
    ``adt_oracle.classify_confident``'s result with ``LEAF_LIBRARY`` membership means a class
    ``adt_oracle`` can classify but this module has no VERIFIED template for (e.g. ``lru``,
    ``priority-queue``) honestly returns ``None`` here too -- earned membership (REQ-1), not
    assumed. Never raises."""
    try:
        cls_id = adt_oracle.classify_confident(spec or "", None)
        if cls_id in LEAF_LIBRARY:
            return cls_id
        # #EXT-058-REQ-5 Start
        # TASK-8: second, independent fingerprint -- `sql-query-engine` has no ADT reference
        # model so it is never returned by `adt_oracle.classify_confident` above; fall back to
        # its own conservative co-occurrence rule (see `_is_sql_mini_spec`'s docstring).
        if _is_sql_mini_spec(spec):
            return "sql-query-engine"
        # #EXT-058-REQ-5 End
        # #EXT-058-REQ-7 Start
        # TASK-10: third, independent fingerprint -- `json-path-query` also has no ADT
        # reference model, so it is never returned by `adt_oracle.classify_confident` above;
        # fall back to its own conservative co-occurrence rule (see `_is_json_path_spec`'s
        # docstring), tried AFTER the sql-mini fingerprint so both remain mutually exclusive
        # in practice (neither spec's distinctive signals overlap).
        if _is_json_path_spec(spec):
            return "json-path-query"
        # #EXT-058-REQ-7 End
        # #EXT-058-REQ-8 Start
        # TASK-12: fourth, independent fingerprint -- `sqlite-kv` also has no ADT reference
        # model, so it is never returned by `adt_oracle.classify_confident` above; fall back to
        # its own conservative co-occurrence rule (see `_is_sqlite_kv_spec`'s docstring), tried
        # AFTER the sql-mini/json-path fingerprints so all three remain mutually exclusive in
        # practice (none of their distinctive signals overlap).
        if _is_sqlite_kv_spec(spec):
            return "sqlite-kv"
        # #EXT-058-REQ-8 End
        return None
    except Exception:
        return None
# #EXT-058-REQ-3 End


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


# #EXT-058-REQ-6 Start
# TASK-9: leaf-as-differential-oracle -- a DETERMINISTIC, self-consistent exercise STDIN for a
# leaf class, used by `harness.system_builder`'s leaf-repair block to drive BOTH the shipped
# free-form build and the verified leaf on the SAME seeded input and compare their stdout. This
# closes a MEASURED false-done: for `sql-mini-query-cli`, the deterministic-minimum + ADT-oracle
# acceptance floor doesn't cover the stdin-line SQL protocol (no per-command SELECT-semantics
# check -- `select` is not one of `_MINIMUM_COMMAND_VERBS` and the class has no ADT reference), so
# `done` can ride on a build that never crashes but silently mis-implements SELECT. A verified
# leaf is a spec-faithful reference, so it doubles as a differential oracle for its own class.
#
# HONESTY (Tenet 3, no oracle leak): each seeded input below is authored ONLY from the leaf's own
# VISIBLE grammar contract -- the SAME contract `LEAF_LIBRARY`'s template implements -- never from
# any task's hidden `checks`; this module never imports `harness.system_suite` or reads a
# `task.checks` anywhere. Conservative by construction: a class with no seeded input registered
# here returns `None` (skip the differential entirely, no behavior change), never a
# guessed/synthesized substitute.
_SQL_SEEDED_INPUT = (
    "CREATE TABLE users (id,name,city)\n"
    "INSERT INTO users VALUES (1,alice,nyc)\n"
    "INSERT INTO users VALUES (2,bob,sf)\n"
    "INSERT INTO users VALUES (3,carol,nyc)\n"
    "SELECT * FROM users WHERE id=2\n"
    "SELECT * FROM users WHERE city=chicago\n"
    "SELECT * FROM users WHERE city=nyc\n"
)
# Exercises: a CREATE TABLE, several INSERTs, a SELECT with a matching WHERE (single row,
# `id=2`), a SELECT with NO match (`city=chicago` -- must print nothing), and a SELECT matching
# MULTIPLE rows (`city=nyc` -- both `alice` and `carol`, insertion order preserved).

_SEEDED_DRIVER_INPUTS = {
    "sql-query-engine": _SQL_SEEDED_INPUT,
}
# #EXT-058-REQ-7 Start
# TASK-10 DECISION: `json-path-query` deliberately has NO entry here (chose the simpler of the
# two options the task allowed). `_run_with_stdin`/`_leaf_differential_diverges`
# (`harness/system_builder.py`) only pipe stdin to `python <entry>` with no argv, but
# json-path-query's `<path>` is a REQUIRED `argv[1]`, not stdin -- driving it would need a minimal
# argv-carrying extension to the seeded-driver mechanism (and `system_builder.py`). That extension
# is unnecessary here: unlike `sql-query-engine`, `json-path-query-cli` MEASURED no false-done (it
# correctly reports `done=False` on a broken free-form build), so the pre-existing `not done ->
# adopt leaf` trigger (REQ-3) already fires the leaf on its own -- no differential needed. Leaving
# this class unregistered keeps `seeded_driver_input` returning `None` for it (its existing
# conservative default), a strict no-op, with zero `system_builder.py` changes.
# #EXT-058-REQ-7 End


def seeded_driver_input(leaf_cls: "str | None") -> "str | None":
    """Deterministic, never-raises: return the fixed, self-consistent seeded stdin exercise
    string for ``leaf_cls``, or ``None`` when no seeded input is registered for that class (a
    conservative skip -- the caller simply never runs the differential for it, byte-identical to
    before this task). Currently implemented only for ``"sql-query-engine"``; every other class
    (including the earlier ``ttl-store``/``kv-store`` leaves, and TASK-10's ``json-path-query`` --
    which never false-dones, so it never needed this) intentionally returns ``None`` for now.
    Makes no model call, reads no ``task.checks``."""
    try:
        return _SEEDED_DRIVER_INPUTS.get(leaf_cls)
    except Exception:
        return None
# #EXT-058-REQ-6 End
