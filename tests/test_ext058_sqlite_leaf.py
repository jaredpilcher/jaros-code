"""EXT-058 TASK-12: offline (no model call) tests for the verified persistent SQLite key-value
leaf (``sqlite-kv``, REQ-8) -- the leaf-library's fourth earned member (after ``ttl-store``,
``sql-query-engine``, and ``json-path-query``), covering the held-out ``sqlite-persistent-kv-cli``
creation class.

MEASURED (on-Jetson, this session): ``sqlite-persistent-kv-cli`` is 1/3 for gemma -- capable but
UNRELIABLE (sometimes a working store, sometimes a crashing one), and it correctly reports
``done=False`` on the crashing builds (no false-done), so the existing ``not done -> adopt leaf``
trigger (REQ-3) is sufficient on its own -- exactly the json-path leaf's (REQ-7) situation, not
the sql-mini leaf's (REQ-6 differential) one.

Covers TASK-12's required cases:
  - The emitted ``SQLITE_KV_LEAF`` template PASSES ALL 5 of ``sqlite-persistent-kv-cli``'s
    independent, oracle-authored checks (reusing ``harness.system_suite._run_single_check`` -- no
    reimplemented grading logic, no oracle leak), run against a SINGLE shared root so the
    cross-process persistence the checks exercise (separate subprocess invocations against the
    same ``store.db``) is genuinely exercised, exactly like the real acceptance run.
  - Running the emitted leaf with NO command-line args exits cleanly (rc=0, no traceback) -- the
    usage-probe case ``build_system``'s derived minimum acceptance drives (the exact gap that bit
    the json-path leaf, TASK-11/ce07ab1).
  - NO OVER-TRIGGER (the conservative co-occurrence rule): ``leaf_for_spec`` maps the real
    ``sqlite-persistent-kv-cli`` sentence to ``"sqlite-kv"``, while ``kv-store-ttl-cli`` still maps
    to ``"ttl-store"``, ``sql-mini-query-cli`` still maps to ``"sql-query-engine"``, and
    ``json-path-query-cli`` still maps to ``"json-path-query"`` -- all unchanged by this task. A
    sweep of every one of the suite's 24 held-out specs (``ALL_CREATION_TASKS``) confirms ONLY
    ``sqlite-persistent-kv-cli`` maps to the new leaf.
  - ``dsl_to_system`` emits the SQLite-kv leaf for a single ``sqlite-kv`` node.

Entirely offline and deterministic: no ``llm``/model call anywhere in this file.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from harness import graph_dsl
from harness.graph_dsl import LEAF_LIBRARY, SQLITE_KV_LEAF, dsl_to_system, leaf_for_spec
from harness.system_suite import ALL_CREATION_TASKS, FIRST_SLICE, HARDER_SLICE, _run_single_check

PY = sys.executable

# #EXT-058-REQ-8 Start


def _find_task(name: str):
    return next(t for t in list(FIRST_SLICE) + list(HARDER_SLICE) if t.name == name)


# --- LEAF_LIBRARY / VOCAB registration -----------------------------------------------------------

def test_leaf_library_seeded_with_sqlite_kv():
    assert LEAF_LIBRARY["sqlite-kv"] == SQLITE_KV_LEAF


def test_sqlite_kv_in_vocab():
    assert "sqlite-kv" in graph_dsl.VOCAB


# --- the SQLite-kv leaf template PASSES sqlite-persistent-kv-cli's independent checks (oracle) ---
#
# All 5 checks are run against ONE shared temp dir (root) -- exactly how `_run_single_check` is
# already driven for every sibling leaf test, and the SAME convention `run_creation_suite`/
# `_run_cli` use for a real build -- so `store.db`'s cross-process persistence (separate
# subprocess invocations, same cwd) is genuinely exercised, not merely simulated.

def test_sqlite_kv_leaf_template_passes_sqlite_persistent_kv_cli_oracle():
    task = _find_task("sqlite-persistent-kv-cli")
    assert task.checks, "the task must carry its own independent checks"
    assert len(task.checks) == 5
    with tempfile.TemporaryDirectory(prefix="ext058_sqlitekv_") as tmp:
        root = Path(tmp)
        (root / "main.py").write_text(SQLITE_KV_LEAF, encoding="utf-8", newline="\n")
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results), f"sqlite-kv leaf template failed checks: {results}"
    assert len(results) == 5


# --- usage-probe: no-args run must exit cleanly, not crash ---------------------------------------

def test_sqlite_kv_leaf_no_args_exits_cleanly():
    """Running the emitted leaf with NO command-line args must exit rc=0 with no traceback on
    stderr -- the exact usage-probe case build_system's derived minimum acceptance drives."""
    with tempfile.TemporaryDirectory(prefix="ext058_sqlitekv_noargs_") as tmp:
        root = Path(tmp)
        main_py = root / "main.py"
        main_py.write_text(SQLITE_KV_LEAF, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [PY, str(main_py)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(root),
        )
    assert proc.returncode == 0, f"no-args run must not crash: stderr={proc.stderr!r}"
    assert proc.stderr == ""


def test_sqlite_kv_leaf_help_flag_exits_cleanly():
    """`--help` is the second invocation build_system's usage probe drives -- must also not
    crash (it is neither `set` nor `get`, so it is simply a no-op, matching every other unknown
    invocation)."""
    with tempfile.TemporaryDirectory(prefix="ext058_sqlitekv_help_") as tmp:
        root = Path(tmp)
        main_py = root / "main.py"
        main_py.write_text(SQLITE_KV_LEAF, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [PY, str(main_py), "--help"],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(root),
        )
    assert proc.returncode == 0, f"--help run must not crash: stderr={proc.stderr!r}"
    assert proc.stderr == ""


def test_sqlite_kv_leaf_template_still_passes_all_checks_with_usage_guard():
    """Belt-and-suspenders: the usage guard did not regress the 5 real checks -- still 5/5."""
    task = _find_task("sqlite-persistent-kv-cli")
    with tempfile.TemporaryDirectory(prefix="ext058_sqlitekv_regress_") as tmp:
        root = Path(tmp)
        (root / "main.py").write_text(SQLITE_KV_LEAF, encoding="utf-8", newline="\n")
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results), f"sqlite-kv leaf template failed checks: {results}"
    assert len(results) == 5


