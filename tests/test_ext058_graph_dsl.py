"""EXT-058 TASK-5: offline (no model call) tests for `harness/graph_dsl.py` -- the governed
graph-DSL machinery ported from the PROVEN prototype (`.jaros-data/dsl_probe.py` +
`.jaros-data/dsl_gate2.py`, both go/no-go gates PASSED 2026-07-07).

Covers:
  - `parse_dsl` / `validate_dsl`: parse-from-text, unknown-class rejection, dangling-edge
    rejection, empty-graph rejection ("cycle-empty-roots" per the task step: a graph with no
    nodes has no valid roots and must be rejected, never silently accepted).
  - `signature` / `equiv`: id/param invariance (two structurally-identical graphs with different
    ids/param values/key order are equivalent) and structural discrimination (different node
    classes or edges are NOT equivalent).
  - The `ttl-store` leaf template PASSES every one of `kv-store-ttl-cli`'s independent,
    oracle-authored checks (reusing `harness.system_suite._run_single_check` -- no reimplemented
    grading logic, no oracle leak: the template under test never sees `task.checks`).
  - `dsl_to_system` emits for a single known-leaf node and declines multi-node / unknown-class /
    malformed graphs.

Entirely offline and deterministic: no `llm`/model call anywhere in this file.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from harness.graph_dsl import (
    LEAF_LIBRARY,
    TTL_STORE_LEAF,
    VOCAB,
    dsl_to_system,
    equiv,
    parse_dsl,
    signature,
    validate_dsl,
)
from harness.system_suite import FIRST_SLICE, HARDER_SLICE, _run_single_check

PY = sys.executable


# --- parse_dsl -------------------------------------------------------------------------------

def test_parse_dsl_extracts_json_object_from_prose():
    raw = 'Sure, here is the graph:\n```json\n{"nodes": [{"id": "a", "class": "ttl-store"}], "edges": []}\n```\n'
    g = parse_dsl(raw)
    assert isinstance(g, dict)
    assert g["nodes"][0]["class"] == "ttl-store"


def test_parse_dsl_returns_none_on_garbage():
    assert parse_dsl("not json at all") is None
    assert parse_dsl("") is None
    assert parse_dsl(None) is None


# --- validate_dsl ------------------------------------------------------------------------------

def test_validate_dsl_accepts_wellformed_graph():
    g = {"nodes": [{"id": "store", "class": "ttl-store", "params": {}}], "edges": []}
    assert validate_dsl(g) == []


def test_validate_dsl_rejects_unknown_class():
    g = {"nodes": [{"id": "x", "class": "quantum-flux-capacitor"}], "edges": []}
    defects = validate_dsl(g)
    assert defects
    assert any("unknown class" in d for d in defects)


def test_validate_dsl_rejects_empty_node_list():
    """No nodes = no roots at all -- must be an honest defect, never silently valid."""
    assert validate_dsl({"nodes": [], "edges": []}) == ["no nodes"]
    assert validate_dsl({}) == ["no nodes"]


def test_validate_dsl_rejects_dangling_edge():
    g = {
        "nodes": [{"id": "a", "class": "rate-limiter"}, {"id": "b", "class": "ttl-store"}],
        "edges": [{"from": "a", "to": "nonexistent-node"}],
    }
    defects = validate_dsl(g)
    assert any("edge refers to unknown node" in d for d in defects)


def test_validate_dsl_never_raises_on_malformed_input():
    assert validate_dsl(None) == ["not an object"]
    assert validate_dsl("a string, not a dict") == ["not an object"]
    assert validate_dsl({"nodes": ["not-a-dict-node"], "edges": []}) == ["node missing id"]
    assert validate_dsl({"nodes": [{"id": "a", "class": "ttl-store"}], "edges": ["not-a-dict-edge"]}) == \
        ["bad edge"]


# --- signature / equiv (structural, id/param-invariant) ----------------------------------------

def test_signature_ignores_ids_and_params():
    g1 = {"nodes": [{"id": "cache", "class": "ttl-store", "params": {"capacity": 3}}], "edges": []}
    g2 = {"nodes": [{"id": "totally-different-name", "class": "ttl-store", "params": {}}], "edges": []}
    assert signature(g1) == signature(g2)
    assert equiv(g1, g2)


def test_equiv_true_for_relabeled_multinode_graph():
    ref = {
        "nodes": [{"id": "limiter", "class": "rate-limiter", "params": {}},
                  {"id": "cache", "class": "ttl-store", "params": {}}],
        "edges": [{"from": "limiter", "to": "cache", "kind": "guards"}],
    }
    relabeled = {
        "nodes": [{"id": "c", "class": "ttl-store", "params": {"x": 1}},
                  {"id": "l", "class": "rate-limiter", "params": {"y": 2}}],
        "edges": [{"from": "l", "to": "c", "kind": "guards"}],
    }
    assert equiv(ref, relabeled)


def test_equiv_false_for_different_structure():
    a = {"nodes": [{"id": "x", "class": "ttl-store"}], "edges": []}
    b = {"nodes": [{"id": "x", "class": "lru"}], "edges": []}
    assert not equiv(a, b)

    c = {
        "nodes": [{"id": "l", "class": "rate-limiter"}, {"id": "s", "class": "ttl-store"}],
        "edges": [{"from": "l", "to": "s", "kind": "guards"}],
    }
    d = {
        "nodes": [{"id": "l", "class": "rate-limiter"}, {"id": "s", "class": "ttl-store"}],
        "edges": [],
    }
    assert not equiv(c, d)


def test_equiv_false_when_either_graph_invalid():
    assert not equiv(None, {"nodes": [{"id": "x", "class": "ttl-store"}], "edges": []})
    assert not equiv({"nodes": [{"id": "x", "class": "ttl-store"}], "edges": []}, "garbage")


# --- VOCAB / LEAF_LIBRARY sanity ----------------------------------------------------------------

def test_vocab_contains_ttl_store_and_escape_hatch():
    assert "ttl-store" in VOCAB
    assert "kv-store" in VOCAB
    assert "custom" in VOCAB


def test_leaf_library_seeded_with_ttl_store_and_kv_store_alias():
    assert LEAF_LIBRARY["ttl-store"] == TTL_STORE_LEAF
    # kv-store-with-ttl IS a ttl-store -- same verified template, no duplication.
    assert LEAF_LIBRARY["kv-store"] == TTL_STORE_LEAF


# --- the ttl-store template PASSES kv-store-ttl-cli's independent checks (no oracle leak) -------

def _find_task(name: str):
    return next(t for t in list(FIRST_SLICE) + list(HARDER_SLICE) if t.name == name)


def test_ttl_store_template_passes_kv_store_ttl_cli_oracle():
    task = _find_task("kv-store-ttl-cli")
    assert task.checks, "the task must carry its own independent checks"
    with tempfile.TemporaryDirectory(prefix="ext058_") as tmp:
        root = Path(tmp)
        (root / "main.py").write_text(TTL_STORE_LEAF, encoding="utf-8", newline="\n")
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results), f"ttl-store leaf template failed checks: {results}"


# --- dsl_to_system -------------------------------------------------------------------------------

def test_dsl_to_system_emits_for_single_ttl_store_node():
    g = {"nodes": [{"id": "store", "class": "ttl-store", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_emit_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is True
        emitted = (root / "main.py").read_text(encoding="utf-8")
        assert emitted == TTL_STORE_LEAF


def test_dsl_to_system_emits_for_kv_store_alias_and_passes_oracle():
    """The DSL routes a `kv-store` node (with TTL semantics) to the same verified template, and
    the emitted file independently passes the task's real oracle end-to-end."""
    task = _find_task("kv-store-ttl-cli")
    g = {"nodes": [{"id": "store", "class": "kv-store", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_kv_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is True
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results)


def test_dsl_to_system_declines_multi_node_graph():
    g = {
        "nodes": [{"id": "limiter", "class": "rate-limiter", "params": {}},
                  {"id": "cache", "class": "ttl-store", "params": {}}],
        "edges": [{"from": "limiter", "to": "cache", "kind": "guards"}],
    }
    with tempfile.TemporaryDirectory(prefix="ext058_multi_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is False
        assert not (root / "main.py").exists()


def test_dsl_to_system_declines_unknown_class():
    g = {"nodes": [{"id": "x", "class": "custom", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_unknown_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is False
        assert not (root / "main.py").exists()


def test_dsl_to_system_never_raises_on_malformed_input():
    with tempfile.TemporaryDirectory(prefix="ext058_bad_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(None, root) is False
        assert dsl_to_system({}, root) is False
        assert dsl_to_system({"nodes": "not-a-list"}, root) is False
        assert dsl_to_system({"nodes": ["not-a-dict"]}, root) is False
