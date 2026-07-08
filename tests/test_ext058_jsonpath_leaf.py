"""EXT-058 TASK-10: offline (no model call) tests for the verified nested-JSON dotted-path query
leaf (``json-path-query``, REQ-7) -- the leaf-library's third earned member (after ``ttl-store``
and ``sql-query-engine``), covering the held-out ``json-path-query-cli`` creation class.

Covers TASK-10's required cases:
  - The emitted ``JSON_PATH_LEAF`` template PASSES ALL 4 of ``json-path-query-cli``'s independent,
    oracle-authored checks (reusing ``harness.system_suite._run_single_check`` -- no reimplemented
    grading logic, no oracle leak: the template under test never sees ``task.checks`` while being
    authored).
  - ``graph_dsl.leaf_for_spec`` returns ``"json-path-query"`` for a spec text that fingerprints the
    nested-JSON dotted-path grammar (the real ``json-path-query-cli`` sentence).
  - NO OVER-TRIGGER (the conservative co-occurrence rule): ``leaf_for_spec`` does NOT return
    ``"json-path-query"`` for a ``sqlite-persistent-kv-cli`` spec, a ``sql-mini-query-cli`` spec,
    or a ``kv-store-ttl-cli`` spec -- all keep resolving to their OWN correct leaf/None, exactly as
    before this task.
  - ``dsl_to_system`` emits the JSON-path leaf for a single ``json-path-query`` node.

Entirely offline and deterministic: no ``llm``/model call anywhere in this file.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from harness import graph_dsl
from harness.graph_dsl import JSON_PATH_LEAF, LEAF_LIBRARY, dsl_to_system, leaf_for_spec
from harness.system_suite import FIRST_SLICE, HARDER_SLICE, _run_single_check

PY = sys.executable

# #EXT-058-REQ-7 Start


def _find_task(name: str):
    return next(t for t in list(FIRST_SLICE) + list(HARDER_SLICE) if t.name == name)


# --- LEAF_LIBRARY registration ------------------------------------------------------------------

def test_leaf_library_seeded_with_json_path_query():
    assert LEAF_LIBRARY["json-path-query"] == JSON_PATH_LEAF


def test_json_path_query_in_vocab():
    assert "json-path-query" in graph_dsl.VOCAB


# --- the JSON-path leaf template PASSES json-path-query-cli's independent checks (no oracle leak)

def test_json_path_leaf_template_passes_json_path_query_cli_oracle():
    task = _find_task("json-path-query-cli")
    assert task.checks, "the task must carry its own independent checks"
    with tempfile.TemporaryDirectory(prefix="ext058_jsonpath_") as tmp:
        root = Path(tmp)
        (root / "main.py").write_text(JSON_PATH_LEAF, encoding="utf-8", newline="\n")
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results), f"json-path-query leaf template failed checks: {results}"
    assert len(results) == 4


# --- leaf_for_spec: positive classification + no-over-trigger negatives -------------------------

def test_leaf_for_spec_classifies_json_path_query_cli_spec():
    task = _find_task("json-path-query-cli")
    assert leaf_for_spec(task.sentence) == "json-path-query"


def test_leaf_for_spec_does_not_over_trigger_on_sqlite_persistent_kv_spec():
    """The sqlite-persistent-kv spec (mentions sqlite/database, never json/dotted) must never
    resolve to the JSON-path leaf."""
    sqlite_task = _find_task("sqlite-persistent-kv-cli")
    result = leaf_for_spec(sqlite_task.sentence)
    assert result != "json-path-query"


def test_leaf_for_spec_does_not_over_trigger_on_sql_mini_query_spec():
    """The sql-mini-query-cli spec must keep resolving to its OWN leaf, never the JSON-path leaf."""
    sql_task = _find_task("sql-mini-query-cli")
    result = leaf_for_spec(sql_task.sentence)
    assert result != "json-path-query"
    assert result == "sql-query-engine"


def test_leaf_for_spec_does_not_over_trigger_on_ttl_store_spec():
    """The ttl-store spec must keep resolving to its OWN leaf, never the JSON-path leaf."""
    ttl_task = _find_task("kv-store-ttl-cli")
    result = leaf_for_spec(ttl_task.sentence)
    assert result != "json-path-query"
    assert result == "ttl-store"


def test_leaf_for_spec_none_for_unrelated_spec():
    assert leaf_for_spec("Write a CLI that sums integers from stdin.") is None
    assert leaf_for_spec(None) is None
    assert leaf_for_spec("") is None


def test_is_json_path_spec_requires_all_signals_to_co_occur():
    # missing "json" -> not confident
    assert graph_dsl._is_json_path_spec(
        "resolves a dotted path against a nested document and queries it") is False
    # missing "dotted" -> not confident
    assert graph_dsl._is_json_path_spec(
        "a json config query tool that resolves a path against a document") is False
    # missing "resolve"/"query" -> not confident
    assert graph_dsl._is_json_path_spec(
        "a json tool that walks a dotted path through a document") is False
    # all three co-occur ("json" + "dotted" + "resolve") -> confident
    assert graph_dsl._is_json_path_spec(
        "a nested-JSON config query tool that resolves a DOTTED path like a.b.c") is True
    # all three co-occur ("json" + "dotted" + "query") -> confident
    assert graph_dsl._is_json_path_spec(
        "a json document dotted path query tool") is True


def test_is_json_path_spec_does_not_over_trigger_on_other_specs():
    sqlite_task = _find_task("sqlite-persistent-kv-cli")
    sql_task = _find_task("sql-mini-query-cli")
    ttl_task = _find_task("kv-store-ttl-cli")
    assert graph_dsl._is_json_path_spec(sqlite_task.sentence) is False
    assert graph_dsl._is_json_path_spec(sql_task.sentence) is False
    assert graph_dsl._is_json_path_spec(ttl_task.sentence) is False


# --- dsl_to_system -------------------------------------------------------------------------------

def test_dsl_to_system_emits_for_single_json_path_query_node():
    g = {"nodes": [{"id": "q", "class": "json-path-query", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_jsonpath_emit_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is True
        emitted = (root / "main.py").read_text(encoding="utf-8")
        assert emitted == JSON_PATH_LEAF


def test_dsl_to_system_emits_json_path_leaf_and_passes_oracle_end_to_end():
    task = _find_task("json-path-query-cli")
    g = {"nodes": [{"id": "q", "class": "json-path-query", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_jsonpath_e2e_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is True
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results)


# --- TASK-11 bugfix: the leaf must survive the no-arg usage probe -------------------------------
#
# MEASURED (on-Jetson): build_system's derived minimum acceptance runs a "usage/--help runs
# without crashing" check with NO extra argv. The emitted leaf used `sys.argv[1]` with no guard,
# so that probe CRASHED (rc=1, IndexError) and the leaf-repair adopt path rolled back to the
# broken free-form build every time (build_path stayed "free-form", class stayed 0/3) even though
# the leaf passes all 4 real checks (which always supply a path argument) in isolation.

def test_json_path_leaf_no_args_exits_cleanly():
    """Running the emitted leaf with NO command-line args must exit rc=0 and print `null` --
    not crash -- so it survives build_system's usage/--help minimum-acceptance probe."""
    import subprocess

    with tempfile.TemporaryDirectory(prefix="ext058_jsonpath_noargs_") as tmp:
        root = Path(tmp)
        main_py = root / "main.py"
        main_py.write_text(JSON_PATH_LEAF, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [PY, str(main_py)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert proc.returncode == 0, f"no-args run must not crash: stderr={proc.stderr!r}"
    assert proc.stdout.strip() == "null"
    assert proc.stderr == ""


def test_json_path_leaf_template_still_passes_all_checks_with_no_args_guard():
    """Belt-and-suspenders: re-confirm the no-args guard did not regress the 4 real checks (which
    always supply a path argument) -- must still be 4/4."""
    task = _find_task("json-path-query-cli")
    with tempfile.TemporaryDirectory(prefix="ext058_jsonpath_regress_") as tmp:
        root = Path(tmp)
        (root / "main.py").write_text(JSON_PATH_LEAF, encoding="utf-8", newline="\n")
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results), f"json-path-query leaf template failed checks: {results}"
    assert len(results) == 4
# #EXT-058-REQ-7 End
