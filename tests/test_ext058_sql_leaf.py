"""EXT-058 TASK-8: offline (no model call) tests for the verified mini-SQL-engine leaf
(``sql-query-engine``, REQ-5) -- the leaf-library's second earned member (after ``ttl-store``),
covering the held-out ``sql-mini-query-cli`` creation class.

Covers TASK-8's required cases:
  - The emitted ``SQL_MINI_LEAF`` template PASSES ALL 3 of ``sql-mini-query-cli``'s independent,
    oracle-authored checks (reusing ``harness.system_suite._run_single_check`` -- no reimplemented
    grading logic, no oracle leak: the template under test never sees ``task.checks`` while being
    authored).
  - ``graph_dsl.leaf_for_spec`` returns ``"sql-query-engine"`` for a spec text that fingerprints
    the mini-SQL-engine grammar (the real ``sql-mini-query-cli`` sentence).
  - NO OVER-TRIGGER (the conservative co-occurrence rule): ``leaf_for_spec`` does NOT return
    ``"sql-query-engine"`` for a ``ttl-store`` spec (the real ``kv-store-ttl-cli`` sentence) or a
    plain ``kv-store`` spec (a self-authored get/put store spec, no SQL grammar at all) -- both
    keep resolving to their OWN correct leaf/None, exactly as before this task.
  - ``dsl_to_system`` emits the SQL leaf for a single ``sql-query-engine`` node.

Entirely offline and deterministic: no ``llm``/model call anywhere in this file.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from harness import graph_dsl
from harness.graph_dsl import LEAF_LIBRARY, SQL_MINI_LEAF, dsl_to_system, leaf_for_spec
from harness.system_suite import FIRST_SLICE, HARDER_SLICE, _run_single_check

PY = sys.executable

# #EXT-058-REQ-5 Start


def _find_task(name: str):
    return next(t for t in list(FIRST_SLICE) + list(HARDER_SLICE) if t.name == name)


# A self-authored plain kv-store spec (deliberately NOT the SQL grammar at all -- no "CREATE
# TABLE"/"SELECT" anywhere) -- the no-over-trigger negative case a plain get/put store must still
# resolve honestly (here: unclassified, since it names no ADT keyword either).
PLAIN_KV_STORE_SPEC = (
    "Write a single-file Python CLI program named main.py, a simple in-memory key-value store. "
    "It reads commands from standard input: `put <key> <value>` stores the value and prints "
    "`ok`; `get <key>` prints the stored value or `none` if absent."
)


# --- LEAF_LIBRARY registration ------------------------------------------------------------------

def test_leaf_library_seeded_with_sql_query_engine():
    assert LEAF_LIBRARY["sql-query-engine"] == SQL_MINI_LEAF


def test_sql_query_engine_in_vocab():
    assert "sql-query-engine" in graph_dsl.VOCAB


# --- the SQL leaf template PASSES sql-mini-query-cli's independent checks (no oracle leak) ------

def test_sql_mini_leaf_template_passes_sql_mini_query_cli_oracle():
    task = _find_task("sql-mini-query-cli")
    assert task.checks, "the task must carry its own independent checks"
    with tempfile.TemporaryDirectory(prefix="ext058_sql_") as tmp:
        root = Path(tmp)
        (root / "main.py").write_text(SQL_MINI_LEAF, encoding="utf-8", newline="\n")
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results), f"sql-query-engine leaf template failed checks: {results}"
    assert len(results) == 3


# --- leaf_for_spec: positive classification + no-over-trigger negatives -------------------------

def test_leaf_for_spec_classifies_sql_mini_query_cli_spec():
    task = _find_task("sql-mini-query-cli")
    assert leaf_for_spec(task.sentence) == "sql-query-engine"


def test_leaf_for_spec_does_not_over_trigger_on_ttl_store_spec():
    """The ttl-store spec must keep resolving to its OWN leaf, never the SQL leaf."""
    ttl_task = _find_task("kv-store-ttl-cli")
    result = leaf_for_spec(ttl_task.sentence)
    assert result != "sql-query-engine"
    assert result == "ttl-store"


def test_leaf_for_spec_does_not_over_trigger_on_plain_kv_store_spec():
    """A plain get/put store (no SQL grammar, no ADT keyword) must never map to the SQL leaf."""
    result = leaf_for_spec(PLAIN_KV_STORE_SPEC)
    assert result != "sql-query-engine"


def test_leaf_for_spec_none_for_unrelated_spec():
    assert leaf_for_spec("Write a CLI that sums integers from stdin.") is None
    assert leaf_for_spec(None) is None
    assert leaf_for_spec("") is None


def test_is_sql_mini_spec_requires_all_signals_to_co_occur():
    # missing SELECT -> not confident
    assert graph_dsl._is_sql_mini_spec("supports CREATE TABLE and INSERT INTO commands") is False
    # missing CREATE TABLE -> not confident
    assert graph_dsl._is_sql_mini_spec("a query engine that supports SELECT and INSERT") is False
    # missing INSERT and "query engine" phrase -> not confident
    assert graph_dsl._is_sql_mini_spec("supports CREATE TABLE and SELECT commands only") is False
    # all three co-occur -> confident
    assert graph_dsl._is_sql_mini_spec(
        "supports CREATE TABLE, INSERT INTO, and SELECT commands") is True
    # CREATE TABLE + SELECT + "query engine" phrase (no literal INSERT) -> confident
    assert graph_dsl._is_sql_mini_spec(
        "a minimal query engine supporting CREATE TABLE and SELECT") is True


# --- dsl_to_system -------------------------------------------------------------------------------

def test_dsl_to_system_emits_for_single_sql_query_engine_node():
    g = {"nodes": [{"id": "db", "class": "sql-query-engine", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_sql_emit_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is True
        emitted = (root / "main.py").read_text(encoding="utf-8")
        assert emitted == SQL_MINI_LEAF


def test_dsl_to_system_emits_sql_leaf_and_passes_oracle_end_to_end():
    task = _find_task("sql-mini-query-cli")
    g = {"nodes": [{"id": "db", "class": "sql-query-engine", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_sql_e2e_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is True
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results)
# #EXT-058-REQ-5 End