# --- leaf_for_spec: positive classification + no-over-trigger negatives -------------------------

def test_leaf_for_spec_classifies_sqlite_persistent_kv_cli_spec():
    task = _find_task("sqlite-persistent-kv-cli")
    assert leaf_for_spec(task.sentence) == "sqlite-kv"


def test_leaf_for_spec_does_not_over_trigger_on_ttl_store_spec():
    """The ttl-store spec must keep resolving to its OWN leaf, never the SQLite-kv leaf."""
    ttl_task = _find_task("kv-store-ttl-cli")
    result = leaf_for_spec(ttl_task.sentence)
    assert result != "sqlite-kv"
    assert result == "ttl-store"


def test_leaf_for_spec_does_not_over_trigger_on_sql_mini_query_spec():
    """The sql-mini-query-cli spec mentions `sqlite3` (to forbid it) but must keep resolving to
    its OWN leaf, never the SQLite-kv leaf."""
    sql_task = _find_task("sql-mini-query-cli")
    result = leaf_for_spec(sql_task.sentence)
    assert result != "sqlite-kv"
    assert result == "sql-query-engine"


def test_leaf_for_spec_does_not_over_trigger_on_json_path_query_spec():
    """The json-path-query-cli spec must keep resolving to its OWN leaf, never the SQLite-kv
    leaf."""
    json_task = _find_task("json-path-query-cli")
    result = leaf_for_spec(json_task.sentence)
    assert result != "sqlite-kv"
    assert result == "json-path-query"


def test_leaf_for_spec_none_for_unrelated_spec():
    assert leaf_for_spec("Write a CLI that sums integers from stdin.") is None
    assert leaf_for_spec(None) is None
    assert leaf_for_spec("") is None


def test_leaf_for_spec_sweep_only_sqlite_persistent_kv_cli_maps_to_new_leaf():
    """Sweep every one of the suite's 24 held-out specs (``ALL_CREATION_TASKS``) and confirm the
    new leaf fires ONLY for the genuine ``sqlite-persistent-kv-cli`` spec -- no other class is
    disturbed by this task."""
    assert len(ALL_CREATION_TASKS) == 24
    matches = [t.name for t in ALL_CREATION_TASKS if leaf_for_spec(t.sentence) == "sqlite-kv"]
    assert matches == ["sqlite-persistent-kv-cli"]


def test_is_sqlite_kv_spec_requires_all_signals_to_co_occur():
    # missing "sqlite" -> not confident
    assert graph_dsl._is_sqlite_kv_spec(
        "a persistent key-value store that survives across separate runs") is False
    # missing "key-value" -> not confident
    assert graph_dsl._is_sqlite_kv_spec(
        "a persistent sqlite-backed store that survives across separate runs") is False
    # missing "persist" -> not confident
    assert graph_dsl._is_sqlite_kv_spec(
        "a sqlite-backed key-value store") is False
    # all three co-occur -> confident
    assert graph_dsl._is_sqlite_kv_spec(
        "a persistent key-value store backed by sqlite that survives separate runs") is True


def test_is_sqlite_kv_spec_does_not_over_trigger_on_other_specs():
    ttl_task = _find_task("kv-store-ttl-cli")
    sql_task = _find_task("sql-mini-query-cli")
    json_task = _find_task("json-path-query-cli")
    assert graph_dsl._is_sqlite_kv_spec(ttl_task.sentence) is False
    assert graph_dsl._is_sqlite_kv_spec(sql_task.sentence) is False
    assert graph_dsl._is_sqlite_kv_spec(json_task.sentence) is False


# --- dsl_to_system -------------------------------------------------------------------------------

def test_dsl_to_system_emits_for_single_sqlite_kv_node():
    g = {"nodes": [{"id": "store", "class": "sqlite-kv", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_sqlitekv_emit_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is True
        emitted = (root / "main.py").read_text(encoding="utf-8")
        assert emitted == SQLITE_KV_LEAF


def test_dsl_to_system_emits_sqlite_kv_leaf_and_passes_oracle_end_to_end():
    task = _find_task("sqlite-persistent-kv-cli")
    g = {"nodes": [{"id": "store", "class": "sqlite-kv", "params": {}}], "edges": []}
    with tempfile.TemporaryDirectory(prefix="ext058_sqlitekv_e2e_") as tmp:
        root = Path(tmp)
        assert dsl_to_system(g, root) is True
        results = [_run_single_check(c, root, None, PY) for c in task.checks]
    assert all(results)
# #EXT-058-REQ-8 End
