"""EXT-060 TASK-1: real-systems capability suite scaffold (leaves-OFF North-Star instrument, REQ-1)
+ the first concrete task, a CSV->JSON group-by ETL system graded by ``harness.fs_oracle`` (REQ-2).

CONTEXT (see ``.jarify/EXT-060/design.md``): EXT-058/EXT-059 built a verified LEAF LIBRARY
(``harness.graph_dsl``) and an independent verification substrate (``harness.fs_oracle``,
``harness.system_suite``'s exact-eq check variants). Neither of those specs measures REAL systems
built the GENERIC free-form way -- a suite that lets the leaf path silently fire would just be
re-measuring the leaf library's own reference implementations, which is dishonest (Tenet 3): a
leaf-produced green proves nothing about the model's OWN capability. This module is the LEAVES-OFF
counterpart -- every task here is picked so no verified leaf template exists for it, the runner
ASSERTS that stays true (both statically, via ``harness.graph_dsl.leaf_for_spec``, before a build is
even attempted, and against the actual build result's ``build_path``), and a leaf-produced result is
always scored a FAILURE, never a pass.

Two-plane split: this module drives ``harness.system_builder.build_system`` (which may itself call a
model) and then grades the result via a DETERMINISTIC, model-free oracle dispatch -- never the
model's own self-derived acceptance checklist, never the build's own stdout claim. ``run_real_systems_
suite`` NEVER raises overall: any per-task failure (a leaves-OFF violation, a build exception, a
missing/broken entrypoint, an oracle mismatch) is recorded as that task's honest ``accepted=False``
and the suite moves on -- one bad task never aborts the whole measurement run.

Honesty (Tenet 3, no oracle leak): every task's ``sentence`` fully specifies its CLI contract (paths,
column/field names, output shape) -- the oracle's expected values are DERIVED from that same visible
contract, never leaked into the build prompt via any other channel, and never read from a hidden
reference implementation the model could not see.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# #EXT-060-REQ-1 Start
# TASK-1: reuse (not reimplement) the landed verification substrate -- the deterministic filesystem
# oracle (EXT-059 REQ-1), the exact-stdout check variant (EXT-059 REQ-2, via `system_suite`'s own
# dispatcher), the leaves-OFF fingerprint (EXT-058 REQ-3), and the existing `build_system` pipeline.
from harness.fs_oracle import DEFAULT_TIMEOUT_S as FS_DEFAULT_TIMEOUT_S
from harness.fs_oracle import run_and_inspect, seed_tree
from harness.graph_dsl import leaf_for_spec
from harness.system_builder import build_system
from harness.system_suite import _run_check_variant

# #EXT-060-REQ-7 Start
# TASK-6: the MODIFY half reuses (not reimplements) `harness.system_builder.modify_system` --
# the SAME regression-gated modify-from-a-sentence pipeline EXT-036 REQ-14 already landed.
from harness.system_builder import modify_system
# #EXT-060-REQ-7 End

# #EXT-060-REQ-3 Start
# TASK-2: reuse (not reimplement) the deterministic import-and-call oracle (EXT-059 REQ-3) for the
# reusable-library ("import" oracle_kind) grading path -- never a fresh subprocess convention.
from harness.import_driver import drive_import

IMPORT_DEFAULT_TIMEOUT_S = 15.0
# #EXT-060-REQ-3 End

# #EXT-060-REQ-9 Start
# TASK-8: reuse (not reimplement) the already-landed server oracle (EXT-036 REQ-22/REQ-47) for the
# "service" oracle_kind's real-HTTP grading, and the already-landed sqlite datastore oracle (EXT-039
# REQ-1) for its INDEPENDENT post-teardown persistence assertion.
from harness.datastore_oracle import count_all_rows, detect_sqlite_datastore
from harness.server_oracle import serve_and_check_stdlib

SERVICE_DEFAULT_STARTUP_TIMEOUT_S = 15.0
SERVICE_DEFAULT_REQUEST_TIMEOUT_S = 5.0
# #EXT-060-REQ-9 End

# #EXT-060-REQ-11 Start
# TASK-9: reuse (not reimplement) the already-landed agent-loop oracle (EXT-059 REQ-6) for the
# first AGENT-shaped ("agent" oracle_kind) grading path -- never a new stub-model/tool-sandbox
# mechanism, never a real model/Jetson call.
from harness.agent_oracle import check_agent, drive_agent, final_turn, tool_call_turn
# #EXT-060-REQ-11 End

# #EXT-060-REQ-13 Start
# TASK-10: reuse (not reimplement) the already-landed state-machine/lifecycle oracle (EXT-059
# REQ-7) for the first LIFECYCLE-shaped ("state_machine" oracle_kind) grading path -- never a new
# driving mechanism.
from harness.state_machine_oracle import grade_state_machine
# #EXT-060-REQ-13 End

# #EXT-060-REQ-15 Start
# TASK-11: reuse (not reimplement) the already-landed conservation/no-oversell oracle (EXT-059
# REQ-8) for the first INVENTORY-shaped ("conservation" oracle_kind) grading path -- never a new
# driving mechanism.
from harness.conservation_oracle import grade_conservation
# #EXT-060-REQ-15 End

# #EXT-060-REQ-17 Start
# TASK-12: reuse (not reimplement) the already-landed double-entry-balance oracle (EXT-059
# REQ-9) for the first FINTECH-LEDGER-shaped ("double_entry" oracle_kind) grading path -- never
# a new driving mechanism.
from harness.double_entry_oracle import grade_double_entry
# #EXT-060-REQ-17 End

# #EXT-060-REQ-28 Start
# TASK-23: reuse (not reimplement) the already-landed injectable-clock oracle (EXT-059 REQ-10)
# for the first TIME-DEPENDENT ("clock" oracle_kind) grading path -- never a new driving
# mechanism.
from harness.clock_oracle import grade_clock
# #EXT-060-REQ-28 End


@dataclass
class RealSystemTask:
    """One held-out sentence->system REAL-systems task. ``oracle_kind`` selects the grading
    dispatch (``"fs"`` -> ``harness.fs_oracle``, ``"cli-exact"`` -> the exact-stdout check variant
    reused from ``harness.system_suite``, ``"import"`` -> ``harness.import_driver`` for a reusable
    library task); ``oracle_spec`` is a plain declarative dict whose shape depends on
    ``oracle_kind`` (see :func:`grade_real_system_task`). Kept intentionally simple and fully
    declarative -- no check here is ever a live callable closing over test-internal state, so a
    task can be inspected/serialized/logged without executing anything."""

    name: str
    cls: str
    sentence: str
    oracle_kind: str
    oracle_spec: dict = field(default_factory=dict)


def grade_real_system_task(task: "RealSystemTask", root: Any, *,
                            python_exe: "str | None" = None) -> "tuple[bool, str]":
    """Grade an ALREADY-BUILT system at ``root`` (a directory containing the built entrypoint,
    typically ``main.py``) against ``task``'s own declarative oracle -- never the model's
    self-acceptance, never a reference implementation. Dispatches on ``task.oracle_kind``:

    - ``"fs"``: ``task.oracle_spec`` is ``{"seed": [...seed_tree entries...], "entrypoint": str,
      "argv": [...], "checks": [...fs_oracle checks...], "timeout": float}``. Seeds the input
      tree, runs the built entrypoint sandboxed, and INDEPENDENTLY re-inspects the resulting tree
      (``harness.fs_oracle.seed_tree`` + ``run_and_inspect``) -- never trusts the entrypoint's own
      stdout for the filesystem effect.
    - ``"cli-exact"``: ``task.oracle_spec`` is ``{"argv": [...], "stdin": str | None,
      "expected_stdout": str}``. Runs the built entrypoint and requires an EXACT (not
      substring) stdout match, reusing ``harness.system_suite``'s ``exact_stdout`` check variant
      (the same sandboxed/scrubbed-env subprocess convention every other black-box check in this
      codebase already goes through -- no divergent execution path).
    - ``"import"``: ``task.oracle_spec`` is ``{"module": str, "api_calls": [...], "injected":
      {...}, "checks": [...], "timeout": float, "expected_sleep_calls": int | None}``. Imports the
      built module in a FRESH sandboxed subprocess (``harness.import_driver.drive_import``) and
      drives its public API with any injected clock/spies declared -- for a reusable LIBRARY task
      (no CLI/stdout contract at all).
    - ``"service"``: ``task.oracle_spec`` is ``{"entry": str, "http_checks": [...], "db": {"path":
      str | None, "min_rows": int, "table": str | None} | None, "startup_timeout": float,
      "request_timeout": float}``. Launches the built entrypoint as a real long-lived server on an
      ephemeral localhost port and drives real HTTP requests against it
      (``harness.server_oracle.serve_and_check_stdlib``); when ``"db"`` is present, AFTER the server
      is torn down, INDEPENDENTLY re-opens the resulting SQLite file (``harness.datastore_oracle``)
      and asserts the persisted row count -- never trusting the service's own HTTP responses for
      durability. For a stdlib REST/SQLite-backed service (no framework, no CLI/stdout contract).
    - ``"agent"``: ``task.oracle_spec`` is ``{"entry": str, "script": [...], "tools": {...},
      "goal": str, "expect_tool_calls": [...], "expect_final_contains": str | None,
      "expect_terminated": bool, "max_steps": int | None, "timeout": float | None}``. Drives the
      built entrypoint as a real agent process against a SCRIPTED stub model + controlled tool
      sandbox (``harness.agent_oracle.drive_agent``) and grades the ORDERED tool-call sequence it
      actually made, never its reasoning (``harness.agent_oracle.check_agent``) -- for a
      multi-step, tool-calling AGENT system (no CLI/stdout/HTTP-service contract at all).
    - ``"state_machine"``: ``task.oracle_spec`` is ``{"module": str, "entity": str, "spec":
      {...state-machine spec shape...}}``. Imports the built ``entity`` class from ``module`` in a
      fresh sandboxed subprocess and drives it through the spec's legal/illegal transition script
      (``harness.state_machine_oracle.grade_state_machine``) -- for a LIFECYCLE-shaped system (an
      illegal transition must be rejected, not silently allowed).
    - ``"conservation"``: ``task.oracle_spec`` is ``{"module": str, "entity": str, "spec":
      {...conservation spec shape...}}``. Imports the built ``entity`` class from ``module`` in a
      fresh sandboxed subprocess and drives it through the spec's legal/illegal operation script
      (``harness.conservation_oracle.grade_conservation``) -- for a CONSERVATION-shaped system (an
      operation that would oversell/overdraw a conserved quantity must be rejected, not silently
      allowed).
    - ``"clock"``: ``task.oracle_spec`` is ``{"module": str, "entity": str, "spec":
      {...injectable-clock spec shape...}}``. Imports the built ``entity`` class from ``module``
      in a fresh sandboxed subprocess and drives it through the spec's injected-clock timeline
      script (``harness.clock_oracle.grade_clock``) -- for a TIME-DEPENDENT system (correctness
      that depends on the passage of time, e.g. an auth lockout window) whose constructor must
      accept a keyword-named zero-argument clock callable and consult ONLY that callable, never
      the real wall clock, for every time decision.

    Returns ``(accepted, note)``. NEVER RAISES: an unknown ``oracle_kind``, a malformed
    ``oracle_spec``, or any exception during grading is an honest ``(False, <reason>)`` -- never a
    fabricated pass."""
    python_exe = python_exe or sys.executable or "python"
    try:
        spec = task.oracle_spec if isinstance(task.oracle_spec, dict) else {}
        if task.oracle_kind == "fs":
            return _grade_fs(spec, root, python_exe)
        if task.oracle_kind == "cli-exact":
            return _grade_cli_exact(spec, root, python_exe)
        # #EXT-060-REQ-3 Start
        if task.oracle_kind == "import":
            return _grade_import(spec, root, python_exe)
        # #EXT-060-REQ-3 End
        # #EXT-060-REQ-9 Start
        if task.oracle_kind == "service":
            return _grade_service(spec, root, python_exe)
        # #EXT-060-REQ-9 End
        # #EXT-060-REQ-11 Start
        if task.oracle_kind == "agent":
            return _grade_agent(spec, root, python_exe)
        # #EXT-060-REQ-11 End
        # #EXT-060-REQ-13 Start
        if task.oracle_kind == "state_machine":
            return _grade_state_machine(spec, root, python_exe)
        # #EXT-060-REQ-13 End
        # #EXT-060-REQ-15 Start
        if task.oracle_kind == "conservation":
            return _grade_conservation(spec, root, python_exe)
        # #EXT-060-REQ-15 End
        # #EXT-060-REQ-17 Start
        if task.oracle_kind == "double_entry":
            return _grade_double_entry(spec, root, python_exe)
        # #EXT-060-REQ-17 End
        # #EXT-060-REQ-28 Start
        if task.oracle_kind == "clock":
            return _grade_clock(spec, root, python_exe)
        # #EXT-060-REQ-28 End
        return False, f"unknown oracle_kind: {task.oracle_kind!r}"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"grade_real_system_task raised unexpectedly: {exc}"


def _grade_fs(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "fs"`` grading path: seed the declared input tree, run the built
    entrypoint, then independently verify the declared post-conditions. Never raises."""
    seed_spec = oracle_spec.get("seed") or []
    seed_ok, seed_note = seed_tree(root, seed_spec)
    if not seed_ok:
        return False, f"seed_tree failed: {seed_note}"
    entrypoint = oracle_spec.get("entrypoint", "main.py")
    argv = oracle_spec.get("argv") or []
    checks = oracle_spec.get("checks") or []
    timeout = oracle_spec.get("timeout", FS_DEFAULT_TIMEOUT_S)
    result = run_and_inspect(root, entrypoint, argv, checks, timeout=timeout, python_exe=python_exe)
    if result.failures:
        return result.ok, result.note + " -- " + " | ".join(result.failures)
    return result.ok, result.note


def _grade_cli_exact(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "cli-exact"`` grading path: an exact (not substring) stdout match,
    reusing ``harness.system_suite``'s ``exact_stdout`` check-variant dispatcher (``plan=None`` so
    entrypoint resolution falls back to ``root/main.py``, the same single-file convention every
    task in this suite pins in its sentence). Never raises."""
    check = {
        "kind": "exact_stdout",
        "argv": oracle_spec.get("argv") or [],
        "stdin": oracle_spec.get("stdin"),
        "expected": oracle_spec.get("expected_stdout", ""),
    }
    return _run_check_variant(check, Path(root), None, python_exe)


# #EXT-060-REQ-3 Start
# TASK-2 (REQ-3): the ``oracle_kind == "import"`` grading path -- a reusable LIBRARY task (no
# CLI/stdout contract). Wires (never reimplements) ``harness.import_driver.drive_import``: import
# the built module in a fresh sandboxed subprocess, drive its public API with any injected
# clock/spies the task declares, and grade by the driver's own sentinel-reported behavior --
# never the built module's own printing, never a reference implementation.
def _grade_import(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "import"`` grading path: import the built module named
    ``oracle_spec["module"]`` in a fresh sandboxed subprocess, drive ``oracle_spec["api_calls"]``
    with ``oracle_spec["injected"]`` (e.g. a monkeypatched ``time.sleep`` clock and/or recording
    spy callables), and require every entry of ``oracle_spec["checks"]`` to hold (see
    :func:`harness.import_driver.drive_import`). When ``oracle_spec["expected_sleep_calls"]`` is
    set, ALSO requires the injected clock's recorded call count to match exactly -- so a retry
    library that gives up early (too few sleeps) or busy-loops without ever calling the injected
    clock (zero sleeps) is caught even though ``drive_import``'s own declarative ``checks`` have no
    dedicated "sleep count" check kind. Never raises: a malformed ``oracle_spec`` (missing
    ``module``) or any exception during grading is an honest ``(False, <reason>)``."""
    module = oracle_spec.get("module")
    if not isinstance(module, str) or not module.strip():
        return False, f"oracle_spec missing/invalid required 'module' key: {module!r}"
    api_calls = oracle_spec.get("api_calls") or []
    checks = oracle_spec.get("checks") or []
    injected = oracle_spec.get("injected") or {}
    timeout = oracle_spec.get("timeout", IMPORT_DEFAULT_TIMEOUT_S)

    result = drive_import(root, module, api_calls, checks, timeout=timeout,
                           injected=injected, python_exe=python_exe)
    if not result.ok:
        detail = " | ".join(result.failures) if result.failures else ""
        return False, result.note + (f" -- {detail}" if detail else "")

    expected_sleep_calls = oracle_spec.get("expected_sleep_calls")
    if expected_sleep_calls is not None and result.sleep_call_count != expected_sleep_calls:
        return False, (
            f"import_driver's own checks passed but the injected clock recorded "
            f"{result.sleep_call_count!r} sleep call(s) between attempts, expected exactly "
            f"{expected_sleep_calls} -- the decorator must sleep between each failed attempt "
            "(no real wall-clock sleep occurred either way, since the clock is injected)"
        )
    return True, result.note
# #EXT-060-REQ-3 End


# #EXT-060-REQ-9 Start
# TASK-8: the ``oracle_kind == "service"`` grading path -- for a real, long-lived REST/SQLite-backed
# service (no CLI/stdout contract at all). Wires (never reimplements)
# ``harness.server_oracle.serve_and_check_stdlib`` for the real-HTTP half, and
# ``harness.datastore_oracle``'s detection/row-counting helpers (or a tiny inline stdlib ``sqlite3``
# read) for the INDEPENDENT, post-teardown persistence half -- never trusting the service's own HTTP
# responses for durability, exactly the same "hollow-persistence" concern
# ``harness.datastore_oracle.verify_persistence`` already guards against for CLI-shaped systems.
def _verify_service_db(root: Any, db_spec: dict) -> "tuple[bool, str]":
    """Open a FRESH ``sqlite3`` connection to the SQLite file the ``db_spec`` names (or, when no
    ``"path"`` is given, the file :func:`harness.datastore_oracle.detect_sqlite_datastore` detects
    under ``root``) and assert its row count meets ``db_spec.get("min_rows", 0)`` -- schema-agnostic
    (``harness.datastore_oracle.count_all_rows``) unless ``db_spec["table"]`` names one table
    explicitly. Called ONLY after the server process has already been torn down (by the caller), so
    this is a genuinely independent read of what actually landed on disk. Never raises: any failure
    (missing file, bad query, malformed spec) is an honest ``(False, <reason>)``."""
    try:
        root_path = Path(root)
    except (TypeError, ValueError) as exc:
        return False, f"db assertion: invalid root {root!r}: {exc}"

    db_rel = db_spec.get("path") if isinstance(db_spec, dict) else None
    if db_rel:
        db_file = root_path / str(db_rel)
    else:
        info = detect_sqlite_datastore(root_path)
        if info is None or not info.db_path:
            return False, "db assertion: no db_path given and none could be auto-detected"
        db_file = root_path / info.db_path

    if not db_file.exists():
        return False, (f"db assertion: database file does not exist at {db_file} -- the service "
                        "never actually persisted to SQLite (hollow-persistence: HTTP responses "
                        "may look correct, the file does not exist)")

    conn = None
    try:
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()
        table = db_spec.get("table") if isinstance(db_spec, dict) else None
        if table:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                row = cur.fetchone()
                row_count = int(row[0]) if row else 0
            except Exception as exc:
                return False, f"db assertion: could not query table {table!r}: {exc}"
        else:
            row_count = count_all_rows(cur)
    except Exception as exc:
        return False, f"db assertion: could not open/query database file {db_file}: {exc}"
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

    min_rows = db_spec.get("min_rows", 0) if isinstance(db_spec, dict) else 0
    try:
        min_rows = int(min_rows)
    except (TypeError, ValueError):
        min_rows = 0
    if row_count < min_rows:
        return False, (f"db assertion: found {row_count} row(s) independently in {db_file}, "
                        f"expected >= {min_rows}")
    return True, f"db assertion ok: {row_count} row(s) independently verified in {db_file}"


def _grade_service(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "service"`` grading path: (a) launch the built entrypoint as a real
    server and drive every declared ``http_checks`` entry against it as a REAL HTTP request
    (``harness.server_oracle.serve_and_check_stdlib`` -- unchanged launch/poll/teardown machinery,
    the SAME sandboxed subprocess convention every other check in this codebase already goes
    through); (b) when ``oracle_spec["db"]`` is present, AFTER that server has already been torn
    down, independently re-verify the persisted SQLite state (:func:`_verify_service_db`). ``python
    _exe`` is accepted for dispatch-signature parity with the other ``_grade_*`` helpers but is not
    forwarded -- ``serve_and_check_stdlib`` always launches the entry with ``sys.executable``
    (there is no interpreter-override parameter on that function). Never raises: any failure at any
    stage is an honest ``(False, <reason>)``."""
    entry = oracle_spec.get("entry") or "main.py"
    http_checks = oracle_spec.get("http_checks") or []
    startup_timeout = oracle_spec.get("startup_timeout", SERVICE_DEFAULT_STARTUP_TIMEOUT_S)
    request_timeout = oracle_spec.get("request_timeout", SERVICE_DEFAULT_REQUEST_TIMEOUT_S)

    result = serve_and_check_stdlib(root, entry, http_checks,
                                     startup_timeout=startup_timeout, request_timeout=request_timeout)
    if not result.get("ok"):
        return False, f"service http checks failed: {result.get('note')}"

    db_spec = oracle_spec.get("db")
    if isinstance(db_spec, dict):
        db_ok, db_note = _verify_service_db(root, db_spec)
        if not db_ok:
            return False, db_note
        return True, f"ok: service http checks passed; {db_note}"

    return True, "ok: service http checks passed"
# #EXT-060-REQ-9 End


# #EXT-060-REQ-11 Start
# TASK-9: the ``oracle_kind == "agent"`` grading path -- for a multi-step, TOOL-CALLING agent
# system (no CLI/stdout/HTTP-service contract at all). Wires (never reimplements)
# ``harness.agent_oracle.drive_agent``/``check_agent`` -- the scripted-stub-model + controlled-
# tool-sandbox oracle already landed for EXT-059 REQ-6, exactly the "grade the orchestration
# control flow, never the model's reasoning" discipline that module documents.
def _grade_agent(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "agent"`` grading path: run the built entrypoint named
    ``oracle_spec.get("entry", "main.py")`` against a SCRIPTED stub model + controlled tool
    sandbox (``harness.agent_oracle.drive_agent``), then assert the ORDERED tool-call sequence it
    actually made and its final answer against ``oracle_spec``'s declared expectations
    (``harness.agent_oracle.check_agent``). ``oracle_spec`` mirrors ``drive_agent``/``check_agent``'s
    own keyword vocabulary directly (``entry``, ``script``, ``tools``, ``goal``,
    ``expect_tool_calls``, ``expect_final_contains``, ``expect_terminated``, plus optional
    ``max_steps``/``timeout`` passthrough) -- never a divergent grading path. Never raises: both
    ``drive_agent`` and ``check_agent`` are themselves never-raise (see ``harness/agent_oracle.py``),
    and this helper adds no exception-prone logic of its own."""
    entry = oracle_spec.get("entry") or "main.py"
    script = oracle_spec.get("script") or []
    tools = oracle_spec.get("tools") or {}
    goal = oracle_spec.get("goal", "")
    drive_kwargs: dict = {}
    if oracle_spec.get("max_steps") is not None:
        drive_kwargs["max_steps"] = oracle_spec["max_steps"]
    if oracle_spec.get("timeout") is not None:
        drive_kwargs["timeout"] = oracle_spec["timeout"]

    result = drive_agent(root, entry, script=script, tools=tools, goal=goal,
                          python_exe=python_exe, **drive_kwargs)

    expect_tool_calls = oracle_spec.get("expect_tool_calls") or []
    expect_final_contains = oracle_spec.get("expect_final_contains")
    expect_terminated = oracle_spec.get("expect_terminated", True)
    ok, note = check_agent(
        result, expect_tool_calls=expect_tool_calls,
        expect_final_contains=expect_final_contains, expect_terminated=bool(expect_terminated),
    )
    if not ok:
        return False, f"{note} (drive_agent note: {result.get('note')!r})"
    return True, result.get("note") or "ok"
# #EXT-060-REQ-11 End


# #EXT-060-REQ-13 Start
# TASK-10: the ``oracle_kind == "state_machine"`` grading path -- for a LIFECYCLE-shaped system
# (order/shipment/fulfillment/etc.) where an ILLEGAL transition must be rejected, not silently
# allowed. Wires (never reimplements) ``harness.state_machine_oracle.grade_state_machine`` -- the
# scripted legal/illegal transition oracle already landed for EXT-059 REQ-7.
def _grade_state_machine(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "state_machine"`` grading path: import ``oracle_spec["entity"]`` from
    ``oracle_spec["module"]`` in a fresh sandboxed subprocess and drive it through
    ``oracle_spec["spec"]``'s legal/illegal transition script
    (``harness.state_machine_oracle.grade_state_machine``), returning ``(accepted, note)``
    UNMODIFIED from that oracle. Never raises: a malformed ``oracle_spec`` (missing ``module``/
    ``entity``/``spec``) or any exception during grading is an honest ``(False, <reason>)`` --
    ``grade_state_machine`` itself already never raises, this helper adds no exception-prone logic
    of its own."""
    module = oracle_spec.get("module")
    if not isinstance(module, str) or not module.strip():
        return False, f"oracle_spec missing/invalid required 'module' key: {module!r}"
    entity = oracle_spec.get("entity")
    if not isinstance(entity, str) or not entity.strip():
        return False, f"oracle_spec missing/invalid required 'entity' key: {entity!r}"
    return grade_state_machine(
        root, module=module, entity=entity, spec=oracle_spec.get("spec"), python_exe=python_exe,
    )
# #EXT-060-REQ-13 End


# #EXT-060-REQ-15 Start
# TASK-11: the ``oracle_kind == "conservation"`` grading path -- for a CONSERVATION-shaped system
# (inventory reservation/wallet balances/etc.) where an operation that would oversell/overdraw a
# conserved quantity must be rejected, not silently allowed. Wires (never reimplements)
# ``harness.conservation_oracle.grade_conservation`` -- the scripted legal/illegal operation
# oracle already landed for EXT-059 REQ-8.
def _grade_conservation(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "conservation"`` grading path: import ``oracle_spec["entity"]`` from
    ``oracle_spec["module"]`` in a fresh sandboxed subprocess and drive it through
    ``oracle_spec["spec"]``'s legal/illegal operation script
    (``harness.conservation_oracle.grade_conservation``), returning ``(accepted, note)``
    UNMODIFIED from that oracle. Never raises: a malformed ``oracle_spec`` (missing ``module``/
    ``entity``/``spec``) or any exception during grading is an honest ``(False, <reason>)`` --
    ``grade_conservation`` itself already never raises, this helper adds no exception-prone logic
    of its own."""
    module = oracle_spec.get("module")
    if not isinstance(module, str) or not module.strip():
        return False, f"oracle_spec missing/invalid required 'module' key: {module!r}"
    entity = oracle_spec.get("entity")
    if not isinstance(entity, str) or not entity.strip():
        return False, f"oracle_spec missing/invalid required 'entity' key: {entity!r}"
    return grade_conservation(
        root, module=module, entity=entity, spec=oracle_spec.get("spec"), python_exe=python_exe,
    )
# #EXT-060-REQ-15 End


# #EXT-060-REQ-17 Start
# TASK-12: the ``oracle_kind == "double_entry"`` grading path -- for a FINTECH-LEDGER-shaped
# system (journal/general-ledger/wallet/escrow/etc.) where an UNBALANCED journal entry (debits
# != credits) must be rejected, not silently posted. Wires (never reimplements)
# ``harness.double_entry_oracle.grade_double_entry`` -- the scripted balanced/unbalanced posting
# oracle already landed for EXT-059 REQ-9.
def _grade_double_entry(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "double_entry"`` grading path: import ``oracle_spec["entity"]`` from
    ``oracle_spec["module"]`` in a fresh sandboxed subprocess and drive it through
    ``oracle_spec["spec"]``'s balanced/unbalanced posting script
    (``harness.double_entry_oracle.grade_double_entry``), returning ``(accepted, note)``
    UNMODIFIED from that oracle. Never raises: a malformed ``oracle_spec`` (missing ``module``/
    ``entity``/``spec``) or any exception during grading is an honest ``(False, <reason>)`` --
    ``grade_double_entry`` itself already never raises, this helper adds no exception-prone
    logic of its own."""
    module = oracle_spec.get("module")
    if not isinstance(module, str) or not module.strip():
        return False, f"oracle_spec missing/invalid required 'module' key: {module!r}"
    entity = oracle_spec.get("entity")
    if not isinstance(entity, str) or not entity.strip():
        return False, f"oracle_spec missing/invalid required 'entity' key: {entity!r}"
    return grade_double_entry(
        root, module=module, entity=entity, spec=oracle_spec.get("spec"), python_exe=python_exe,
    )
# #EXT-060-REQ-17 End


# #EXT-060-REQ-28 Start
# TASK-23: the ``oracle_kind == "clock"`` grading path -- for a TIME-DEPENDENT system (auth
# lockout/backoff, SLA windows, token validity, etc.) whose correctness depends on the passage of
# time. Wires (never reimplements) ``harness.clock_oracle.grade_clock`` -- the injectable-clock
# timeline oracle already landed for EXT-059 REQ-10.
def _grade_clock(oracle_spec: dict, root: Any, python_exe: str) -> "tuple[bool, str]":
    """The ``oracle_kind == "clock"`` grading path: import ``oracle_spec["entity"]`` from
    ``oracle_spec["module"]`` in a fresh sandboxed subprocess and drive it through
    ``oracle_spec["spec"]``'s injected-clock timeline script (``harness.clock_oracle.grade_clock``),
    returning ``(accepted, note)`` UNMODIFIED from that oracle. Never raises: a malformed
    ``oracle_spec`` (missing ``module``/``entity``/``spec``) or any exception during grading is an
    honest ``(False, <reason>)`` -- ``grade_clock`` itself already never raises, this helper adds
    no exception-prone logic of its own."""
    module = oracle_spec.get("module")
    if not isinstance(module, str) or not module.strip():
        return False, f"oracle_spec missing/invalid required 'module' key: {module!r}"
    entity = oracle_spec.get("entity")
    if not isinstance(entity, str) or not entity.strip():
        return False, f"oracle_spec missing/invalid required 'entity' key: {entity!r}"
    return grade_clock(
        root, module=module, entity=entity, spec=oracle_spec.get("spec"), python_exe=python_exe,
    )
# #EXT-060-REQ-28 End


def _rates(results: "list[dict]") -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0, "pass_rate": 0.0}
    return {"n": n, "pass_rate": sum(1 for r in results if r["accepted"]) / n}


def _aggregate(results: "list[dict]") -> dict:
    agg = {"overall": _rates(results)}
    classes = sorted({r["cls"] for r in results})
    agg["by_cls"] = {c: _rates([r for r in results if r["cls"] == c]) for c in classes}
    return agg


def _run_one_task(task: "RealSystemTask", *, llm: Any, python_exe: str) -> dict:
    """Build + grade ONE task in an isolated temp root, enforcing leaves-OFF at TWO points: (1)
    statically, before any build is attempted, via ``leaf_for_spec(task.sentence)`` -- a spec that
    fingerprints a verified leaf's contract is a suite-scoping defect and is scored a failure
    without ever calling ``build_system`` (so this never risks a spurious model call for a
    misscoped task); (2) against the actual build result's ``build_path`` -- if ``build_system``'s
    OWN leaf-repair stage (EXT-058 REQ-3) adopted a leaf template for this spec, that is likewise
    scored a failure, never a pass, however good the leaf's own reference implementation is (a
    leaf-produced green proves nothing about the model's OWN capability, Tenet 3). Never raises:
    any exception at any stage is an honest ``accepted=False`` with a diagnostic ``note``."""
    rec = {"name": task.name, "cls": task.cls, "accepted": False, "shipped": False,
           "leaf_fired": False, "note": ""}
    try:
        pre_leaf = leaf_for_spec(task.sentence)
        if pre_leaf is not None:
            rec["leaf_fired"] = True
            rec["note"] = (f"leaves-OFF violation: leaf_for_spec matched {pre_leaf!r} for a "
                            "real-systems spec -- scored as a failure (Tenet 3), build skipped")
            return rec

        with tempfile.TemporaryDirectory(prefix="real_sys_suite_") as tmp:
            root = Path(tmp)
            build = build_system(task.sentence, root, llm=llm)
            if not isinstance(build, dict):
                rec["note"] = "build_system returned a non-dict result"
                return rec

            rec["shipped"] = bool(build.get("shipped"))
            build_path = str(build.get("build_path") or "free-form")
            if build_path.startswith("leaf:"):
                rec["leaf_fired"] = True
                rec["note"] = (f"leaves-OFF violation: build_system adopted leaf path "
                                f"{build_path!r} for a real-systems spec -- scored as a failure "
                                "(Tenet 3)")
                return rec

            if not rec["shipped"]:
                rec["note"] = build.get("note") or "build did not ship"
                return rec

            accepted, note = grade_real_system_task(task, root, python_exe=python_exe)
            rec["accepted"] = bool(accepted)
            rec["note"] = note
            return rec
    except Exception as exc:  # never raise -- one bad task never aborts the whole suite
        rec["note"] = f"suite run raised unexpectedly: {exc}"
        return rec


def run_real_systems_suite(tasks: "list[RealSystemTask] | None" = None, *, llm: Any = None,
                            python_exe: "str | None" = None) -> dict:
    """Run the leaves-OFF real-systems suite: for each task, build via
    ``harness.system_builder.build_system(task.sentence, root, llm=llm)`` (leak-free -- the build
    sees only ``task.sentence``, never ``task.oracle_spec``), assert the leaf path stayed OFF, and
    grade ONLY by the task's own black-box oracle (:func:`grade_real_system_task`). Returns
    ``{"results": [...], "aggregate": {"overall": {...}, "by_cls": {...}}}`` reporting an honest
    per-class pass@1. Defaults to :data:`REAL_SYSTEMS_TASKS` when ``tasks`` is ``None``.

    NEVER raises: any per-task failure is recorded as that task's ``accepted=False`` and the suite
    continues to the next task."""
    tasks = REAL_SYSTEMS_TASKS if tasks is None else tasks
    python_exe = python_exe or sys.executable or "python"
    results = [_run_one_task(task, llm=llm, python_exe=python_exe) for task in tasks]
    return {"results": results, "aggregate": _aggregate(results)}
# #EXT-060-REQ-1 End


# #EXT-060-REQ-2 Start
# TASK-1 (REQ-2): the CSV->JSON group-by ETL task -- a real, single-file data-pipeline system (not
# a toy CLI): read an input CSV file, group its rows by a named column, sum a numeric column per
# group, and write the grouped result as JSON to an output file. Every path/column/output-format
# detail is pinned in the sentence itself (contract-precise, the same convention
# `harness.system_suite`'s tasks use) so the independent oracle can byte-compare the output
# deterministically -- no hidden key, no value the model could not read off the sentence.
#
# The `amount` column is pinned to WHOLE INTEGERS (never a decimal) specifically so the summed
# per-group values, and therefore the output JSON's byte representation, are never subject to
# floating-point formatting ambiguity (e.g. `30.0` vs `30` vs a rounding artifact) -- an honest
# design choice that keeps the oracle a true byte-exact comparison without pinning down anything
# the sentence does not already state.
_CSV_GROUPBY_SENTENCE = (
    "Write a single-file Python CLI program in a file named main.py, a CSV-to-JSON group-by ETL "
    "tool. Running it as `python main.py <input_csv> <output_json>` (exactly two command-line "
    "arguments: the path to an input CSV file, then the path to write an output JSON file), it "
    "reads the CSV file at the first path, where the FIRST line is a comma-separated header row "
    "containing a column named `category` and a column named `amount` (amount values are always "
    "whole integers, no quoting/escaping needed), and each subsequent line is one data row aligned "
    "to that header. It groups the rows by their `category` value and computes the SUM of the "
    "`amount` column, as an integer, for EACH distinct category. It then writes the grouped result "
    "to the file at the second path as a single JSON object, produced via the standard library "
    "`json` module's `json.dumps` called with `sort_keys=True` and `separators=(',', ':')` (so the "
    "object's keys appear in ascending alphabetical order and there is no extra whitespace anywhere "
    "in the output), whose keys are the distinct `category` strings and whose values are each "
    "category's summed `amount` as a JSON integer, followed by a single trailing newline character. "
    "Encode that JSON document plus its trailing newline as UTF-8 and write those exact bytes "
    "directly to the output file opened in BINARY mode (e.g. `open(output_json, \"wb\")` or "
    "`pathlib.Path(output_json).write_bytes(...)`) -- never a text-mode write, so no platform-"
    "specific newline translation occurs. Print nothing to standard output. The file must contain "
    "an `if __name__ == \"__main__\":` block that runs this."
)

# Seeded input CSV: three categories, each with more than one row, so a correct build must both
# GROUP correctly and SUM correctly (a build that groups but forgets to sum, or sums but forgets to
# group, produces a different, independently-catchable result).
_CSV_GROUPBY_SEED_CSV = (
    "category,amount\n"
    "produce,10\n"
    "electronics,20\n"
    "produce,5\n"
    "electronics,7\n"
    "office,3\n"
)
# Expected grouped sums: electronics=20+7=27, office=3, produce=10+5=15 -- sorted alphabetically
# and compactly serialized exactly as the sentence pins (`sort_keys=True`, `separators=(',', ':')`),
# followed by one trailing newline.
_CSV_GROUPBY_EXPECTED_JSON = '{"electronics":27,"office":3,"produce":15}\n'

CSV_GROUPBY_ETL_TASK = RealSystemTask(
    name="csv-groupby-json-etl",
    cls="etl",
    sentence=_CSV_GROUPBY_SENTENCE,
    oracle_kind="fs",
    oracle_spec={
        "seed": [{"path": "input.csv", "bytes": _CSV_GROUPBY_SEED_CSV}],
        "entrypoint": "main.py",
        "argv": ["input.csv", "output.json"],
        "checks": [
            {"kind": "path_exists", "path": "output.json"},
            {"kind": "file_bytes_equal", "path": "output.json", "bytes": _CSV_GROUPBY_EXPECTED_JSON},
        ],
    },
)

# #EXT-060-REQ-2 End


# #EXT-060-REQ-3 Start
# TASK-2 (REQ-3): the retry/backoff decorator library task -- a real, reusable single-file library
# (no CLI/stdout contract at all): a `retry.py` module exporting a `retry(times, exceptions=
# Exception)` decorator. Every detail of the public contract (filename, decorator name, signature,
# attempt-count/sleep-between-attempts/return-first-success/re-raise-on-exhaust semantics) is
# pinned in the sentence itself so the import_driver oracle's expected values are all DERIVED from
# that same visible contract -- `times` and `exceptions` are the decorator's own named parameters
# (echoed by the contract), so exercising the built module with a concrete `times=3` call is an
# ordinary black-box test input, never a hidden undocumented key.
_RETRY_BACKOFF_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named retry.py, a "
    "retry-with-backoff decorator library. The module must import the standard library `time` "
    "module at the top, and define exactly one public function named `retry` with the signature "
    "`retry(times, exceptions=Exception)`. Calling `retry(times, exceptions=Exception)` returns a "
    "DECORATOR (a function that takes one argument, the callable to wrap, and returns a new "
    "callable) meant to be used as `@retry(times=N)` above a function definition, or applied "
    "directly as `retry(times=N)(some_callable)`. The new (wrapped) callable returned by the "
    "decorator accepts the exact same positional and keyword arguments as the callable it wraps "
    "and forwards them unchanged on every attempt. When the new callable is invoked: it calls the "
    "wrapped callable with the forwarded arguments; if that call raises an exception that is an "
    "instance of `exceptions` (a single exception type, or a tuple of exception types), that "
    "counts as one FAILED attempt -- the new callable calls `time.sleep(...)` exactly once (any "
    "nonnegative duration) and then invokes the wrapped callable again with the same forwarded "
    "arguments, continuing for up to `times` total attempts. As soon as any attempt RETURNS "
    "without raising, the new callable returns that attempt's return value immediately and "
    "performs no further attempts and no further `time.sleep` calls. If every one of the `times` "
    "attempts raises (including the final, `times`-th attempt), the new callable does NOT sleep "
    "again after that final attempt and instead re-raises that final attempt's exception to its "
    "own caller. An exception that is NOT an instance of `exceptions` propagates immediately on "
    "whichever attempt raised it, with no further retry and no `time.sleep` call for that "
    "exception at all."
)

RETRY_BACKOFF_LIB_TASK = RealSystemTask(
    name="retry-backoff-decorator-lib",
    cls="library",
    sentence=_RETRY_BACKOFF_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "retry",
        # Call chain: (1) `retry(times=3)` -> the decorator itself; (2) apply that decorator to
        # the injected fail-twice-then-succeed spy -> the decorated callable; (3) invoke the
        # decorated callable with no arguments -> its eventual return value. `_bindings` in the
        # import_driver's rendered driver resolves each prior call_id as a callable target, so
        # this decorator-of-a-decorator chain is driven purely declaratively (no eval/exec).
        "api_calls": [
            {"id": "make_decorator", "target": "retry", "args": [], "kwargs": {"times": 3}},
            {"id": "decorated", "target": "make_decorator",
             "args": [{"__jaros_ref__": "flaky"}], "kwargs": {}},
            {"id": "result", "target": "decorated", "args": [], "kwargs": {}},
        ],
        "injected": {
            "clock": True,  # monkeypatches time.sleep to a recording no-op -- never real sleep
            "spies": {
                # Raises ValueError on its first 2 invocations, then returns "success" -- a
                # correct `retry(times=3)` must call this exactly 3 times and return "success".
                "flaky": {"return_value": "success", "raise_exception": "ValueError",
                          "raise_count": 2},
            },
        },
        "checks": [
            {"kind": "returns_equals", "call_id": "result", "expected": "success"},
            {"kind": "call_count", "spy": "flaky", "expected": 3},
        ],
        # Exactly 2 sleeps: between attempt 1->2 and attempt 2->3, never after the final (3rd,
        # succeeding) attempt -- catches a decorator that never sleeps between attempts (a
        # busy-loop retry) even though such a stub could still pass the two checks above.
        "expected_sleep_calls": 2,
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS: "list[RealSystemTask]" = [CSV_GROUPBY_ETL_TASK, RETRY_BACKOFF_LIB_TASK]
# #EXT-060-REQ-3 End


# #EXT-060-REQ-4 Start
# TASK-3: the INI-section config-query CLI task -- a third held-out real-systems task, graded by
# the ALREADY-LANDED cli-exact oracle (no new oracle code: reuses `_grade_cli_exact` ->
# `harness.system_suite`'s `exact_stdout` check variant, the same sandboxed/scrubbed-env
# subprocess convention every other black-box check in this codebase already goes through). Every
# parsing rule (section/key line shape, whitespace stripping, absent-key/-section exit behavior)
# is pinned in the sentence itself so the oracle's expected stdout is fully DERIVED from that same
# visible contract -- no hidden key, no reference implementation the model could not see.
_INI_SECTION_QUERY_SENTENCE = (
    "Write a command-line program in a file named main.py that reads an INI-format configuration "
    "file from standard input and takes exactly two command-line arguments: a section name and a "
    "key name. It parses the INI text (sections are lines like `[section]`; within a section, keys "
    "are lines like `key = value` or `key=value`, values may have surrounding whitespace that must "
    "be stripped). It prints, to standard output, exactly the value of the given key inside the "
    "given section, followed by a single trailing newline, and nothing else. If the section or key "
    "is absent it prints nothing and exits with a nonzero status."
)

# Seeded INI text: two sections both defining a `port` key with DIFFERENT values, so a correct
# build must resolve the key WITHIN the named section, not just the first/last occurrence of the
# key anywhere in the file (a build that ignores section scoping would read `port` from whichever
# section it encounters -- last, `db` -> 5432 -- or first, `server` -> 8080 by coincidence; the
# oracle only accepts the value that is actually correct for the requested `server` section).
_INI_SECTION_QUERY_STDIN = (
    "[server]\n"
    "host = localhost\n"
    "port = 8080\n"
    "[db]\n"
    "port = 5432\n"
)

INI_SECTION_QUERY_TASK = RealSystemTask(
    name="ini-section-query-cli",
    cls="config-cli",
    sentence=_INI_SECTION_QUERY_SENTENCE,
    oracle_kind="cli-exact",
    oracle_spec={
        "argv": ["server", "port"],
        "stdin": _INI_SECTION_QUERY_STDIN,
        "expected_stdout": "8080\n",
    },
)

REAL_SYSTEMS_TASKS.append(INI_SECTION_QUERY_TASK)
# #EXT-060-REQ-4 End


# #EXT-060-REQ-5 Start
# TASK-4: the memoize/cache decorator library task -- a 4th held-out real-systems task, graded by
# the ALREADY-LANDED import_driver oracle (no new oracle code: reuses `_grade_import` ->
# `harness.import_driver.drive_import`, exactly REQ-3's `"import"` dispatch path). This is
# deliberately a SECOND reusable-library task, with a DOCUMENTED, entirely-defaulted parameter
# (`maxsize=128`) -- the oracle's own primary call chain invokes `memoize()` with NO arguments at
# all, so a build that drops the documented default (making `maxsize` a required positional
# parameter, mirroring the exact defect shape EXT-036 REQ-45's deterministic signature-contract
# repair targets) fails to even construct the decorator, never mind cache correctly. Every detail
# of the public contract (filename, function name/signature, decorator/caching semantics, keying
# by the positional-argument tuple) is pinned in the sentence itself so the oracle's expected
# values are all DERIVED from that same visible contract.
_MEMOIZE_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named memoize.py, a "
    "memoization/caching decorator library. Define exactly one public function named `memoize` "
    "with the signature `memoize(maxsize=128)` -- the `maxsize` parameter must be OPTIONAL with "
    "that exact default value, so calling `memoize()` with NO arguments at all is valid and uses "
    "the default. Calling `memoize(maxsize=128)`, or calling it with no arguments at all since "
    "`maxsize=128` is its default, returns a DECORATOR (a function that takes one argument, the "
    "callable to wrap, and returns a new callable) meant to be used as `@memoize()` above a "
    "function definition, or applied directly as `memoize()(some_callable)`. The new (wrapped) "
    "callable returned by the decorator accepts the exact same positional arguments as the "
    "callable it wraps and forwards them unchanged. It maintains an internal cache keyed by the "
    "tuple of positional arguments it is called with. The FIRST time the new callable is invoked "
    "with a given tuple of positional arguments, it calls the wrapped callable with those exact "
    "arguments, stores the returned value in its cache keyed by that argument tuple, and returns "
    "that value. Every SUBSEQUENT time the new callable is invoked with a positional-argument "
    "tuple that exactly matches one already present in its cache, it returns the cached value "
    "immediately WITHOUT calling the wrapped callable again. Assume `maxsize` is always large "
    "enough that no cached entry is ever evicted for the inputs used against it."
)

MEMOIZE_LIB_TASK = RealSystemTask(
    name="memoize-decorator-lib",
    cls="library",
    sentence=_MEMOIZE_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "memoize",
        # Call chain: (1) `memoize()` with NO arguments (relying entirely on the documented
        # `maxsize=128` default -- the signature-contract angle) -> the decorator itself; (2)
        # apply that decorator to the injected recording spy -> the decorated callable; (3)-(6)
        # invoke the decorated callable with arg 5 twice, then arg 7 once, then arg 5 again -- a
        # correct implementation calls the underlying spy only for the FIRST occurrence of each
        # distinct argument (2 total calls: one for 5, one for 7), serving every repeat (including
        # the LAST call, `call_x3`, which follows an intervening different-argument call) from its
        # cache -- so this also catches a "cache only the most recent call" bug, not just a
        # "never caches" bug.
        "api_calls": [
            {"id": "make_decorator", "target": "memoize", "args": [], "kwargs": {}},
            {"id": "decorated", "target": "make_decorator",
             "args": [{"__jaros_ref__": "counter"}], "kwargs": {}},
            {"id": "call_x1", "target": "decorated", "args": [5], "kwargs": {}},
            {"id": "call_x2", "target": "decorated", "args": [5], "kwargs": {}},
            {"id": "call_y1", "target": "decorated", "args": [7], "kwargs": {}},
            {"id": "call_x3", "target": "decorated", "args": [5], "kwargs": {}},
        ],
        "injected": {
            "spies": {
                # A fixed-return recording spy -- correctness here is decided by ITS CALL COUNT
                # (2, not 4), never by varying its return value per argument (the import_driver
                # spy protocol has no such feature; see harness/import_driver.py).
                "counter": {"return_value": "spied-value"},
            },
        },
        "checks": [
            {"kind": "returns_equals", "call_id": "call_x1", "expected": "spied-value"},
            {"kind": "returns_equals", "call_id": "call_x2", "expected": "spied-value"},
            {"kind": "returns_equals", "call_id": "call_y1", "expected": "spied-value"},
            {"kind": "returns_equals", "call_id": "call_x3", "expected": "spied-value"},
            {"kind": "call_count", "spy": "counter", "expected": 2},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(MEMOIZE_LIB_TASK)
# #EXT-060-REQ-5 End


# #EXT-060-REQ-6 Start
# TASK-5: the file-organizer-by-extension CLI task -- a 5th held-out real-systems task, in a NEW
# domain (a filesystem-organizing utility, not a data-pipeline or a library), graded by the
# ALREADY-LANDED fs oracle (no new oracle code: reuses `_grade_fs` -> `harness.fs_oracle`'s
# `seed_tree` + `run_and_inspect`, exactly REQ-2's `"fs"` dispatch path). Every rule (single argv
# directory, non-recursive immediate-children-only scope, lowercased-extension-without-dot
# subdirectory naming, the `noext` fallback, filename preserved unchanged, silent/exit-0 on
# success) is pinned in the sentence itself so the oracle's expected post-tree is fully DERIVED
# from that same visible contract -- no hidden key, no reference implementation the model could
# not see, and no leaf-library name-drop (kept as plain prose, per the sentence-authoring
# convention every other task in this module already follows).
_FILE_ORGANIZER_SENTENCE = (
    "Write a command-line program in a file named main.py that takes one command-line argument: "
    "a path to a directory. For every regular file directly inside that directory (do not recurse "
    "into subdirectories), it moves the file into a subdirectory (created if needed, inside that "
    "same directory) named after the file's lowercased extension WITHOUT the leading dot (e.g. "
    "`report.TXT` -> `txt/report.TXT`); a file with no extension (no dot in its name, or a name "
    "beginning with a dot and no other dot) is moved into a subdirectory named `noext`. The file's "
    "own name is preserved. It prints nothing on success and exits 0. Use only the Python standard "
    "library."
)

# Seeded input directory: a lowercase-extension file, an uppercase-extension file (same extension
# family as the lowercase one, so a correct build must LOWERCASE the destination directory name
# rather than reusing the file's own extension casing verbatim), a different extension, and a
# no-extension file -- so a build that forgets to lowercase, recurses, or leaves originals in
# place is independently catchable.
_FILE_ORGANIZER_SEED = [
    {"path": "indir/a.txt", "bytes": "A"},
    {"path": "indir/b.TXT", "bytes": "B"},
    {"path": "indir/c.md", "bytes": "C"},
    {"path": "indir/d", "bytes": "D"},
]

FILE_ORGANIZER_TASK = RealSystemTask(
    name="file-organizer-by-extension-cli",
    cls="fs-utility",
    sentence=_FILE_ORGANIZER_SENTENCE,
    oracle_kind="fs",
    oracle_spec={
        "seed": _FILE_ORGANIZER_SEED,
        "entrypoint": "main.py",
        "argv": ["indir"],
        "checks": [
            {"kind": "path_exists", "path": "indir/txt/a.txt"},
            {"kind": "file_bytes_equal", "path": "indir/txt/a.txt", "bytes": "A"},
            {"kind": "path_absent", "path": "indir/a.txt"},
            {"kind": "path_exists", "path": "indir/txt/b.TXT"},
            {"kind": "file_bytes_equal", "path": "indir/txt/b.TXT", "bytes": "B"},
            {"kind": "path_absent", "path": "indir/b.TXT"},
            {"kind": "path_exists", "path": "indir/md/c.md"},
            {"kind": "file_bytes_equal", "path": "indir/md/c.md", "bytes": "C"},
            {"kind": "path_absent", "path": "indir/c.md"},
            {"kind": "path_exists", "path": "indir/noext/d"},
            {"kind": "file_bytes_equal", "path": "indir/noext/d", "bytes": "D"},
            {"kind": "path_absent", "path": "indir/d"},
        ],
    },
)

REAL_SYSTEMS_TASKS.append(FILE_ORGANIZER_TASK)
# #EXT-060-REQ-6 End


# #EXT-060-REQ-7 Start
# TASK-6: the MODIFY half -- EXT-060 becomes the CANONICAL two-half real-systems scoreboard by
# measuring not just CREATE (a real system from a sentence) but MODIFY (an already-working real
# system changed from a one-sentence change request), graded exactly as strictly as CREATE: an
# independent, execution-plane, leak-free oracle -- never the model's own self-acceptance.
@dataclass
class RealSystemModifyTask:
    """One held-out MODIFY-from-a-sentence real-systems task. ``start_system`` is the
    known-good baseline (``{filename: source}``) the modification starts from; ``mod_sentence``
    is the one-sentence change request driving ``harness.system_builder.modify_system``.
    ``oracle_kind``/``oracle_spec`` are the SAME declarative shape :class:`RealSystemTask` uses
    -- deliberately, so the CREATE half's independent oracle dispatcher (
    :func:`grade_real_system_task`) grades a *modified* tree with zero new oracle code (duck
    typing: that dispatcher only ever reads ``task.oracle_kind``/``task.oracle_spec``).

    ``base_sentence`` (REQ-23, TASK-18): optional, defaults to ``""`` -- fully backward
    compatible. When set, it is the ORIGINAL CREATE-style sentence the ``start_system`` baseline
    was built from (e.g. the matching ``RealSystemTask.sentence``); ``_run_one_modify_task``
    forwards it to ``harness.system_builder.modify_system`` as ``spec_hint`` (REQ-52's landed
    kwarg) so the deterministic repair chain's spec detectors (``spec_demands_stdlib_http_
    service``/``spec_demands_tool_calling_agent``) see the FULL protocol contract -- a bare
    ``mod_sentence`` alone (e.g. "Add a `PUT /items/<id>` endpoint...") typically does not
    mention the http.server/OpenAI-protocol keywords those scaffolds key on, so without
    ``base_sentence`` they never fire on a real modify task."""

    name: str
    cls: str
    start_system: dict
    mod_sentence: str
    oracle_kind: str
    oracle_spec: dict = field(default_factory=dict)
    base_sentence: str = ""


def _run_one_modify_task(task: "RealSystemModifyTask", *, llm: Any, python_exe: str) -> dict:
    """Modify + grade ONE task in an isolated temp root, enforcing leaves-OFF at the same
    STATIC point the CREATE half enforces it (``leaf_for_spec(task.mod_sentence)`` -- a mod
    sentence that fingerprints a verified leaf's contract is a suite-scoping defect and is
    scored a failure without ever calling ``modify_system``, so this never risks a spurious
    model call for a misscoped task). Grades ONLY when ``modify_system`` reports ``applied``
    True -- an unapplied (reverted) modification is honestly scored a failure, never graded as
    if it had happened. Never raises: any exception at any stage is an honest
    ``accepted=False`` with a diagnostic ``note``."""
    rec = {"name": task.name, "cls": task.cls, "accepted": False, "applied": False,
           "leaf_fired": False, "note": ""}
    try:
        pre_leaf = leaf_for_spec(task.mod_sentence)
        if pre_leaf is not None:
            rec["leaf_fired"] = True
            rec["note"] = (f"leaves-OFF violation: leaf_for_spec matched {pre_leaf!r} for a "
                            "real-systems MODIFY spec -- scored as a failure (Tenet 3), "
                            "modify_system call skipped")
            return rec

        with tempfile.TemporaryDirectory(prefix="real_sys_modify_suite_") as tmp:
            root = Path(tmp)
            # #EXT-060-REQ-23 Start
            # TASK-18: thread the task's `base_sentence` (the original CREATE-style sentence its
            # `start_system` was built from) through to `modify_system` as `spec_hint` (REQ-52's
            # landed kwarg) -- combined with `mod_sentence`, this lets the http/agent scaffolds'
            # spec detectors see the full protocol contract even though the bare `mod_sentence`
            # alone often doesn't mention it. `task.base_sentence` defaults to `""`, which is
            # falsy, so `spec_hint=None` for any task that doesn't set it (fully backward
            # compatible with the two REQ-7 tasks that predate this field).
            result = modify_system(dict(task.start_system or {}), task.mod_sentence, root,
                                    llm=llm, spec_hint=(task.base_sentence or None))
            # #EXT-060-REQ-23 End
            if not isinstance(result, dict):
                rec["note"] = "modify_system returned a non-dict result"
                return rec

            rec["applied"] = bool(result.get("applied"))
            if not rec["applied"]:
                rec["note"] = result.get("note") or "modification not applied"
                return rec

            # Grade the ALREADY-MODIFIED tree via the SAME independent oracle dispatcher the
            # CREATE half uses -- `grade_real_system_task` only ever reads `task.oracle_kind`/
            # `task.oracle_spec`, so a `RealSystemModifyTask` grades with zero new oracle code.
            accepted, note = grade_real_system_task(task, root, python_exe=python_exe)
            rec["accepted"] = bool(accepted)
            rec["note"] = note
            return rec
    except Exception as exc:  # never raise -- one bad task never aborts the whole suite
        rec["note"] = f"modify suite run raised unexpectedly: {exc}"
        return rec


def run_real_systems_modify_suite(tasks: "list[RealSystemModifyTask] | None" = None, *,
                                   llm: Any = None, python_exe: "str | None" = None) -> dict:
    """Run the leaves-OFF real-systems MODIFY suite: for each task, modify the declared
    ``start_system`` via ``harness.system_builder.modify_system(modules, mod_sentence, root,
    llm=llm)`` (leak-free -- the modify call sees only ``task.mod_sentence``, never
    ``task.oracle_spec``), assert the leaf path stayed OFF, and grade ONLY the tasks whose
    modification was actually ``applied``, by the task's own black-box oracle (reusing
    :func:`grade_real_system_task` -- no new oracle code). Returns ``{"results": [...],
    "aggregate": {"overall": {...}, "by_cls": {...}}}`` in the exact same shape as
    :func:`run_real_systems_suite`. Defaults to :data:`REAL_SYSTEMS_MODIFY_TASKS` when
    ``tasks`` is ``None``.

    NEVER raises: any per-task failure is recorded as that task's ``accepted=False`` and the
    suite continues to the next task."""
    tasks = REAL_SYSTEMS_MODIFY_TASKS if tasks is None else tasks
    python_exe = python_exe or sys.executable or "python"
    results = [_run_one_modify_task(task, llm=llm, python_exe=python_exe) for task in tasks]
    return {"results": results, "aggregate": _aggregate(results)}


# TASK-6 (REQ-7): MODIFY task (a) -- add an optional `base_delay` keyword parameter to the
# retry/backoff library, graded by the ALREADY-LANDED import_driver oracle (no new oracle
# code). `start_system` is a hand-authored CORRECT baseline `retry.py` matching REQ-3's
# original contract exactly (`retry(times, exceptions=Exception)`); the mod sentence's only
# ask is the new optional parameter + its role as the sleep duration -- every detail the
# oracle checks (parameter name, default, that it is now an accepted keyword) is derivable
# from that same visible sentence.
_RETRY_BASELINE_PY = (
    "import time\n\n\n"
    "def retry(times, exceptions=Exception):\n"
    "    def decorator(fn):\n"
    "        def wrapper(*args, **kwargs):\n"
    "            attempt = 0\n"
    "            while True:\n"
    "                attempt += 1\n"
    "                try:\n"
    "                    return fn(*args, **kwargs)\n"
    "                except exceptions:\n"
    "                    if attempt >= times:\n"
    "                        raise\n"
    "                    time.sleep(0.1)\n"
    "        return wrapper\n"
    "    return decorator\n"
)

_RETRY_BASE_DELAY_MOD_SENTENCE = (
    "Modify retry.py so that `retry(times, exceptions=Exception, base_delay=0.1)` accepts an "
    "ADDITIONAL optional keyword parameter named `base_delay`, with a default value of `0.1`, "
    "and uses that value as the duration passed to `time.sleep(...)` between each failed "
    "attempt (instead of any previously hardcoded duration). Every other existing aspect of "
    "its behavior -- accepting the same `times`/`exceptions` parameters, calling the wrapped "
    "callable, sleeping exactly once between each failed attempt, returning the first "
    "successful attempt's value immediately, and re-raising the final attempt's exception "
    "when every attempt fails -- is completely unchanged."
)

RETRY_BASE_DELAY_MODIFY_TASK = RealSystemModifyTask(
    name="retry-backoff-base-delay-modify",
    cls="library-modify",
    start_system={"retry.py": _RETRY_BASELINE_PY},
    mod_sentence=_RETRY_BASE_DELAY_MOD_SENTENCE,
    # #EXT-060-REQ-23 Start
    # TASK-18: the matching CREATE task's sentence (RETRY_BACKOFF_LIB_TASK's), forwarded to
    # `modify_system` as `spec_hint` so its deterministic repair chain sees the full original
    # contract, not just this MODIFY task's one-sentence delta.
    base_sentence=_RETRY_BACKOFF_SENTENCE,
    # #EXT-060-REQ-23 End
    oracle_kind="import",
    oracle_spec={
        "module": "retry",
        # `base_delay` is explicitly passed here -- a module that did NOT adopt the new
        # optional keyword raises TypeError on this very call, which cascades through
        # `decorated`/`result` (see harness/import_driver.py's `_bindings` chain) and fails
        # the `returns_equals` check below; a module that adopted it behaves exactly like
        # RETRY_BACKOFF_LIB_TASK's own oracle otherwise.
        "api_calls": [
            {"id": "make_decorator", "target": "retry", "args": [],
             "kwargs": {"times": 3, "base_delay": 0.05}},
            {"id": "decorated", "target": "make_decorator",
             "args": [{"__jaros_ref__": "flaky"}], "kwargs": {}},
            {"id": "result", "target": "decorated", "args": [], "kwargs": {}},
        ],
        "injected": {
            "clock": True,
            "spies": {
                "flaky": {"return_value": "success", "raise_exception": "ValueError",
                          "raise_count": 2},
            },
        },
        "checks": [
            {"kind": "returns_equals", "call_id": "result", "expected": "success"},
            {"kind": "call_count", "spy": "flaky", "expected": 3},
        ],
        "expected_sleep_calls": 2,
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)


# TASK-6 (REQ-7): MODIFY task (b) -- add an optional `--default VALUE` fallback to the
# INI-section config-query CLI, graded by the ALREADY-LANDED cli-exact oracle (no new oracle
# code). `start_system` is a hand-authored CORRECT baseline `main.py` matching REQ-4's
# original contract exactly (exactly two argv args, nonzero exit + no output when absent).
_INI_QUERY_BASELINE_PY = (
    "import sys\n\n\n"
    "def parse_ini(text):\n"
    "    sections = {}\n"
    "    current = None\n"
    "    for line in text.splitlines():\n"
    "        line = line.strip()\n"
    "        if not line:\n"
    "            continue\n"
    "        if line.startswith('[') and line.endswith(']'):\n"
    "            current = line[1:-1]\n"
    "            sections.setdefault(current, {})\n"
    "            continue\n"
    "        if current is not None and '=' in line:\n"
    "            key, _, value = line.partition('=')\n"
    "            sections[current][key.strip()] = value.strip()\n"
    "    return sections\n\n\n"
    "def main():\n"
    "    if len(sys.argv) != 3:\n"
    "        sys.exit(1)\n"
    "    section, key = sys.argv[1], sys.argv[2]\n"
    "    sections = parse_ini(sys.stdin.read())\n"
    "    if section in sections and key in sections[section]:\n"
    "        print(sections[section][key])\n"
    "        return\n"
    "    sys.exit(1)\n\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_INI_DEFAULT_FLAG_MOD_SENTENCE = (
    "Modify main.py so that it ALSO accepts two additional optional trailing command-line "
    "arguments, `--default` followed by a VALUE (i.e. it may be invoked as `python main.py "
    "<section> <key> --default VALUE`, four arguments total, in addition to the existing "
    "exactly-two-argument form). When invoked with `--default VALUE` and the requested "
    "section or key is ABSENT from the INI text, it prints VALUE followed by a single "
    "trailing newline and exits 0 (instead of printing nothing and exiting nonzero). When "
    "the section and key ARE both present, the found value is printed exactly as before and "
    "`--default VALUE` (if supplied) is ignored. When `--default VALUE` is NOT supplied, "
    "behavior for an absent section/key is completely unchanged (print nothing, exit "
    "nonzero); any other argument count is still rejected (print nothing, exit nonzero)."
)

# Absent key ("missing") with `--default fallback` supplied -- the baseline (unmodified)
# main.py would print nothing and exit nonzero for this input; a correct modification prints
# exactly "fallback\n".
_INI_DEFAULT_FLAG_STDIN = (
    "[server]\n"
    "host = localhost\n"
    "port = 8080\n"
)

INI_DEFAULT_FLAG_MODIFY_TASK = RealSystemModifyTask(
    name="ini-section-query-default-flag-modify",
    cls="config-cli-modify",
    start_system={"main.py": _INI_QUERY_BASELINE_PY},
    mod_sentence=_INI_DEFAULT_FLAG_MOD_SENTENCE,
    # #EXT-060-REQ-23 Start
    # TASK-18: the matching CREATE task's sentence (INI_SECTION_QUERY_TASK's).
    base_sentence=_INI_SECTION_QUERY_SENTENCE,
    # #EXT-060-REQ-23 End
    oracle_kind="cli-exact",
    oracle_spec={
        "argv": ["server", "missing", "--default", "fallback"],
        "stdin": _INI_DEFAULT_FLAG_STDIN,
        "expected_stdout": "fallback\n",
    },
)

REAL_SYSTEMS_MODIFY_TASKS: "list[RealSystemModifyTask]" = [
    RETRY_BASE_DELAY_MODIFY_TASK, INI_DEFAULT_FLAG_MODIFY_TASK,
]
# #EXT-060-REQ-7 End


# #EXT-060-REQ-8 Start
# TASK-7: the UNIFIED CANONICAL SCOREBOARD -- runs BOTH halves and reports ONE headline
# number, the combined pass@1. This is the entrypoint the ROADMAP/governance loop reports
# from going forward; the CREATE-only `run_real_systems_suite` and the new MODIFY-only
# `run_real_systems_modify_suite` remain independently callable (e.g. for the killable
# per-task subprocess runners), but neither is "the number" on its own anymore.
def _combined_rate(create_results: "list[dict]", modify_results: "list[dict]") -> dict:
    n = len(create_results) + len(modify_results)
    passed = (sum(1 for r in create_results if r.get("accepted")) +
              sum(1 for r in modify_results if r.get("accepted")))
    return {"n": n, "passed": passed, "pass_rate": (passed / n) if n else 0.0}


def run_canonical_scoreboard(*, llm: Any = None,
                              create_tasks: "list[RealSystemTask] | None" = None,
                              modify_tasks: "list[RealSystemModifyTask] | None" = None,
                              python_exe: "str | None" = None) -> dict:
    """Run BOTH halves of the canonical real-systems scoreboard (CREATE via
    :func:`run_real_systems_suite`, MODIFY via :func:`run_real_systems_modify_suite`) and
    report the ONE tracked headline number alongside each half's own breakdown. Returns
    ``{"create": <run_real_systems_suite result>, "modify": <run_real_systems_modify_suite
    result>, "combined": {"n": int, "passed": int, "pass_rate": float}}`` -- ``combined`` is
    ``(create passes + modify passes) / (create n + modify n)``, guarded against
    division-by-zero (``pass_rate`` is ``0.0`` when both halves are empty). NEVER raises: each
    half's own runner already absorbs every per-task failure."""
    create = run_real_systems_suite(create_tasks, llm=llm, python_exe=python_exe)
    modify = run_real_systems_modify_suite(modify_tasks, llm=llm, python_exe=python_exe)
    combined = _combined_rate(create.get("results") or [], modify.get("results") or [])
    return {"create": create, "modify": modify, "combined": combined}
# #EXT-060-REQ-8 End


# #EXT-060-REQ-9 Start
# TASK-8: the FIRST genuinely-SaaS-shaped task -- a stdlib REST API (http.server + sqlite3 + json,
# no framework) exposing CRUD over an `items` resource, persisted to SQLite, graded by the new
# "service" oracle_kind (real HTTP over a real subprocess server + an INDEPENDENT post-teardown
# SQLite read -- never trusting the service's own HTTP responses for durability).
_REST_SQLITE_CRUD_SENTENCE = (
    "Write a Python web service in a file named main.py using only the standard library "
    "(http.server + sqlite3 + json). On startup it listens on the TCP port given by the PORT "
    "environment variable and stores data in a SQLite database file named data.db in the current "
    "directory (create the table if missing). It serves a JSON REST API for `items`, each item "
    "having an integer id (autoincrement) and a string `name`: `POST /items` with a JSON body "
    "`{\"name\": ...}` inserts a new item and responds 201 with the created item as JSON including "
    "its id; `GET /items` responds 200 with a JSON array of all items; `GET /items/<id>` responds "
    "200 with that item as JSON, or 404 if absent; `DELETE /items/<id>` deletes it and responds "
    "204, or 404 if absent. Data must persist in data.db across process restarts."
)

REST_SQLITE_CRUD_TASK = RealSystemTask(
    name="rest-sqlite-items-crud-service",
    cls="rest-api",
    sentence=_REST_SQLITE_CRUD_SENTENCE,
    oracle_kind="service",
    oracle_spec={
        "entry": "main.py",
        "http_checks": [
            # A SECOND item ("beta") is created and deliberately never deleted below, purely so
            # the independent post-teardown db assertion (>= 1 row) is honestly satisfiable even
            # though item "alpha" (id 1) IS deleted later in this same sequence -- a correct
            # implementation genuinely ends the run with exactly one persisted row (id 2, "beta"),
            # never zero, so `min_rows: 1` never accidentally rejects a correct build.
            {"method": "POST", "path": "/items", "json_body": {"name": "alpha"},
             "status": 201, "json_contains": {"name": "alpha", "id": 1}},
            {"method": "POST", "path": "/items", "json_body": {"name": "beta"},
             "status": 201, "json_contains": {"name": "beta", "id": 2}},
            {"method": "GET", "path": "/items", "status": 200, "body_contains": "alpha"},
            {"method": "GET", "path": "/items/1", "status": 200,
             "json_contains": {"name": "alpha"}},
            {"method": "DELETE", "path": "/items/1", "status": 204},
            {"method": "GET", "path": "/items/1", "status": 404},
        ],
        "db": {"path": "data.db", "min_rows": 1},
    },
)

REAL_SYSTEMS_TASKS.append(REST_SQLITE_CRUD_TASK)


# TASK-8: the correct baseline stdlib CRUD service used both as the MODIFY task's known-good
# `start_system` and (in tests/test_ext060_service_oracle.py) as the hand-authored CORRECT fixture
# proving the "service" oracle_kind grades REST_SQLITE_CRUD_TASK honestly. Matches
# REST_SQLITE_CRUD_TASK's contract exactly (no `PUT` -- that is what REST_SQLITE_ADD_UPDATE_MODIFY
# adds).
_REST_SQLITE_BASELINE_PY = '''import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

DB_PATH = "data.db"


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS items ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"
    )
    conn.commit()
    return conn


CONN = _init_db()


def _item_id(path):
    parts = urlparse(path).path.strip("/").split("/")
    if len(parts) == 2 and parts[0] == "items":
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/items":
            cur = CONN.execute("SELECT id, name FROM items ORDER BY id")
            rows = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
            self._send_json(200, rows)
            return
        item_id = _item_id(self.path)
        if item_id is not None:
            cur = CONN.execute("SELECT id, name FROM items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                self._send_json(404, {"error": "not found"})
            else:
                self._send_json(200, {"id": row[0], "name": row[1]})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/items":
            self._send_json(404, {"error": "not found"})
            return
        data = self._read_json()
        name = data.get("name")
        cur = CONN.execute("INSERT INTO items (name) VALUES (?)", (name,))
        CONN.commit()
        self._send_json(201, {"id": cur.lastrowid, "name": name})

    def do_DELETE(self):
        item_id = _item_id(self.path)
        if item_id is None:
            self._send_json(404, {"error": "not found"})
            return
        cur = CONN.execute("DELETE FROM items WHERE id = ?", (item_id,))
        CONN.commit()
        if cur.rowcount == 0:
            self._send_json(404, {"error": "not found"})
        else:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ["PORT"])
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
'''
# #EXT-060-REQ-9 End


# #EXT-060-REQ-11 Start
# TASK-9: the FIRST AGENT-shaped task -- a plain, stdlib-only, single-file tool-calling agent,
# graded by the new "agent" oracle_kind (a scripted stub model + controlled tool sandbox,
# `harness.agent_oracle`, no real model/Jetson call anywhere in this measurement). jaros-code is
# itself a Jaros agent system, so this is a high-priority real-systems class. The sentence pins
# the EXACT injection contract `harness/agent_oracle.py` fixes (env vars, request/response
# shapes, the final-answer sentinel) -- the SAME agent code graded here is the one a real build
# would point at the Jetson llama.cpp endpoint instead, only the endpoint ever changes.
_PLAIN_AGENT_SENTENCE = (
    "Write a single-file Python program using only the standard library (no third-party "
    "packages) in a file named main.py, implementing a minimal tool-calling AGENT LOOP against "
    "an OpenAI-compatible chat-completions endpoint. On startup, read the goal from the first "
    "command-line argument (sys.argv[1]). Read the base URL for the chat-completions endpoint "
    "from the OPENAI_BASE_URL environment variable, and the base URL for tool invocations from "
    "the JAROS_TOOL_URL environment variable. Maintain a list of chat messages, starting with "
    "exactly one message `{\"role\": \"user\", \"content\": <goal>}`. Repeatedly: send an HTTP "
    "POST request with a JSON body `{\"model\": \"stub\", \"messages\": <the current message "
    "list>}` to `f\"{OPENAI_BASE_URL}/chat/completions\"`, and parse the JSON response's "
    "`response[\"choices\"][0][\"message\"]`. If that message has a non-empty `\"tool_calls\"` "
    "list, take its first entry, whose `[\"function\"][\"name\"]` is the tool name to call and "
    "whose `[\"function\"][\"arguments\"]` is a JSON-encoded STRING of the tool's arguments "
    "(parse it with `json.loads`); append that assistant message (including its `\"tool_calls\"`) "
    "to the message list, then send an HTTP POST request with the parsed arguments as a JSON "
    "body to `f\"{JAROS_TOOL_URL}/<tool_name>\"`, read the JSON response's `\"observation\"` "
    "value, append a message `{\"role\": \"tool\", \"tool_call_id\": <that tool call's \"id\">, "
    "\"content\": json.dumps(<the observation value>)}` to the message list, and repeat the loop "
    "(send another chat-completions request). Otherwise (the message has no tool_calls), take "
    "its `\"content\"` string as the final answer: print EXACTLY the string "
    "`\"__JAROS_AGENT_FINAL__\"` followed by that content followed by `\"__END__\"`, with no "
    "other output anywhere, then exit with status 0."
)

PLAIN_AGENT_TASK = RealSystemTask(
    name="plain-tool-calling-agent",
    cls="agent",
    sentence=_PLAIN_AGENT_SENTENCE,
    oracle_kind="agent",
    oracle_spec={
        "entry": "main.py",
        # A 2-tool-call-then-final script -- a correct agent must call BOTH tools, in order, with
        # the exact arguments the scripted model names, feed each observation back into the next
        # request, then print the final answer once the model stops naming a tool.
        "script": [
            tool_call_turn("list_files", {"path": "."}),
            tool_call_turn("read_file", {"path": "notes.txt"}),
            final_turn("the notes say: remember the milk"),
        ],
        "tools": {
            "list_files": {"files": ["notes.txt"]},
            "read_file": {"content": "remember the milk"},
        },
        "goal": "find and read the notes file",
        "expect_tool_calls": [
            {"name": "list_files", "args": {"path": "."}},
            {"name": "read_file", "args": {"path": "notes.txt"}},
        ],
        "expect_final_contains": "remember the milk",
        "expect_terminated": True,
    },
)

REAL_SYSTEMS_TASKS.append(PLAIN_AGENT_TASK)
# #EXT-060-REQ-11 End


# #EXT-060-REQ-10 Start
# TASK-8: the first SaaS-shaped MODIFY task -- add a `PUT /items/<id>` endpoint to the baseline
# CRUD service above. Graded by the SAME "service" oracle_kind dispatcher REQ-9 lands -- no new
# oracle code for the MODIFY half, mirroring how REQ-7's MODIFY tasks reused REQ-3/REQ-4's oracle
# dispatch verbatim.
_REST_SQLITE_PUT_MOD_SENTENCE = (
    "Add a `PUT /items/<id>` endpoint that accepts a JSON body `{\"name\": ...}`, updates that "
    "item's name, and responds 200 with the updated item as JSON (or 404 if the item does not "
    "exist)."
)

REST_SQLITE_ADD_UPDATE_MODIFY = RealSystemModifyTask(
    name="rest-sqlite-items-put-modify",
    cls="rest-api-modify",
    start_system={"main.py": _REST_SQLITE_BASELINE_PY},
    mod_sentence=_REST_SQLITE_PUT_MOD_SENTENCE,
    # #EXT-060-REQ-23 Start
    # TASK-18: the matching CREATE task's sentence (REST_SQLITE_CRUD_TASK's) -- the bare
    # `mod_sentence` above ("Add a `PUT /items/<id>` endpoint...") does not itself mention
    # `http.server`/"web service"/the PORT env var, so WITHOUT this `spec_demands_stdlib_http_
    # service` never fires on this MODIFY task's repair chain; combined with `mod_sentence` it
    # does (verified in tests/test_ext060_spec_hint.py).
    base_sentence=_REST_SQLITE_CRUD_SENTENCE,
    # #EXT-060-REQ-23 End
    oracle_kind="service",
    oracle_spec={
        "entry": "main.py",
        "http_checks": [
            # Two items seeded: id 1 ("alpha") is updated via PUT then deleted below (exercising
            # the NEW endpoint plus the still-working DELETE/404 regression path, plus a PUT
            # against the now-deleted id); id 2 ("keep") is left alone so the independent
            # post-teardown db assertion (>= 1 row) stays honestly satisfiable.
            {"method": "POST", "path": "/items", "json_body": {"name": "alpha"},
             "status": 201, "json_contains": {"name": "alpha", "id": 1}},
            {"method": "POST", "path": "/items", "json_body": {"name": "keep"},
             "status": 201, "json_contains": {"name": "keep", "id": 2}},
            {"method": "PUT", "path": "/items/1", "json_body": {"name": "beta"},
             "status": 200, "json_contains": {"name": "beta", "id": 1}},
            {"method": "GET", "path": "/items/1", "status": 200,
             "json_contains": {"name": "beta"}},
            {"method": "DELETE", "path": "/items/1", "status": 204},
            {"method": "GET", "path": "/items/1", "status": 404},
            {"method": "PUT", "path": "/items/1", "json_body": {"name": "gamma"}, "status": 404},
        ],
        "db": {"path": "data.db", "min_rows": 1},
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(REST_SQLITE_ADD_UPDATE_MODIFY)
# #EXT-060-REQ-10 End


# #EXT-060-REQ-12 Start
# TASK-9: the FIRST AGENT-shaped MODIFY task -- add a maximum-steps guard to the plain agent
# above, graded by the SAME "agent" oracle_kind dispatcher REQ-11 lands (no new oracle code,
# mirroring how REQ-7/REQ-10's MODIFY tasks reuse their CREATE half's oracle dispatch verbatim).
# `start_system` is the UNGUARDED baseline (an unbounded `while True:` loop -- it never stops
# asking the model what to do next); a correct modification must recognize when it has made 3
# tool calls in a row without ever getting a final (non-tool-call) answer and stop itself.
_AGENT_UNGUARDED_BASELINE_PY = '''import json
import os
import sys
import urllib.request


def _post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    goal = sys.argv[1] if len(sys.argv) > 1 else ""
    base_url = os.environ["OPENAI_BASE_URL"]
    tool_url = os.environ["JAROS_TOOL_URL"]
    messages = [{"role": "user", "content": goal}]

    while True:
        resp = _post(base_url + "/chat/completions", {"model": "stub", "messages": messages})
        message = resp["choices"][0]["message"]
        tool_calls = message.get("tool_calls")
        if tool_calls:
            call = tool_calls[0]
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
            observed = _post(tool_url + "/" + name, args)
            messages.append({
                "role": "tool", "tool_call_id": call["id"],
                "content": json.dumps(observed.get("observation")),
            })
            continue
        content = message.get("content") or ""
        print("__JAROS_AGENT_FINAL__" + content + "__END__", flush=True)
        return


if __name__ == "__main__":
    main()
'''

_AGENT_STEP_GUARD_MOD_SENTENCE = (
    "Modify main.py so that it ALSO tracks how many tool calls it has made IN A ROW without yet "
    "receiving a final (non-tool-call) answer from the model. If that count reaches 3 tool calls "
    "without a final answer, STOP making any further chat-completions requests: print EXACTLY "
    "the string `\"__JAROS_AGENT_FINAL__gave up after 3 tool calls__END__\"`, with no other "
    "output anywhere, and exit with status 0 -- instead of continuing the loop. Every other "
    "existing aspect of its behavior (reading the goal from sys.argv[1], the "
    "OPENAI_BASE_URL/JAROS_TOOL_URL request/response shapes, following an ordinary tool call, "
    "and printing an ordinary final answer when the model actually returns one before the count "
    "reaches 3) is completely unchanged."
)

AGENT_ADD_STEP_GUARD_MODIFY = RealSystemModifyTask(
    name="plain-agent-add-step-guard-modify",
    cls="agent-modify",
    start_system={"main.py": _AGENT_UNGUARDED_BASELINE_PY},
    mod_sentence=_AGENT_STEP_GUARD_MOD_SENTENCE,
    # #EXT-060-REQ-23 Start
    # TASK-18: the matching CREATE task's sentence (PLAIN_AGENT_TASK's) -- pins the
    # OPENAI_BASE_URL/JAROS_TOOL_URL/tool_calling/chat-completions protocol contract
    # `spec_demands_tool_calling_agent` keys on, so combined with `mod_sentence` the repair
    # chain's agent scaffold sees the full protocol (verified in
    # tests/test_ext060_spec_hint.py).
    base_sentence=_PLAIN_AGENT_SENTENCE,
    # #EXT-060-REQ-23 End
    oracle_kind="agent",
    oracle_spec={
        "entry": "main.py",
        # A single tool_call turn -- `agent_oracle`'s stub repeats the LAST scripted turn once
        # the script is exhausted, so this same turn is served for every chat-completions
        # request the agent makes -- NEVER a final turn, so an UNGUARDED agent would keep asking
        # forever (a script that "would loop forever without the guard"). `max_steps` is kept
        # small and well past the guard's pinned count (3) so an unguarded baseline's failure is
        # caught FAST (the stub starts refusing further requests once max_steps is exceeded,
        # which an unguarded agent's own unhandled HTTP error surfaces as a prompt crash) rather
        # than waiting out the oracle's full overall timeout.
        "script": [tool_call_turn("poll", {})],
        "tools": {"poll": "still going"},
        "goal": "poll until done",
        "max_steps": 8,
        "expect_tool_calls": [{"name": "poll"}, {"name": "poll"}, {"name": "poll"}],
        "expect_final_contains": "gave up",
        "expect_terminated": True,
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(AGENT_ADD_STEP_GUARD_MODIFY)
# #EXT-060-REQ-12 End


# #EXT-060-REQ-13 Start
# TASK-10: the FIRST LIFECYCLE-shaped task -- a stdlib order state machine, graded by the new
# "state_machine" oracle_kind (an entity class driven through a scripted legal/illegal transition
# script via `harness.state_machine_oracle`, no real model/Jetson call anywhere in this
# measurement). Illegal transitions (ship before pay, cancel after delivery) must raise ValueError
# and leave state unchanged -- the honesty core `state_machine_oracle` exists to catch.
_ORDER_LIFECYCLE_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named order.py, "
    "using only the standard library, defining exactly one public class named `Order` modeling an "
    "order lifecycle state machine. `Order()` (no constructor arguments) creates a new order whose "
    "initial state is the string `\"created\"`. The class exposes a real Python `@property` named "
    "`state` that returns the order's current state as one of the strings `\"created\"`, "
    "`\"paid\"`, `\"shipped\"`, `\"delivered\"`, or `\"cancelled\"`. It defines exactly four "
    "zero-argument action methods: `pay()` moves the order from `\"created\"` to `\"paid\"`; "
    "`ship()` moves it from `\"paid\"` to `\"shipped\"`; `deliver()` moves it from `\"shipped\"` to "
    "`\"delivered\"`; `cancel()` moves it from `\"created\"` to `\"cancelled\"`. Each of these four "
    "methods is legal ONLY from the exact source state named above; calling any of them from any "
    "OTHER current state (for example calling `ship()` before `pay()` has been called, or calling "
    "`cancel()` after the order has been delivered) must instead raise `ValueError` and must leave "
    "the order's `state` COMPLETELY UNCHANGED -- no partial mutation before the raise."
)

# The order.py baseline used both as ORDER_ADD_REFUND_MODIFY's known-good `start_system` and (in
# tests/test_ext060_lifecycle_inventory.py) as the hand-authored CORRECT fixture proving the
# "state_machine" oracle_kind grades ORDER_LIFECYCLE_TASK honestly. Matches ORDER_LIFECYCLE_TASK's
# contract exactly (no `refund()` -- that is what ORDER_ADD_REFUND_MODIFY adds).
_ORDER_BASELINE_PY = (
    "class Order:\n"
    "    _TRANSITIONS = {\n"
    "        (\"created\", \"pay\"): \"paid\",\n"
    "        (\"paid\", \"ship\"): \"shipped\",\n"
    "        (\"shipped\", \"deliver\"): \"delivered\",\n"
    "        (\"created\", \"cancel\"): \"cancelled\",\n"
    "    }\n"
    "\n"
    "    def __init__(self):\n"
    "        self._state = \"created\"\n"
    "\n"
    "    @property\n"
    "    def state(self):\n"
    "        return self._state\n"
    "\n"
    "    def _transition(self, action):\n"
    "        key = (self._state, action)\n"
    "        if key not in self._TRANSITIONS:\n"
    "            raise ValueError(f\"illegal transition: {action} from {self._state}\")\n"
    "        self._state = self._TRANSITIONS[key]\n"
    "\n"
    "    def pay(self):\n"
    "        self._transition(\"pay\")\n"
    "\n"
    "    def ship(self):\n"
    "        self._transition(\"ship\")\n"
    "\n"
    "    def deliver(self):\n"
    "        self._transition(\"deliver\")\n"
    "\n"
    "    def cancel(self):\n"
    "        self._transition(\"cancel\")\n"
)

ORDER_LIFECYCLE_TASK = RealSystemTask(
    name="order-lifecycle-state-machine",
    cls="lifecycle",
    sentence=_ORDER_LIFECYCLE_SENTENCE,
    oracle_kind="state_machine",
    oracle_spec={
        "module": "order",
        "entity": "Order",
        "spec": {
            "states": ["created", "paid", "shipped", "delivered", "cancelled"],
            "initial": "created",
            "transitions": {
                "created:pay": "paid",
                "paid:ship": "shipped",
                "shipped:deliver": "delivered",
                "created:cancel": "cancelled",
            },
            # Illegal ship-before-pay FIRST (must be rejected), then the full legal path to
            # "delivered", then an illegal cancel-after-delivered (must also be rejected) -- both
            # the honesty core (illegal transitions refused) and the legal path are exercised.
            "drive": [
                {"action": "ship", "expect": "reject"},
                {"action": "pay", "expect": "accept"},
                {"action": "ship", "expect": "accept"},
                {"action": "deliver", "expect": "accept"},
                {"action": "cancel", "expect": "reject"},
            ],
            "expect_final": "delivered",
        },
    },
)

REAL_SYSTEMS_TASKS.append(ORDER_LIFECYCLE_TASK)
# #EXT-060-REQ-13 End


# #EXT-060-REQ-14 Start
# TASK-10: the first LIFECYCLE-shaped MODIFY task -- add a `refund()` transition to the order
# state machine above. Graded by the SAME "state_machine" oracle_kind dispatcher REQ-13 lands -- no
# new oracle code, mirroring how REQ-7/REQ-10/REQ-12's MODIFY tasks reuse their CREATE half's
# oracle dispatch verbatim.
_ORDER_ADD_REFUND_MOD_SENTENCE = (
    "Modify order.py so that `Order` ALSO supports a new zero-argument action method named "
    "`refund()`. Calling `refund()` while the order's current state is `\"delivered\"` moves it to "
    "a NEW state, the string `\"refunded\"` (extend the existing `state` property so it can also "
    "report `\"refunded\"`). Calling `refund()` from ANY state other than `\"delivered\"` "
    "(including `\"refunded\"` itself) must instead raise `ValueError` and must leave the order's "
    "`state` COMPLETELY UNCHANGED, exactly like every other illegal transition. Every other "
    "existing aspect of its behavior -- the `pay()`/`ship()`/`deliver()`/`cancel()` methods, their "
    "exact legal source states, the `ValueError`-on-illegal-transition-with-unchanged-state "
    "contract, and the `state` property -- is completely unchanged."
)

ORDER_ADD_REFUND_MODIFY = RealSystemModifyTask(
    name="order-lifecycle-add-refund-modify",
    cls="lifecycle-modify",
    start_system={"order.py": _ORDER_BASELINE_PY},
    mod_sentence=_ORDER_ADD_REFUND_MOD_SENTENCE,
    # #EXT-060-REQ-23 Start
    # TASK-18: the matching CREATE task's sentence (ORDER_LIFECYCLE_TASK's).
    base_sentence=_ORDER_LIFECYCLE_SENTENCE,
    # #EXT-060-REQ-23 End
    oracle_kind="state_machine",
    oracle_spec={
        "module": "order",
        "entity": "Order",
        "spec": {
            "states": ["created", "paid", "shipped", "delivered", "cancelled", "refunded"],
            "initial": "created",
            "transitions": {
                "created:pay": "paid",
                "paid:ship": "shipped",
                "shipped:deliver": "delivered",
                "created:cancel": "cancelled",
                "delivered:refund": "refunded",
            },
            # Regression of the original illegal ship-before-pay check, THEN a NEW illegal refund
            # from an earlier (non-"delivered") state, THEN the full legal path to "delivered",
            # THEN the new legal refund transition -- a module that never added `refund()` at all
            # fails immediately (AttributeError cascades through drive_import's own checks); a
            # module that added it UNGUARDED (legal from any state) fails the earlier illegal-
            # refund check.
            "drive": [
                {"action": "ship", "expect": "reject"},
                {"action": "refund", "expect": "reject"},
                {"action": "pay", "expect": "accept"},
                {"action": "ship", "expect": "accept"},
                {"action": "deliver", "expect": "accept"},
                {"action": "refund", "expect": "accept"},
            ],
            "expect_final": "refunded",
        },
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(ORDER_ADD_REFUND_MODIFY)
# #EXT-060-REQ-14 End


# #EXT-060-REQ-15 Start
# TASK-11: the FIRST INVENTORY-shaped task -- a stdlib single-SKU stock-reservation class, graded
# by the new "conservation" oracle_kind (an entity class driven through a scripted legal/illegal
# operation script via `harness.conservation_oracle`, no real model/Jetson call anywhere in this
# measurement). An oversell attempt must raise ValueError and leave every quantity unchanged --
# the honesty core `conservation_oracle` exists to catch.
_INVENTORY_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named inventory.py, "
    "using only the standard library, defining exactly one public class named `Inventory` "
    "modeling single-SKU stock reservation. `Inventory(initial_stock)` (exactly one positional "
    "constructor argument, a non-negative integer) creates stock tracking for one SKU whose "
    "`available` units start at `initial_stock` and whose `reserved` units start at `0`. It "
    "exposes two zero-argument reader methods, `available()` and `reserved()`, each returning the "
    "current integer value of that quantity. It defines two methods that each take one positional "
    "integer argument, `qty`: `reserve(qty)` moves `qty` units from `available` to `reserved` "
    "(decreasing `available` by `qty` and increasing `reserved` by `qty`) -- but if `qty` is "
    "GREATER than the CURRENT `available` count (an oversell), it must instead raise `ValueError` "
    "and leave BOTH `available` and `reserved` COMPLETELY UNCHANGED; `release(qty)` moves `qty` "
    "units back from `reserved` to `available` (increasing `available` by `qty` and decreasing "
    "`reserved` by `qty`). The total of `available` plus `reserved` must never change across any "
    "successful call -- units are only ever moved between the two, never created or destroyed."
)

# The inventory.py baseline used both as INVENTORY_ADD_BACKORDER_MODIFY's known-good
# `start_system` and (in tests/test_ext060_lifecycle_inventory.py) as the hand-authored CORRECT
# fixture proving the "conservation" oracle_kind grades INVENTORY_TASK honestly. Matches
# INVENTORY_TASK's contract exactly (no `backorder()` -- that is what
# INVENTORY_ADD_BACKORDER_MODIFY adds).
_INVENTORY_BASELINE_PY = (
    "class Inventory:\n"
    "    def __init__(self, initial_stock):\n"
    "        self._available = initial_stock\n"
    "        self._reserved = 0\n"
    "\n"
    "    def available(self):\n"
    "        return self._available\n"
    "\n"
    "    def reserved(self):\n"
    "        return self._reserved\n"
    "\n"
    "    def reserve(self, qty):\n"
    "        if qty > self._available:\n"
    "            raise ValueError(f\"cannot reserve {qty}: only {self._available} available\")\n"
    "        self._available -= qty\n"
    "        self._reserved += qty\n"
    "\n"
    "    def release(self, qty):\n"
    "        if qty > self._reserved:\n"
    "            raise ValueError(f\"cannot release {qty}: only {self._reserved} reserved\")\n"
    "        self._reserved -= qty\n"
    "        self._available += qty\n"
)

INVENTORY_TASK = RealSystemTask(
    name="inventory-no-oversell-reservation",
    cls="inventory",
    sentence=_INVENTORY_SENTENCE,
    oracle_kind="conservation",
    oracle_spec={
        "module": "inventory",
        "entity": "Inventory",
        "spec": {
            "quantities": ["available", "reserved"],
            "initial": {"available": 100, "reserved": 0},
            "construct_args": [100],
            # Illegal oversell FIRST (150 of 100 -- must be rejected), then a legal reserve (30)
            # and a legal release (10), landing on available=80, reserved=20.
            "drive": [
                {"action": "reserve", "args": [150], "expect": "reject"},
                {"action": "reserve", "args": [30], "expect": "accept",
                 "deltas": {"available": -30, "reserved": 30}},
                {"action": "release", "args": [10], "expect": "accept",
                 "deltas": {"available": 10, "reserved": -10}},
            ],
            "expect_final": {"available": 80, "reserved": 20},
        },
    },
)

REAL_SYSTEMS_TASKS.append(INVENTORY_TASK)
# #EXT-060-REQ-15 End


# #EXT-060-REQ-16 Start
# TASK-11: the first INVENTORY-shaped MODIFY task -- add a `backorder()` method to the inventory
# class above that records demand beyond available WITHOUT ever touching `available`/`reserved`
# (never oversells committed stock). Graded by the SAME "conservation" oracle_kind dispatcher
# REQ-15 lands -- no new oracle code, mirroring how REQ-7/REQ-10/REQ-12/REQ-14's MODIFY tasks reuse
# their CREATE half's oracle dispatch verbatim. `spec["quantities"]` is extended with a mirrored
# pair (`backordered`/`backorder_credit`, always summing to exactly 0) so the conservation law
# (every accept op's deltas sum to zero across ALL declared quantities) stays satisfiable while
# still independently proving `available`/`reserved` are left completely undisturbed by
# `backorder()` -- the mirror pair is fully pinned in the visible mod_sentence, no oracle leak.
_INVENTORY_BACKORDER_MOD_SENTENCE = (
    "Modify inventory.py so that `Inventory` ALSO supports a method `backorder(qty)` (one "
    "positional integer argument) that records demand for `qty` units that could not be filled "
    "from current stock. Calling `backorder(qty)` must NEVER change `available` or `reserved` in "
    "any way -- it only records the extra demand, and it never raises (it always succeeds, for "
    "any nonnegative `qty`), so committed stock (already-reserved units) can never be oversold by "
    "it. To make that demand visible and independently checkable, the class must ALSO expose two "
    "new zero-argument reader methods that always move together as an exact mirror pair: "
    "`backordered()`, which starts at `0` and increases by `qty` on every `backorder(qty)` call "
    "(the running total of unfilled demand), and `backorder_credit()`, which starts at `0` and "
    "DECREASES by `qty` on every `backorder(qty)` call, so `backordered()` plus "
    "`backorder_credit()` is always exactly `0` (proving the demand is only ever recorded, never "
    "allowed to silently create or destroy units). Every other existing aspect of `Inventory`'s "
    "behavior -- `reserve(qty)`/`release(qty)`, the oversell-rejection contract, and the "
    "`available()`/`reserved()` readers -- is completely unchanged."
)

INVENTORY_ADD_BACKORDER_MODIFY = RealSystemModifyTask(
    name="inventory-add-backorder-modify",
    cls="inventory-modify",
    start_system={"inventory.py": _INVENTORY_BASELINE_PY},
    mod_sentence=_INVENTORY_BACKORDER_MOD_SENTENCE,
    # #EXT-060-REQ-23 Start
    # TASK-18: the matching CREATE task's sentence (INVENTORY_TASK's).
    base_sentence=_INVENTORY_SENTENCE,
    # #EXT-060-REQ-23 End
    oracle_kind="conservation",
    oracle_spec={
        "module": "inventory",
        "entity": "Inventory",
        "spec": {
            "quantities": ["available", "reserved", "backordered", "backorder_credit"],
            "initial": {"available": 100, "reserved": 0, "backordered": 0, "backorder_credit": 0},
            "construct_args": [100],
            # Regression of the original illegal oversell + legal reserve, THEN a NEW
            # `backorder(20)` op whose deltas touch ONLY the mirror pair (proving available/
            # reserved are left untouched), THEN the original legal release -- a module that never
            # added `backorder()`/`backordered()`/`backorder_credit()` at all fails immediately
            # (AttributeError cascades through drive_import's own checks); a module whose
            # `backorder()` incorrectly mutates available/reserved fails the post-op reader check.
            "drive": [
                {"action": "reserve", "args": [150], "expect": "reject"},
                {"action": "reserve", "args": [30], "expect": "accept",
                 "deltas": {"available": -30, "reserved": 30}},
                {"action": "backorder", "args": [20], "expect": "accept",
                 "deltas": {"backordered": 20, "backorder_credit": -20}},
                {"action": "release", "args": [10], "expect": "accept",
                 "deltas": {"available": 10, "reserved": -10}},
            ],
            "expect_final": {
                "available": 80, "reserved": 20, "backordered": 20, "backorder_credit": -20,
            },
        },
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(INVENTORY_ADD_BACKORDER_MODIFY)
# #EXT-060-REQ-16 End


# #EXT-060-REQ-17 Start
# TASK-12: the FIRST FINTECH-LEDGER-shaped task -- a stdlib double-entry journal class over three
# named accounts, graded by the new "double_entry" oracle_kind (an entity class driven through a
# scripted balanced/unbalanced posting script via `harness.double_entry_oracle`, no real
# model/Jetson call anywhere in this measurement). An unbalanced posting (debits != credits) must
# raise ValueError and leave every account balance unchanged -- the honesty core
# `double_entry_oracle` exists to catch (the debits-equal-credits invariant, not self-report).
_LEDGER_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named ledger.py, "
    "using only the standard library, defining exactly one public class named `Ledger` modeling "
    "a double-entry journal over exactly three named accounts: `cash`, `revenue`, and `expense`. "
    "`Ledger()` (no constructor arguments) creates a ledger where all three accounts start at a "
    "balance of `0` (an exact integer number of cents). It exposes three zero-argument reader "
    "methods, `cash()`, `revenue()`, and `expense()`, each returning that account's CURRENT "
    "integer balance in cents. It defines exactly one method, `post(legs)`, taking one positional "
    "argument -- a list of leg dicts, each either `{\"account\": <name>, \"debit\": <cents>}` or "
    "`{\"account\": <name>, \"credit\": <cents>}`, where `<name>` is one of `cash`/`revenue`/"
    "`expense` and `<cents>` is a positive integer. Posting a leg to an account with `debit` ADDS "
    "that many cents to the account's balance; posting a leg with `credit` SUBTRACTS that many "
    "cents from the account's balance. If the legs in one call to `post(legs)` are BALANCED (the "
    "sum of every `debit` amount in the list equals the sum of every `credit` amount in the "
    "list), `post(legs)` must apply EVERY leg to its account's balance and return normally. If "
    "the legs are UNBALANCED (the sum of the `debit` amounts does not equal the sum of the "
    "`credit` amounts), `post(legs)` must instead raise `ValueError` and leave EVERY account's "
    "balance COMPLETELY UNCHANGED -- no partial posting of any leg from an unbalanced call."
)

DOUBLE_ENTRY_LEDGER_TASK = RealSystemTask(
    name="double-entry-ledger",
    cls="ledger",
    sentence=_LEDGER_SENTENCE,
    oracle_kind="double_entry",
    oracle_spec={
        "module": "ledger",
        "entity": "Ledger",
        "spec": {
            "accounts": ["cash", "revenue", "expense"],
            "initial": {"cash": 0, "revenue": 0, "expense": 0},
            "post_method": "post",
            # Unbalanced entry FIRST (debit cash 5000, credit revenue 4000 -- off by 1000 cents,
            # must be rejected), then three balanced entries: a $100 cash sale, a $30 cash
            # expense payment, and a $20 cash sale, landing on cash=9000, revenue=-12000,
            # expense=3000 (debit-positive/credit-negative sign convention, so the ledger-wide
            # sum of every accepted entry's legs -- and hence every account's final balance --
            # always nets to what its own legs predict).
            "drive": [
                {"legs": [{"account": "cash", "debit": 5000},
                          {"account": "revenue", "credit": 4000}],
                 "expect": "reject"},
                {"legs": [{"account": "cash", "debit": 10000},
                          {"account": "revenue", "credit": 10000}],
                 "expect": "accept"},
                {"legs": [{"account": "expense", "debit": 3000},
                          {"account": "cash", "credit": 3000}],
                 "expect": "accept"},
                {"legs": [{"account": "cash", "debit": 2000},
                          {"account": "revenue", "credit": 2000}],
                 "expect": "accept"},
            ],
            "expect_final": {"cash": 9000, "revenue": -12000, "expense": 3000},
        },
    },
)

REAL_SYSTEMS_TASKS.append(DOUBLE_ENTRY_LEDGER_TASK)
# #EXT-060-REQ-17 End


# #EXT-060-REQ-18 Start
# TASK-13: a SECOND LIFECYCLE-shaped task, in a NEW SaaS-billing vertical (a subscription, not an
# order) -- graded by the ALREADY-LANDED "state_machine" oracle_kind dispatch REQ-13 lands (no new
# oracle code: reuses `_grade_state_machine` -> `harness.state_machine_oracle.grade_state_machine`
# verbatim). `cancel()` is deliberately legal from TWO source states (`active` AND `past_due` --
# encoded as two separate `"from_state:action"` transitions table entries targeting the same
# `canceled` state), and the driven script exercises TWO distinct illegal transitions (cancelling a
# subscription that never activated, and expiring one that is already canceled) so a build that
# guards only ONE of `cancel()`'s two legal source states, or that lets `expire()` fire from any
# state, is independently caught.
_SUBSCRIPTION_LIFECYCLE_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "subscription.py, using only the standard library, defining exactly one public class named "
    "`Subscription` modeling a SaaS billing subscription lifecycle state machine. "
    "`Subscription()` (no constructor arguments) creates a new subscription whose initial state "
    "is the string `\"trialing\"`. The class exposes a real Python `@property` named `state` that "
    "returns the subscription's current state as one of the strings `\"trialing\"`, `\"active\"`, "
    "`\"past_due\"`, `\"canceled\"`, or `\"expired\"`. It defines exactly five zero-argument "
    "action methods: `activate()` moves the subscription from `\"trialing\"` to `\"active\"` (the "
    "trial converts to a paid subscription); `payment_failed()` moves it from `\"active\"` to "
    "`\"past_due\"` (a billing charge failed); `recover()` moves it from `\"past_due\"` back to "
    "`\"active\"` (a retried charge succeeded); `cancel()` moves it to `\"canceled\"`, and is legal "
    "from EITHER `\"active\"` OR `\"past_due\"` (either state may be cancelled directly); "
    "`lapse()` moves it from `\"trialing\"` to `\"expired\"` (the trial period ended without ever "
    "being activated). Each of these five methods is legal ONLY from the exact source state(s) "
    "named above; calling any of them from any OTHER current state (for example calling "
    "`cancel()` on a subscription that is still `\"trialing\"` and has never been activated or "
    "paid for, or calling `lapse()` on a subscription that has already been `\"canceled\"`) must "
    "instead raise `ValueError` and must leave the subscription's `state` COMPLETELY UNCHANGED -- "
    "no partial mutation before the raise."
)

SUBSCRIPTION_LIFECYCLE_TASK = RealSystemTask(
    name="subscription-lifecycle-state-machine",
    cls="subscription",
    sentence=_SUBSCRIPTION_LIFECYCLE_SENTENCE,
    oracle_kind="state_machine",
    oracle_spec={
        "module": "subscription",
        "entity": "Subscription",
        "spec": {
            "states": ["trialing", "active", "past_due", "canceled", "expired"],
            "initial": "trialing",
            "transitions": {
                "trialing:activate": "active",
                "active:payment_failed": "past_due",
                "past_due:recover": "active",
                "active:cancel": "canceled",
                "past_due:cancel": "canceled",
                "trialing:lapse": "expired",
            },
            # Illegal cancel-while-still-trialing FIRST (must be rejected), then the full legal
            # billing path activate -> payment_failed -> recover -> cancel (exercising BOTH of
            # cancel()'s two legal source states is NOT possible in one linear script, but landing
            # on "active" then failing then recovering then cancelling from "active" proves the
            # "active" leg; REQ-18's oracle_spec deliberately keeps the script linear -- a second
            # illegal lapse-after-cancel closes the loop), then an illegal lapse-from-canceled.
            "drive": [
                {"action": "cancel", "expect": "reject"},
                {"action": "activate", "expect": "accept"},
                {"action": "payment_failed", "expect": "accept"},
                {"action": "recover", "expect": "accept"},
                {"action": "cancel", "expect": "accept"},
                {"action": "lapse", "expect": "reject"},
            ],
            "expect_final": "canceled",
        },
    },
)

REAL_SYSTEMS_TASKS.append(SUBSCRIPTION_LIFECYCLE_TASK)
# #EXT-060-REQ-18 End


# #EXT-060-REQ-19 Start
# TASK-14: a SECOND CONSERVATION-shaped task, in a fintech-wallet vertical (not inventory) -- graded
# by the ALREADY-LANDED "conservation" oracle_kind dispatch REQ-15 lands (no new oracle code: reuses
# `_grade_conservation` -> `harness.conservation_oracle.grade_conservation` verbatim). A plain wallet
# has only ONE naturally-conserved reader (`balance_cents`), but `conservation_oracle.validate_spec`
# REQUIRES every accepted op's `deltas` to sum to zero across ALL declared quantities (the structural
# encoding of the conservation law -- see `harness/conservation_oracle.py`'s module docstring) --
# so, mirroring the same bookkeeping-mirror-pair trick REQ-16's `INVENTORY_ADD_BACKORDER_MODIFY`
# already uses (`backordered`/`backorder_credit`), this task pins a second reader, an internal
# `ledger_cents` bookkeeping counter that always moves opposite `balance_cents` cent-for-cent, so
# the conservation law is checkable structurally while still proving `balance_cents` itself is
# genuinely never allowed to go negative.
_WALLET_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named wallet.py, "
    "using only the standard library, defining exactly one public class named `Wallet` modeling a "
    "fintech wallet balance with credit/debit operations that never allow an overdraw. "
    "`Wallet(initial_balance_cents)` (exactly one positional constructor argument, a non-negative "
    "integer number of cents) creates a wallet whose `balance_cents` starts at "
    "`initial_balance_cents` and whose internal `ledger_cents` bookkeeping counter starts at `0`. "
    "It exposes two zero-argument reader methods, `balance_cents()` and `ledger_cents()`, each "
    "returning the current integer value of that quantity. It defines two methods that each take "
    "one positional integer argument, `cents`: `credit(cents)` deposits `cents` into the wallet "
    "(increasing `balance_cents` by `cents` and decreasing the internal `ledger_cents` counter by "
    "`cents`) -- `credit(cents)` always succeeds for any nonnegative `cents` and never raises; "
    "`debit(cents)` withdraws `cents` from the wallet (decreasing `balance_cents` by `cents` and "
    "increasing the internal `ledger_cents` counter by `cents`) -- but if `cents` is GREATER than "
    "the CURRENT `balance_cents` (an overdraw), it must instead raise `ValueError` and leave BOTH "
    "`balance_cents` and `ledger_cents` COMPLETELY UNCHANGED; `balance_cents` must never go "
    "negative. The sum of `balance_cents` plus `ledger_cents` must never change across any "
    "successful call -- cents are only ever moved between the wallet's balance and its internal "
    "ledger counter, never created or destroyed."
)

WALLET_NO_OVERDRAW_TASK = RealSystemTask(
    name="wallet-no-overdraw",
    cls="wallet",
    sentence=_WALLET_SENTENCE,
    oracle_kind="conservation",
    oracle_spec={
        "module": "wallet",
        "entity": "Wallet",
        "spec": {
            "quantities": ["balance_cents", "ledger_cents"],
            "initial": {"balance_cents": 5000, "ledger_cents": 0},
            "construct_args": [5000],
            # Illegal overdraw FIRST (debit 8000 of 5000 available -- must be rejected), then a
            # legal credit (2000) and a legal debit (3000), then a SECOND illegal overdraw
            # mid-sequence (debit 5000 of the remaining 4000) -- proving the oversell guard holds
            # not just at the initial balance but after legal ops have moved it too.
            "drive": [
                {"action": "debit", "args": [8000], "expect": "reject"},
                {"action": "credit", "args": [2000], "expect": "accept",
                 "deltas": {"balance_cents": 2000, "ledger_cents": -2000}},
                {"action": "debit", "args": [3000], "expect": "accept",
                 "deltas": {"balance_cents": -3000, "ledger_cents": 3000}},
                {"action": "debit", "args": [5000], "expect": "reject"},
            ],
            "expect_final": {"balance_cents": 4000, "ledger_cents": 1000},
        },
    },
)

REAL_SYSTEMS_TASKS.append(WALLET_NO_OVERDRAW_TASK)
# #EXT-060-REQ-19 End


# #EXT-060-REQ-20 Start
# TASK-15: a SECOND LIFECYCLE-shaped task, in a NEW support/helpdesk vertical (not order/subscription)
# -- graded by the ALREADY-LANDED "state_machine" oracle_kind dispatch REQ-13 lands (no new oracle
# code: reuses `_grade_state_machine` -> `harness.state_machine_oracle.grade_state_machine`
# verbatim). The driven script exercises TWO distinct illegal transitions (resolving a ticket that
# was never assigned, and reopening a ticket that was never closed) so a build that guards only ONE
# of those, or that lets any action fire from any state, is independently caught. The trial-lapse
# naming lesson from REQ-18 applies here too: no leaf-fingerprinting tokens (queue/cache/ttl/expire/
# stack/ring/buffer/memoize) appear anywhere in this sentence -- confirmed via `leaf_for_spec`.
_TICKET_WORKFLOW_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named ticket.py, "
    "using only the standard library, defining exactly one public class named `Ticket` modeling a "
    "support/helpdesk ticket workflow state machine. `Ticket()` (no constructor arguments) creates "
    "a new ticket whose initial state is the string `\"open\"`. The class exposes a real Python "
    "`@property` named `state` that returns the ticket's current state as one of the strings "
    "`\"open\"`, `\"assigned\"`, `\"pending_customer\"`, `\"resolved\"`, or `\"closed\"`. It defines "
    "exactly six zero-argument action methods: `assign()` moves the ticket from `\"open\"` to "
    "`\"assigned\"` (a support agent takes ownership); `await_customer()` moves it from "
    "`\"assigned\"` to `\"pending_customer\"` (the agent is waiting on more information from the "
    "customer); `respond()` moves it from `\"pending_customer\"` back to `\"assigned\"` (the "
    "customer has replied); `resolve()` moves it from `\"assigned\"` to `\"resolved\"` (the agent "
    "has fixed the issue); `close()` moves it from `\"resolved\"` to `\"closed\"`; `reopen()` moves "
    "it from `\"closed\"` back to `\"open\"` (the ticket is reopened after being closed). Each of "
    "these six methods is legal ONLY from the exact source state named above; calling any of them "
    "from any OTHER current state (for example calling `resolve()` on a ticket that is still "
    "`\"open\"` and has never been assigned to anyone, or calling `reopen()` on a ticket that is "
    "`\"assigned\"` and was never closed) must instead raise `ValueError` and must leave the "
    "ticket's `state` COMPLETELY UNCHANGED -- no partial mutation before the raise."
)

TICKET_WORKFLOW_TASK = RealSystemTask(
    name="support-ticket-workflow-state-machine",
    cls="ticket",
    sentence=_TICKET_WORKFLOW_SENTENCE,
    oracle_kind="state_machine",
    oracle_spec={
        "module": "ticket",
        "entity": "Ticket",
        "spec": {
            "states": ["open", "assigned", "pending_customer", "resolved", "closed"],
            "initial": "open",
            "transitions": {
                "open:assign": "assigned",
                "assigned:await_customer": "pending_customer",
                "pending_customer:respond": "assigned",
                "assigned:resolve": "resolved",
                "resolved:close": "closed",
                "closed:reopen": "open",
            },
            # Illegal resolve-while-still-unassigned FIRST (must be rejected), then the legal
            # assign, then an illegal reopen from "assigned" (never closed -- must ALSO be
            # rejected, a SECOND distinct illegal transition), then the full legal support path
            # (await_customer -> respond -> resolve -> close -> reopen) back to "open".
            "drive": [
                {"action": "resolve", "expect": "reject"},
                {"action": "assign", "expect": "accept"},
                {"action": "reopen", "expect": "reject"},
                {"action": "await_customer", "expect": "accept"},
                {"action": "respond", "expect": "accept"},
                {"action": "resolve", "expect": "accept"},
                {"action": "close", "expect": "accept"},
                {"action": "reopen", "expect": "accept"},
            ],
            "expect_final": "open",
        },
    },
)

REAL_SYSTEMS_TASKS.append(TICKET_WORKFLOW_TASK)
# #EXT-060-REQ-20 End


# #EXT-060-REQ-21 Start
# TASK-16: a THIRD CONSERVATION-shaped task, in an events/venue-booking vertical (not inventory or
# wallet) -- graded by the ALREADY-LANDED "conservation" oracle_kind dispatch REQ-15 lands (no new
# oracle code: reuses `_grade_conservation` -> `harness.conservation_oracle.grade_conservation`
# verbatim). Mirrors `INVENTORY_TASK`'s two-quantity (available/reserved) shape exactly, applied to
# seat capacity rather than SKU stock, with TWO distinct illegal overbooking attempts (at the very
# start, and again mid-sequence after a partial release) so a guard that only checks the initial
# capacity, or that stops enforcing after any legal operation has occurred, is independently caught.
_SEAT_BOOKING_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named booking.py, "
    "using only the standard library, defining exactly one public class named `SeatBooking` "
    "modeling seat reservations for a single event or venue with a fixed seating capacity. "
    "`SeatBooking(total_seats)` (exactly one positional constructor argument, a non-negative "
    "integer) creates seat tracking for that event whose `available_seats` start at `total_seats` "
    "and whose `reserved_seats` start at `0`. It exposes two zero-argument reader methods, "
    "`available_seats()` and `reserved_seats()`, each returning the current integer value of that "
    "quantity. It defines two methods that each take one positional integer argument, `n`: "
    "`reserve(n)` moves `n` seats from `available_seats` to `reserved_seats` (decreasing "
    "`available_seats` by `n` and increasing `reserved_seats` by `n`) -- but if `n` is GREATER than "
    "the CURRENT `available_seats` (an overbooking), it must instead raise `ValueError` and leave "
    "BOTH `available_seats` and `reserved_seats` COMPLETELY UNCHANGED; `release(n)` moves `n` seats "
    "back from `reserved_seats` to `available_seats` (increasing `available_seats` by `n` and "
    "decreasing `reserved_seats` by `n`). The total of `available_seats` plus `reserved_seats` must "
    "never change across any successful call -- seats are only ever moved between the two, never "
    "created or destroyed."
)

SEAT_BOOKING_TASK = RealSystemTask(
    name="seat-booking-no-double-book",
    cls="booking",
    sentence=_SEAT_BOOKING_SENTENCE,
    oracle_kind="conservation",
    oracle_spec={
        "module": "booking",
        "entity": "SeatBooking",
        "spec": {
            "quantities": ["available_seats", "reserved_seats"],
            "initial": {"available_seats": 100, "reserved_seats": 0},
            "construct_args": [100],
            # Illegal overbooking at the very START (150 of 100 -- must be rejected), then two
            # legal ops (reserve 60, release 20), then a SECOND illegal overbooking MID-sequence
            # (reserving 70 when only 60 is available after the partial release -- proving the
            # guard holds after legal ops have moved the balance too, not just at construction),
            # then a final legal reserve landing on a concrete expect_final.
            "drive": [
                {"action": "reserve", "args": [150], "expect": "reject"},
                {"action": "reserve", "args": [60], "expect": "accept",
                 "deltas": {"available_seats": -60, "reserved_seats": 60}},
                {"action": "release", "args": [20], "expect": "accept",
                 "deltas": {"available_seats": 20, "reserved_seats": -20}},
                {"action": "reserve", "args": [70], "expect": "reject"},
                {"action": "reserve", "args": [50], "expect": "accept",
                 "deltas": {"available_seats": -50, "reserved_seats": 50}},
            ],
            "expect_final": {"available_seats": 10, "reserved_seats": 90},
        },
    },
)

REAL_SYSTEMS_TASKS.append(SEAT_BOOKING_TASK)
# #EXT-060-REQ-21 End


# #EXT-060-REQ-22 Start
# TASK-17: a SECOND FINTECH-LEDGER-shaped task, in an accounts-receivable/invoicing vertical (not
# the general cash/revenue/expense journal REQ-17 already covers) -- graded by the ALREADY-LANDED
# "double_entry" oracle_kind dispatch REQ-17 lands (no new oracle code: reuses
# `_grade_double_entry` -> `harness.double_entry_oracle.grade_double_entry` verbatim). The driven
# script issues two customer invoices (debit accounts_receivable / credit revenue) and receives one
# payment (debit cash / credit accounts_receivable) alongside one unbalanced-posting rejection --
# `expect_final` is hand-derived from the debit-positive/credit-negative shadow math (verified via
# `harness.double_entry_oracle.validate_spec` and an end-to-end `grade_double_entry` dry run against
# both a correct and a broken fixture before this task was added to the roster).
_INVOICE_AR_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named invoicing.py, "
    "using only the standard library, defining exactly one public class named `Invoicing` modeling "
    "an accounts-receivable double-entry ledger over exactly three named accounts: "
    "`accounts_receivable`, `revenue`, and `cash`. `Invoicing()` (no constructor arguments) creates "
    "a ledger where all three accounts start at a balance of `0` (an exact integer number of "
    "cents). It exposes three zero-argument reader methods, `accounts_receivable()`, `revenue()`, "
    "and `cash()`, each returning that account's CURRENT integer balance in cents. It defines "
    "exactly one method, `post(legs)`, taking one positional argument -- a list of leg dicts, each "
    "either `{\"account\": <name>, \"debit\": <cents>}` or `{\"account\": <name>, \"credit\": "
    "<cents>}`, where `<name>` is one of `accounts_receivable`/`revenue`/`cash` and `<cents>` is a "
    "positive integer. Posting a leg to an account with `debit` ADDS that many cents to the "
    "account's balance; posting a leg with `credit` SUBTRACTS that many cents from the account's "
    "balance. Issuing a customer invoice is recorded by posting legs that DEBIT "
    "`accounts_receivable` and CREDIT `revenue` for the same amount; later receiving payment "
    "against that invoice is recorded by posting legs that DEBIT `cash` and CREDIT "
    "`accounts_receivable` for the same amount. If the legs in one call to `post(legs)` are "
    "BALANCED (the sum of every `debit` amount in the list equals the sum of every `credit` amount "
    "in the list), `post(legs)` must apply EVERY leg to its account's balance and return normally. "
    "If the legs are UNBALANCED (the sum of the `debit` amounts does not equal the sum of the "
    "`credit` amounts), `post(legs)` must instead raise `ValueError` and leave EVERY account's "
    "balance COMPLETELY UNCHANGED -- no partial posting of any leg from an unbalanced call."
)

INVOICE_AR_TASK = RealSystemTask(
    name="invoice-accounts-receivable-ledger",
    cls="invoice",
    sentence=_INVOICE_AR_SENTENCE,
    oracle_kind="double_entry",
    oracle_spec={
        "module": "invoicing",
        "entity": "Invoicing",
        "spec": {
            "accounts": ["accounts_receivable", "revenue", "cash"],
            "initial": {"accounts_receivable": 0, "revenue": 0, "cash": 0},
            "post_method": "post",
            # Unbalanced entry FIRST (debit accounts_receivable 10000, credit revenue 9000 -- off
            # by 1000 cents, must be rejected), then two balanced invoice postings ($500.00 and
            # $300.00, each debiting accounts_receivable / crediting revenue), then one balanced
            # payment posting ($500.00, debiting cash / crediting accounts_receivable) -- landing
            # on accounts_receivable=30000, revenue=-80000, cash=50000 (debit-positive/
            # credit-negative sign convention, matching DOUBLE_ENTRY_LEDGER_TASK's own convention).
            "drive": [
                {"legs": [{"account": "accounts_receivable", "debit": 10000},
                          {"account": "revenue", "credit": 9000}],
                 "expect": "reject"},
                {"legs": [{"account": "accounts_receivable", "debit": 50000},
                          {"account": "revenue", "credit": 50000}],
                 "expect": "accept"},
                {"legs": [{"account": "accounts_receivable", "debit": 30000},
                          {"account": "revenue", "credit": 30000}],
                 "expect": "accept"},
                {"legs": [{"account": "cash", "debit": 50000},
                          {"account": "accounts_receivable", "credit": 50000}],
                 "expect": "accept"},
            ],
            "expect_final": {"accounts_receivable": 30000, "revenue": -80000, "cash": 50000},
        },
    },
)

REAL_SYSTEMS_TASKS.append(INVOICE_AR_TASK)
# #EXT-060-REQ-22 End


# #EXT-060-REQ-24 Start
# TASK-19: a FOURTH LIFECYCLE-shaped task, in an SLA-tiered helpdesk vertical -- DISTINCT from
# `TICKET_WORKFLOW_TASK` (REQ-20's plain support ticket): the defining behavior here is SLA-tier
# ESCALATION (a ticket that breaches its response window is bumped to a higher-priority tier via
# `escalate()`, legal ONLY from `"triaged"`), not just an assign/respond/resolve/close loop.
# Graded by the ALREADY-LANDED "state_machine" oracle_kind dispatch REQ-13 lands (no new oracle
# code: reuses `_grade_state_machine` -> `harness.state_machine_oracle.grade_state_machine`
# verbatim). The driven script exercises TWO distinct illegal transitions (escalating a
# brand-new, never-triaged ticket, and closing a ticket that has never been resolved) so a build
# that guards only ONE of those, or that lets any action fire from any state, is independently
# caught.
_HELPDESK_SLA_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named helpdesk.py, "
    "using only the standard library, defining exactly one public class named `HelpdeskTicket` "
    "modeling an SLA-tiered helpdesk support ticket -- distinct from a plain support ticket in "
    "that a ticket is explicitly ESCALATED to a higher SLA tier when initial triage cannot "
    "resolve it within that tier's response window. `HelpdeskTicket()` (no constructor "
    "arguments) creates a new ticket whose initial state is the string `\"new\"`. The class "
    "exposes a real Python `@property` named `state` that returns the ticket's current state as "
    "one of the strings `\"new\"`, `\"triaged\"`, `\"escalated\"`, `\"waiting_customer\"`, "
    "`\"resolved\"`, or `\"closed\"`. It defines exactly seven zero-argument action methods: "
    "`triage()` moves the ticket from `\"new\"` to `\"triaged\"` (an agent has classified the "
    "ticket and assigned its SLA tier); `escalate()` moves the ticket from `\"triaged\"` to "
    "`\"escalated\"` (the ticket has breached its SLA response window and is bumped to a "
    "higher-priority tier) -- `escalate()` is legal ONLY from `\"triaged\"`, never from `\"new\"` "
    "or any other state; `wait_on_customer()` moves the ticket from EITHER `\"triaged\"` OR "
    "`\"escalated\"` to `\"waiting_customer\"` (the agent is blocked waiting on more information "
    "from the customer); `resume()` moves the ticket from `\"waiting_customer\"` back to "
    "`\"triaged\"` (the customer has replied and normal-tier handling resumes); `resolve()` "
    "moves the ticket from EITHER `\"triaged\"` OR `\"escalated\"` to `\"resolved\"` (the agent "
    "has fixed the issue, at whichever SLA tier it was resolved); `close()` moves the ticket "
    "from `\"resolved\"` to `\"closed\"`; `reopen()` moves the ticket from `\"closed\"` back to "
    "`\"new\"` (a closed ticket is reopened and must go back through triage and SLA-tier "
    "assignment from scratch). Each of these seven methods is legal ONLY from the exact source "
    "state(s) named above; calling any of them from any OTHER current state (for example calling "
    "`escalate()` on a brand-new ticket that has never been triaged, or calling `close()` on a "
    "ticket that has never been resolved) must instead raise `ValueError` and must leave the "
    "ticket's `state` COMPLETELY UNCHANGED -- no partial mutation before the raise."
)

HELPDESK_SLA_TASK = RealSystemTask(
    name="helpdesk-ticket-sla-state-machine",
    cls="helpdesk",
    sentence=_HELPDESK_SLA_SENTENCE,
    oracle_kind="state_machine",
    oracle_spec={
        "module": "helpdesk",
        "entity": "HelpdeskTicket",
        "spec": {
            "states": ["new", "triaged", "escalated", "waiting_customer", "resolved", "closed"],
            "initial": "new",
            "transitions": {
                "new:triage": "triaged",
                "triaged:escalate": "escalated",
                "triaged:resolve": "resolved",
                "escalated:resolve": "resolved",
                "triaged:wait_on_customer": "waiting_customer",
                "escalated:wait_on_customer": "waiting_customer",
                "waiting_customer:resume": "triaged",
                "resolved:close": "closed",
                "closed:reopen": "new",
            },
            # Illegal escalate-from-"new" FIRST (must be rejected -- escalate() requires a prior
            # triage()), then the legal triage, then an illegal close-from-"triaged" (never
            # resolved -- must ALSO be rejected, a SECOND distinct illegal transition), then the
            # full legal SLA-escalation path (triage -> escalate -> wait_on_customer -> resume ->
            # resolve -> close -> reopen) back to "new".
            "drive": [
                {"action": "escalate", "expect": "reject"},
                {"action": "triage", "expect": "accept"},
                {"action": "close", "expect": "reject"},
                {"action": "escalate", "expect": "accept"},
                {"action": "wait_on_customer", "expect": "accept"},
                {"action": "resume", "expect": "accept"},
                {"action": "resolve", "expect": "accept"},
                {"action": "close", "expect": "accept"},
                {"action": "reopen", "expect": "accept"},
            ],
            "expect_final": "new",
        },
    },
)

REAL_SYSTEMS_TASKS.append(HELPDESK_SLA_TASK)
# #EXT-060-REQ-24 End


# #EXT-060-REQ-25 Start
# TASK-20: a SECOND cli-exact CREATE task (the first since REQ-4's INI-query CLI), in an
# elections/voting vertical -- graded by the ALREADY-LANDED cli-exact oracle (no new oracle code:
# reuses `_grade_cli_exact` -> `harness.system_suite`'s `exact_stdout` check variant, the same
# sandboxed/scrubbed-env subprocess convention every other black-box check in this codebase
# already goes through). Every counting/printing rule (round-tally format, majority threshold,
# elimination order, deterministic alphabetical tie-free ordering) is pinned in the sentence
# itself so the oracle's expected stdout is fully DERIVED from that same visible contract -- no
# hidden key, no reference implementation the model could not see. The seeded ballot fixture is
# deliberately built so the FIRST-round plurality leader (`A`, 10 of 21 first-choice votes) LOSES
# after `C` is eliminated and its second-choice votes transfer to `B` (proving real
# instant-runoff transfer logic, not a plurality/most-first-choice-votes shortcut, which would
# wrongly declare `A` the winner).
_IRV_TALLY_SENTENCE = (
    "Write a command-line program in a file named main.py that reads ranked-choice ballot data "
    "from standard input and prints the winner of an instant-runoff (ranked-choice) election, "
    "computed by successive elimination rounds. Each line of standard input is exactly one "
    "voter's ballot: a comma-separated list of candidate names in ranked order, most-preferred "
    "candidate first (for example `A,B,C` ranks `A` first, `B` second, `C` third); a ballot need "
    "not rank every candidate. The program takes no command-line arguments. In EACH round: "
    "tally, for every candidate still in the race, the number of ballots whose HIGHEST-ranked "
    "remaining candidate (skipping any candidate already eliminated in an earlier round) is that "
    "candidate; a ballot none of whose ranked candidates remain in the race any longer casts no "
    "vote in that round (or in any later round). Print one line for that round of the exact form "
    "`Round <N>: <name1>=<count1>, <name2>=<count2>, ...` -- every candidate still in the race "
    "that round, listed in ALPHABETICAL order by name, separated by `\", \"`, followed by a "
    "single newline. If any candidate's count that round is STRICTLY MORE than half of the sum "
    "of every candidate's count that same round (a strict majority of the ballots still active "
    "that round), that candidate has won: immediately print one final line of the exact form "
    "`Winner: <name>` followed by a single newline, and print nothing further. Otherwise, no "
    "candidate has a strict majority yet: eliminate the single candidate with the STRICTLY "
    "FEWEST votes that round (the graded input never produces a tie for fewest), print one line "
    "of the exact form `Eliminated: <name>` followed by a single newline, and proceed to tally "
    "the next round with that candidate removed from the race."
)

# 21 ballots: 10 rank A first (then B), 6 rank B first (then C), 5 rank C first (then B). Round 1
# plurality leader is A (10 votes) -- but A is NOT a majority of 21 (needs > 10.5), so no one
# wins round 1. C is eliminated (fewest, 5 votes); C's ballots all transfer to their second
# choice, B. Round 2: A=10, B=11 (6 original + 5 transferred) -- B now has a strict majority
# (11 > 10.5) and wins, even though A led round 1's plurality.
_IRV_TALLY_STDIN = ("A,B\n" * 10) + ("B,C\n" * 6) + ("C,B\n" * 5)
_IRV_TALLY_EXPECTED_STDOUT = (
    "Round 1: A=10, B=6, C=5\n"
    "Eliminated: C\n"
    "Round 2: A=10, B=11\n"
    "Winner: B\n"
)

IRV_TALLY_TASK = RealSystemTask(
    name="ranked-choice-irv-tally-cli",
    cls="elections",
    sentence=_IRV_TALLY_SENTENCE,
    oracle_kind="cli-exact",
    oracle_spec={
        "argv": [],
        "stdin": _IRV_TALLY_STDIN,
        "expected_stdout": _IRV_TALLY_EXPECTED_STDOUT,
    },
)

REAL_SYSTEMS_TASKS.append(IRV_TALLY_TASK)
# #EXT-060-REQ-25 End


# #EXT-060-REQ-26 Start
# TASK-21: a THIRD "import" oracle_kind CREATE task (after REQ-3's retry-backoff and REQ-5's
# memoize libraries), in a payroll/tax vertical -- graded by the ALREADY-LANDED "import"
# oracle_kind dispatch REQ-3 lands (no new oracle code: reuses `_grade_import` ->
# `harness.import_driver.drive_import` verbatim). NO jurisdiction/bracket table is hardcoded
# anywhere in the built module -- `brackets` is always supplied by the caller, exactly mirroring
# the caller-supplied-config discipline `RETRY_BACKOFF_LIB_TASK` already established for its own
# decorator parameters. The floor-division contribution rule (`(portion_cents * rate_percent) //
# 100`) is pinned explicitly in the sentence so there is no floating-point rounding ambiguity --
# every checked value below was hand-verified against that exact rule before being added to the
# roster (see the module's own scratch verification in the task's commit).
_TAX_WITHHOLDING_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "withholding.py, using only the standard library, defining exactly one public function "
    "named `compute_withholding_cents` with the signature `compute_withholding_cents"
    "(income_cents, brackets)`. `income_cents` is a non-negative integer, the employee's gross "
    "pay for the period in an exact integer number of cents. `brackets` is a list of "
    "two-element `[upper_bound_cents, rate_percent]` pairs, one per progressive tax bracket, "
    "given in ASCENDING order by `upper_bound_cents`; each `rate_percent` is a positive integer "
    "percentage rate that applies to the portion of `income_cents` that falls within that "
    "bracket. The bracket boundaries are CUMULATIVE: the first bracket covers income from `0` "
    "up to and including its own `upper_bound_cents`; each later bracket covers income ABOVE the "
    "previous bracket's `upper_bound_cents` up to and including its own `upper_bound_cents`. The "
    "LAST entry in `brackets` always has `upper_bound_cents` set to Python's `None`, meaning it "
    "has no ceiling and covers all remaining income above the previous bracket's "
    "`upper_bound_cents`. There is no hardcoded jurisdiction or bracket table anywhere in the "
    "module -- `brackets` is always supplied by the caller. For each bracket, compute the "
    "portion of `income_cents` that falls into that bracket's range (`0` when `income_cents` "
    "does not reach that bracket's lower edge); that bracket's contribution to the withholding "
    "is `(portion_cents * rate_percent) // 100`, using INTEGER FLOOR DIVISION (never "
    "floating-point arithmetic or rounding). `compute_withholding_cents` returns the SUM of "
    "every bracket's contribution as a single integer number of cents."
)

# [[upper_bound_cents, rate_percent], ...]: $0-$1,000.00 @ 10%, $1,000.00-$4,000.00 @ 20%,
# above $4,000.00 (open-ended, `None`) @ 30%.
_TAX_WITHHOLDING_BRACKETS = [[100000, 10], [400000, 20], [None, 30]]

TAX_WITHHOLDING_TASK = RealSystemTask(
    name="progressive-tax-withholding-lib",
    cls="payroll",
    sentence=_TAX_WITHHOLDING_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "withholding",
        "api_calls": [
            {"id": "zero", "target": "compute_withholding_cents",
             "args": [0, _TAX_WITHHOLDING_BRACKETS], "kwargs": {}},
            {"id": "boundary", "target": "compute_withholding_cents",
             "args": [100000, _TAX_WITHHOLDING_BRACKETS], "kwargs": {}},
            {"id": "mid", "target": "compute_withholding_cents",
             "args": [225037, _TAX_WITHHOLDING_BRACKETS], "kwargs": {}},
            {"id": "top", "target": "compute_withholding_cents",
             "args": [500000, _TAX_WITHHOLDING_BRACKETS], "kwargs": {}},
        ],
        "checks": [
            # zero income -> zero withholding.
            {"kind": "returns_equals", "call_id": "zero", "expected": 0},
            # income exactly AT the first bracket's boundary ($1,000.00): the whole $1,000.00 is
            # taxed at 10% -> 10000 cents. A build with an off-by-one boundary (exclusive instead
            # of inclusive) shortchanges this by 1 cent.
            {"kind": "returns_equals", "call_id": "boundary", "expected": 10000},
            # mid-second-bracket income ($2,250.37): 10000 (bracket 1) + (125037 * 20 // 100 =
            # 25007) (bracket 2 portion) = 35007 cents.
            {"kind": "returns_equals", "call_id": "mid", "expected": 35007},
            # income above the top bracket's ceiling ($5,000.00): 10000 (bracket 1) + 60000
            # (bracket 2, full $3,000.00 span at 20%) + 30000 (bracket 3, $1,000.00 overflow at
            # 30%) = 100000 cents.
            {"kind": "returns_equals", "call_id": "top", "expected": 100000},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(TAX_WITHHOLDING_TASK)
# #EXT-060-REQ-26 End


# #EXT-060-REQ-27 Start
# TASK-22: a FOURTH "import" oracle_kind CREATE task, in a legal/court-filing vertical -- graded
# by the ALREADY-LANDED "import" oracle_kind dispatch REQ-3 lands (no new oracle code: reuses
# `_grade_import` -> `harness.import_driver.drive_import` verbatim). Fully deterministic: every
# input (trigger date, day count, counting rule, the explicit holiday list) is passed in by the
# caller -- nothing depends on "today", so no clock/injected-time seam is needed. Every checked
# date below was independently hand-verified with `datetime.date` arithmetic before being added
# to the roster (see the task's commit for the verification script).
_COURT_DEADLINE_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named deadline.py, "
    "using only the standard library (the `datetime` module is allowed), defining exactly one "
    "public function named `compute_deadline` with the signature `compute_deadline(trigger_date, "
    "day_count, counting_rule, holidays)`. `trigger_date` is a string in ISO format "
    "`\"YYYY-MM-DD\"`; `day_count` is a non-negative integer; `counting_rule` is exactly the "
    "string `\"calendar\"` or the string `\"court\"`; `holidays` is a list of zero or more "
    "ISO-format `\"YYYY-MM-DD\"` date strings, each an explicit non-court holiday -- there is no "
    "built-in holiday calendar anywhere in the module, ONLY the dates the caller passes in "
    "`holidays` are treated as holidays. Saturday and Sunday are ALWAYS non-court weekend days "
    "(a fixed rule, never configurable). `compute_deadline` returns the computed filing deadline "
    "as an ISO `\"YYYY-MM-DD\"` string, computed as follows. When `counting_rule` is "
    "`\"calendar\"`: the RAW landing day is `trigger_date` plus exactly `day_count` calendar "
    "days (every day counts, weekends and holidays included). When `counting_rule` is "
    "`\"court\"`: starting from the day immediately AFTER `trigger_date`, walk forward one "
    "calendar day at a time and count a day toward `day_count` ONLY when that day is NEITHER a "
    "Saturday/Sunday NOR listed in `holidays`; the RAW landing day is the day on which the "
    "`day_count`-th such counted day is reached. In BOTH cases, after computing the RAW landing "
    "day, if that RAW landing day is itself a Saturday, a Sunday, or a date listed in "
    "`holidays`, roll it forward one calendar day at a time -- skipping any further Saturday, "
    "Sunday, or `holidays` date the exact same way -- until it lands on a day that is neither a "
    "weekend day nor listed in `holidays`; that final day is the returned deadline."
)

COURT_DEADLINE_TASK = RealSystemTask(
    name="court-deadline-date-math-lib",
    cls="legal",
    sentence=_COURT_DEADLINE_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "deadline",
        "api_calls": [
            # Baseline sanity: 3 calendar days from a Friday lands on a Monday -- no rolling
            # needed, proves plain date arithmetic is correct before any weekend/holiday logic.
            {"id": "baseline", "target": "compute_deadline",
             "args": ["2027-01-01", 3, "calendar", []], "kwargs": {}},
            # Calendar-day landing on a Saturday rolls forward across the whole weekend to the
            # next Monday.
            {"id": "sat_roll", "target": "compute_deadline",
             "args": ["2027-01-01", 1, "calendar", []], "kwargs": {}},
            # Court-day counting skips weekends AND an interior holiday (2027-01-05, a Tuesday)
            # while counting toward day_count.
            {"id": "court_skip", "target": "compute_deadline",
             "args": ["2027-01-01", 3, "court", ["2027-01-05"]], "kwargs": {}},
            # Holiday-adjacent edge: a calendar-rule landing day (2027-01-06, a Wednesday) that
            # is itself listed as a holiday must still roll forward, even though it is not a
            # weekend day.
            {"id": "holiday_landing", "target": "compute_deadline",
             "args": ["2027-01-01", 5, "calendar", ["2027-01-06"]], "kwargs": {}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "baseline", "expected": "2027-01-04"},
            {"kind": "returns_equals", "call_id": "sat_roll", "expected": "2027-01-04"},
            {"kind": "returns_equals", "call_id": "court_skip", "expected": "2027-01-07"},
            {"kind": "returns_equals", "call_id": "holiday_landing", "expected": "2027-01-07"},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(COURT_DEADLINE_TASK)
# #EXT-060-REQ-27 End


# #EXT-060-REQ-28 Start
# TASK-23: the FIRST TIME-DEPENDENT CREATE task -- an account login-attempt lockout/backoff
# policy, in an auth vertical -- graded by the NEW `oracle_kind="clock"` dispatch this
# requirement lands (`_grade_clock` -> `harness.clock_oracle.grade_clock`, no reimplementation of
# the oracle itself). The defining honesty core: the entity's constructor accepts a keyword-named
# zero-argument clock callable (`now_fn`, per `harness.clock_oracle`'s pinned `clock_param`
# contract) and MUST consult only that callable for every time decision -- a build that instead
# calls the real wall clock internally (`time.time()`/`datetime.datetime.now()`) is caught because
# the driven timeline jumps from t=30 to t=650 (a 620-simulated-second leap) in real milliseconds:
# a real-clock-driven build sees no meaningful elapsed time between those two calls and so cannot
# correctly report BOTH "still locked at t=30" and "unlocked again at t=650". The sentence
# deliberately says the lock "clears" (never "expires") and avoids every other
# leaf-fingerprinting token (cache/ttl/queue/stack/ring/buffer/memoize) so this auth-lockout class
# is never confused with the verified `ttl-store` leaf.
_LOCKOUT_BACKOFF_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named lockout.py, "
    "using only the standard library, defining exactly one exception class named `LockedOut` "
    "(a subclass of the built-in `Exception`, taking no required constructor arguments) and "
    "exactly one public class named `LoginAttemptTracker` modeling an account login-attempt "
    "lockout/backoff policy. `LoginAttemptTracker(now_fn)` accepts exactly one argument, the "
    "keyword `now_fn`: a zero-argument callable that returns the current time as an integer "
    "number of epoch seconds. The class must determine EVERY time-based decision by calling "
    "`now_fn()` at the moment it needs to know the current time -- it must never read the real "
    "system clock (`time.time()`, `datetime.datetime.now()`, or any other wall-clock source) "
    "for any purpose. The class exposes exactly one action method, `record_attempt(success)` "
    "(`success` is a bool: `True` for a successful login attempt, `False` for a failed one), "
    "and exactly one zero-argument reader method, `is_locked()`, returning a bool. Track a run "
    "of consecutive failed attempts (a 'failure streak'), counted only while the account is not "
    "locked: the streak starts at the first failed attempt seen, and each further consecutive "
    "failed attempt extends it, UNLESS more than 300 seconds have elapsed (per `now_fn()`) "
    "since the streak's first failure, in which case that failed attempt starts a brand-new "
    "streak of length 1 instead of extending the old one. The moment a THIRD failed attempt "
    "lands in the SAME streak (three consecutive failures, all within 300 seconds of the "
    "streak's first failure), the account becomes locked: record a lock-clear time of "
    "`now_fn() + 600` (600 seconds after that third failure), and `is_locked()` must return "
    "`True` from that call onward. While the account is locked (the current `now_fn()` reading "
    "is still strictly before the recorded lock-clear time), calling `record_attempt(...)` with "
    "EITHER `True` or `False` must immediately raise `LockedOut` and must have no other effect "
    "-- it must not count toward, reset, or otherwise change the failure streak, the lock-clear "
    "time, or anything else. Once `now_fn()` reaches or passes the recorded lock-clear time, "
    "the account is no longer locked: the very next `record_attempt(...)` call is processed "
    "exactly like any other attempt below (not raising `LockedOut`), and `is_locked()` must "
    "return `False` again once that call has been processed (unless that same call itself "
    "immediately re-locks the account). A SUCCESSFUL attempt (`success=True`) processed while "
    "not locked always resets the failure streak completely (no failures currently counted). "
    "`record_attempt` returns `None` on every call that does not raise `LockedOut`."
)

LOCKOUT_BACKOFF_TASK = RealSystemTask(
    name="account-lockout-backoff-lib",
    cls="auth",
    sentence=_LOCKOUT_BACKOFF_SENTENCE,
    oracle_kind="clock",
    oracle_spec={
        "module": "lockout",
        "entity": "LoginAttemptTracker",
        "spec": {
            "clock_param": "now_fn",
            "construct_args": [],
            "construct_kwargs": {},
            # Hand-walked timeline (see the task's commit for the scratch verification script):
            # t=0/10/20 are three consecutive failures within the 300s window -> the third
            # (t=20) triggers a lock clearing at t=20+600=620. t=30 is still inside the lock
            # (30 < 620) -> must raise LockedOut. t=650 is a 620-SIMULATED-second jump from t=30
            # (executed in real milliseconds) that lands AFTER the lock clears (650 >= 620) -> a
            # real-wall-clock-driven build cannot distinguish this from t=30 and fails here.
            "timeline": [
                {"at": 0, "call": "record_attempt", "args": [False], "expect": {"returns": None}},
                {"at": 10, "call": "record_attempt", "args": [False], "expect": {"returns": None}},
                {"at": 20, "call": "record_attempt", "args": [False], "expect": {"returns": None}},
                {"at": 30, "call": "record_attempt", "args": [True],
                 "expect": {"raises": "LockedOut"}},
                {"at": 650, "call": "record_attempt", "args": [True], "expect": {"returns": None}},
            ],
            "expect_final": {"is_locked": False},
        },
    },
)

REAL_SYSTEMS_TASKS.append(LOCKOUT_BACKOFF_TASK)
# #EXT-060-REQ-28 End


# #EXT-060-REQ-29 Start
# TASK-24: the FIRST agent/LLM-infrastructure CREATE task from the atlas's wave-5 agent-infra
# vertical -- an LLM-output parsing library -- graded by the ALREADY-LANDED "import" oracle_kind
# dispatch REQ-3 lands (no new oracle code -- reuses `_grade_import` ->
# `harness.import_driver.drive_import` verbatim). Every expected value below was hand-verified
# against a scratch reference implementation (see the task's commit) before being added to the
# roster.
_OUTPUT_PARSER_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "output_parser.py, using only the standard library, defining exactly three public "
    "functions: `parse_json_block(text)`, `parse_key_values(text)`, and `strip_fences(text)` -- "
    "each extracting structured data out of messy, LLM-style free-text output. "
    "`parse_json_block(text)` searches `text` line by line for a fenced block that OPENS with a "
    "line whose stripped content is EXACTLY three backticks immediately followed by the word "
    "`json` (no space between the backticks and `json`) and CLOSES at the next line whose "
    "stripped content is EXACTLY three backticks and nothing else; every line strictly between "
    "those two fence lines (joined back together with a single newline between each, exactly as "
    "they appeared) is parsed as JSON text with the standard library's `json.loads`, and that "
    "parsed value is returned. Ordinary prose lines before and after the fenced block are "
    "ignored (tolerated), and the JSON content itself may contain arbitrarily nested objects "
    "and arrays. When `text` contains NO such fenced json block anywhere, `parse_json_block` "
    "raises `ValueError`. When more than one such fenced block is present, only the FIRST one "
    "is used. `parse_key_values(text)` splits `text` into lines and, for each line that "
    "contains at least one colon character `:`, splits that line at its FIRST colon only, "
    "strips leading/trailing whitespace from both the part before the colon (the key) and the "
    "part after it (the value), and records `key -> value` in a dict it returns (a later line "
    "with a repeated key overwrites the value recorded for an earlier line with the same key); "
    "a line containing NO colon at all is skipped entirely (never added to the returned dict, "
    "never an error). `strip_fences(text)` splits `text` into lines and removes every line "
    "whose content, once leading/trailing whitespace is stripped, STARTS WITH three backticks "
    "(this covers both a bare fence line and a fence line immediately followed by a language "
    "tag such as `json` or `python`), keeping every other line completely unchanged and in its "
    "original order, then joins the surviving lines back together with a single newline between "
    "each (no trailing newline added) and returns that joined string."
)

_PARSER_TEXT_JSON_BLOCK = (
    "Here is the result:\n"
    "```json\n"
    '{"a": 1, "b": {"c": 2, "d": [1, 2, 3]}}\n'
    "```\n"
    "Thanks!\n"
)
_PARSER_TEXT_NO_JSON = "no fenced json here, just prose.\n"
_PARSER_TEXT_KEY_VALUES = (
    "Name: Alice\n"
    "Just some prose without a colon\n"
    "Age: 30\n"
    "Time: 10:30\n"
)
_PARSER_TEXT_FENCED = "before\n```python\ncode_line_1\ncode_line_2\n```\nafter\n"

OUTPUT_PARSER_TASK = RealSystemTask(
    name="llm-output-parser-lib",
    cls="agent-infra",
    sentence=_OUTPUT_PARSER_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "output_parser",
        "api_calls": [
            {"id": "json_ok", "target": "parse_json_block",
             "args": [_PARSER_TEXT_JSON_BLOCK], "kwargs": {}},
            {"id": "json_error", "target": "parse_json_block",
             "args": [_PARSER_TEXT_NO_JSON], "kwargs": {}},
            {"id": "kv", "target": "parse_key_values",
             "args": [_PARSER_TEXT_KEY_VALUES], "kwargs": {}},
            {"id": "fences", "target": "strip_fences",
             "args": [_PARSER_TEXT_FENCED], "kwargs": {}},
        ],
        "checks": [
            # fence with a language tag + a nested-brace JSON value: proves the extraction is
            # LINE-based (never balanced-brace counting), so nesting survives intact.
            {"kind": "returns_equals", "call_id": "json_ok",
             "expected": {"a": 1, "b": {"c": 2, "d": [1, 2, 3]}}},
            # no-block edge case: must raise, never silently return None/empty.
            {"kind": "raises", "call_id": "json_error", "exception": "ValueError"},
            {"kind": "returns_equals", "call_id": "kv",
             "expected": {"Name": "Alice", "Age": "30", "Time": "10:30"}},
            {"kind": "returns_equals", "call_id": "fences",
             "expected": "before\ncode_line_1\ncode_line_2\nafter"},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(OUTPUT_PARSER_TASK)
# #EXT-060-REQ-29 End


# #EXT-060-REQ-30 Start
# TASK-25: the SECOND agent/LLM-infrastructure CREATE task from the atlas's wave-5 agent-infra
# vertical -- a Pydantic-AI-shaped schema-validation-retry loop -- graded by the ALREADY-LANDED
# `oracle_kind="agent"` dispatch REQ-11 lands (no new oracle code -- reuses `_grade_agent` ->
# `harness.agent_oracle.drive_agent`/`check_agent` verbatim). Structured output is extracted via
# tool/function calling (the model "calls" a `submit_output` function whose arguments ARE the
# candidate structured payload -- exactly how real structured-output libraries like Pydantic-AI/
# instructor implement extraction under the hood), so the ORDERED, args-checked `tool_calls`
# sequence `check_agent` already grades independently proves BOTH that exactly two model
# round-trips occurred (never zero retries, never more than one) AND that the second submission
# is the schema-corrected one -- no new oracle mechanism needed. `tools["submit_output"]`'s
# canned observation is a plain audit-log acknowledgement (its value is never consulted for
# validity by the agent) -- the required-keys schema check itself is LOCAL to the agent, mirroring
# the built agent code every fixture below implements.
_VALIDATION_RETRY_SENTENCE = (
    "Write a single-file Python plain-Python agent program in a file named main.py, "
    "stdlib-only (the `json`, `os`, `sys`, and `urllib.request` modules are enough), "
    "implementing a validation-retry loop that extracts STRUCTURED output from a chat-style "
    "language model through tool/function calling -- distinct from a model that merely answers "
    "in prose. It reads its LLM endpoint from the environment variable `OPENAI_BASE_URL` and its "
    "controlled-tool endpoint from the environment variable `JAROS_TOOL_URL`; it takes its goal "
    "from `sys.argv[1]`. Maintain a list of chat messages, starting with exactly one message "
    "`{\"role\": \"user\", \"content\": <goal>}`. The REQUIRED schema for the structured output "
    "is exactly the two keys `name` and `email` (both must be present for the output to be "
    "VALID; any other keys are ignored; either key missing makes the output INVALID). Repeat "
    "the following up to twice (at most 2 requests to the model in total): send an HTTP POST "
    "request with a JSON body `{\"model\": \"stub\", \"messages\": <the current message list>}` "
    "to `f\"{OPENAI_BASE_URL}/chat/completions\"`, and parse the JSON response's "
    "`response[\"choices\"][0][\"message\"]`. That message's non-empty `\"tool_calls\"` list's "
    "first entry's `[\"function\"][\"name\"]` is the structured-output function the model chose "
    "to call, and its `[\"function\"][\"arguments\"]` is a JSON-encoded STRING of the model's "
    "candidate structured-output payload (parse it with `json.loads`); append that assistant "
    "message (including its `\"tool_calls\"`) to the message list, then send an HTTP POST "
    "request with the parsed payload as a JSON body to `f\"{JAROS_TOOL_URL}/<function_name>\"` "
    "(an audit-log sink recording every candidate submission -- its JSON response's "
    "`\"observation\"` value is not needed for validation), and append a message "
    "`{\"role\": \"tool\", \"tool_call_id\": <that tool call's \"id\">, \"content\": "
    "json.dumps(<that endpoint's \"observation\" value>)}` to the message list. Then LOCALLY "
    "check the parsed payload against the required schema (both `name` and `email` present). If "
    "VALID: print EXACTLY the string `\"__JAROS_AGENT_FINAL__\"` followed by "
    "`json.dumps(<the parsed payload>)` followed by `\"__END__\"`, with no other output "
    "anywhere, then exit with status 0 -- do not send any further request to the model. If "
    "INVALID and this was the FIRST request: append one more message to the message list, "
    "`{\"role\": \"user\", \"content\": <a string describing the validation error, naming every "
    "missing required key>}` (so the retry request the model sees literally contains the "
    "validation failure), then repeat the loop (send a SECOND chat-completions request) -- this "
    "is the ONE allowed retry. If INVALID and this was already the SECOND request (the retry "
    "also failed validation), print EXACTLY the string `\"__JAROS_AGENT_FINAL__\"` followed by "
    "the literal text `\"validation failed after retry\"` followed by `\"__END__\"`, with no "
    "other output anywhere, then exit with status 0, without sending a third request."
)

VALIDATION_RETRY_TASK = RealSystemTask(
    name="schema-validation-retry-loop",
    cls="agent-infra",
    sentence=_VALIDATION_RETRY_SENTENCE,
    oracle_kind="agent",
    oracle_spec={
        "entry": "main.py",
        # Turn 1: the model's FIRST structured-output attempt is missing the required `email`
        # key (invalid); turn 2 (served only if the agent actually retries) is the corrected,
        # valid attempt.
        "script": [
            tool_call_turn("submit_output", {"name": "Alice"}),
            tool_call_turn("submit_output", {"name": "Alice", "email": "alice@example.com"}),
        ],
        "tools": {
            "submit_output": {"logged": True},
        },
        "goal": "produce a JSON object describing a new user's signup with required keys name and email",
        # An ORDERED, args-exact 2-entry expectation: a build that never retries makes only ONE
        # submit_output call (length mismatch, rejected); a build that retries but resubmits the
        # SAME invalid payload fails the second entry's args match (rejected).
        "expect_tool_calls": [
            {"name": "submit_output", "args": {"name": "Alice"}},
            {"name": "submit_output", "args": {"name": "Alice", "email": "alice@example.com"}},
        ],
        "expect_final_contains": "alice@example.com",
        "expect_terminated": True,
    },
)

REAL_SYSTEMS_TASKS.append(VALIDATION_RETRY_TASK)
# #EXT-060-REQ-30 End


# #EXT-060-REQ-31 Start
# TASK-26: a THIRD import-oracle-shaped CREATE task from the atlas's top impact x buildability
# lists, in a NEW backup/ops vertical -- a Grandfather-Father-Son (GFS) backup retention pruning
# library -- graded by the ALREADY-LANDED "import" oracle_kind dispatch REQ-3 lands (no new
# oracle code -- reuses `_grade_import` -> `harness.import_driver.drive_import` verbatim). Every
# expected value below was hand-verified via a scratch computation of the exact same
# daily/weekly/monthly grouping rule the sentence pins (see the task's commit) before being added
# to the roster.
_GFS_RETENTION_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "gfs_retention.py, using only the standard library, defining exactly one public function "
    "`compute_keep_dates(snapshots, keep_daily, keep_weekly, keep_monthly)` implementing a "
    "Grandfather-Father-Son (GFS) backup retention policy. `snapshots` is a list of ISO-format "
    "(`YYYY-MM-DD`) date strings, one per day a backup snapshot exists, in any order, with no "
    "duplicate dates; `keep_daily`/`keep_weekly`/`keep_monthly` are non-negative integers. The "
    "function returns a new list of the ISO date strings that must be KEPT under the policy, "
    "sorted in ascending order with no duplicate entries, computed as the UNION of three tiers "
    "(a date belonging to more than one tier appears only once in the returned list): (1) the "
    "DAILY tier keeps the `keep_daily` most-recent dates from `snapshots` outright (by calendar "
    "date order); (2) the WEEKLY tier groups `snapshots` by ISO calendar week (the "
    "`(iso_year, iso_week)` pair Python's `datetime.date.isocalendar()` reports -- a week runs "
    "Monday through Sunday), orders the distinct weeks that contain at least one snapshot from "
    "most-recent to least-recent, takes the `keep_weekly` most-recent of those weeks, and from "
    "EACH of those weeks keeps only the single newest snapshot date within that week; (3) the "
    "MONTHLY tier groups `snapshots` by calendar month (the `(year, month)` pair), orders the "
    "distinct months that contain at least one snapshot from most-recent to least-recent, takes "
    "the `keep_monthly` most-recent of those months, and from EACH of those months keeps only "
    "the single newest snapshot date within that month. When `keep_daily`/`keep_weekly`/"
    "`keep_monthly` is larger than the number of dates/distinct weeks/distinct months actually "
    "available, that tier simply keeps everything it has (never an error, never a padded or "
    "fabricated date)."
)

# 15 snapshot dates spanning three calendar months (May/June/July 2024), spaced 5 days apart so
# several fall in the SAME ISO week or SAME calendar month (hand-verified isocalendar()/month
# groupings via a scratch script before being pinned here): weeks 19/21/24/26 each hold TWO of
# these dates, and May/June/July each hold several -- exactly what exercises the "keep only the
# newest in each bucket" rule. Passed in intentionally SHUFFLED order to also prove the build
# sorts by calendar date itself rather than trusting input order.
_GFS_SNAPSHOTS_SHUFFLED = [
    "2024-06-05", "2024-05-11", "2024-07-10", "2024-05-01", "2024-06-15", "2024-05-26",
    "2024-06-30", "2024-05-16", "2024-06-20", "2024-05-06", "2024-07-05", "2024-05-31",
    "2024-06-10", "2024-05-21", "2024-06-25",
]
# keep_daily=3 -> {07-10, 07-05, 06-30} outright. keep_weekly=4 -> the 4 most-recent distinct
# ISO weeks (28, 27, 26, 25) newest-per-week: week28->07-10 (dup daily), week27->07-05 (dup
# daily), week26 (06-25/06-30)->06-30 (dup daily), week25 (06-20 only)->06-20 (NEW, unique to
# the weekly tier). keep_monthly=3 -> the 3 most-recent distinct months (July/June/May)
# newest-per-month: July->07-10 (dup), June->06-30 (dup), May (05-01..05-31)->05-31 (NEW, unique
# to the monthly tier). Union, sorted: exactly the 5 dates below -- proving BOTH tiers'
# independent grouping logic AND the multi-tier-overlap dedup rule in one driven call.
_GFS_EXPECTED_KEEP = [
    "2024-05-31", "2024-06-20", "2024-06-30", "2024-07-05", "2024-07-10",
]

GFS_RETENTION_TASK = RealSystemTask(
    name="backup-retention-gfs-pruning-lib",
    cls="backup",
    sentence=_GFS_RETENTION_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "gfs_retention",
        "api_calls": [
            {"id": "gfs_main", "target": "compute_keep_dates",
             "args": [_GFS_SNAPSHOTS_SHUFFLED, 3, 4, 3], "kwargs": {}},
            # fewer-than-policy edge case: only 3 snapshots exist at all, but every tier asks
            # for 10 -- a correct build simply keeps all 3 (no error, no padding).
            {"id": "gfs_fewer_than_policy", "target": "compute_keep_dates",
             "args": [["2024-01-03", "2024-01-01", "2024-01-02"], 10, 10, 10], "kwargs": {}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "gfs_main", "expected": _GFS_EXPECTED_KEEP},
            {"kind": "returns_equals", "call_id": "gfs_fewer_than_policy",
             "expected": ["2024-01-01", "2024-01-02", "2024-01-03"]},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(GFS_RETENTION_TASK)
# #EXT-060-REQ-31 End


# #EXT-060-REQ-32 Start
# TASK-27: a FOURTH import-oracle-shaped CREATE task, in a devtools/CI vertical -- a CI job-
# matrix expansion library -- graded by the SAME ALREADY-LANDED "import" oracle_kind dispatch
# REQ-3 lands (no new oracle code -- reuses `_grade_import` -> `harness.import_driver.drive_import`
# verbatim). Every expected value below was hand-verified via a scratch `itertools.product`
# computation of the exact same axis-ordering/exclude/include rule the sentence pins (see the
# task's commit) before being added to the roster.
_CI_MATRIX_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "ci_matrix.py, using only the standard library, defining exactly one public function "
    "`expand_matrix(matrix, exclude=None, include=None)` that expands a continuous-integration "
    "job matrix configuration into the full list of job dicts. `matrix` is a dict mapping an "
    "axis name (a string, e.g. `\"os\"`) to a list of that axis's possible values; `exclude` "
    "(defaulting to an empty list when omitted or `None`) is a list of dicts, each naming a "
    "SUBSET of the matrix's axes (as few as one axis, up to all of them) with a specific value "
    "for each named axis; `include` (defaulting to an empty list when omitted or `None`) is a "
    "list of extra, ready-made job dicts. The function computes the full cross product of "
    "`matrix`'s axes -- iterating the axis NAMES in ascending alphabetical (string-sorted) "
    "order, with the alphabetically LAST axis's values cycling fastest (exactly the ordering "
    "`itertools.product(*[matrix[axis] for axis in sorted(matrix)])` produces, each combination "
    "turned into a `{axis_name: value, ...}` dict) -- then REMOVES from that cross product "
    "every generated job dict that matches ALL of the axis:value pairs named by AT LEAST ONE "
    "`exclude` entry (an exclude entry naming only one axis removes every job whose value on "
    "that one axis matches, regardless of its value on any other axis), preserving the relative "
    "order of the jobs that remain, and finally APPENDS every entry of `include` verbatim, "
    "unchanged and in the given order, to the end of that filtered list (an `include` entry is "
    "never expanded, never deduplicated against an existing job, and is unaffected by "
    "`exclude`). Returns the resulting list of job dicts."
)

CI_MATRIX_TASK = RealSystemTask(
    name="ci-job-matrix-expansion-lib",
    cls="devtools",
    sentence=_CI_MATRIX_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "ci_matrix",
        "api_calls": [
            # 2x3 matrix + 1 exclude (full-axis match) + 1 include (verbatim append).
            {"id": "full_matrix", "target": "expand_matrix",
             "args": [
                 {"os": ["linux", "windows"], "python": ["3.9", "3.10", "3.11"]},
                 [{"os": "windows", "python": "3.9"}],
                 [{"os": "macos", "python": "3.11", "extra": "beta"}],
             ], "kwargs": {}},
            # a SUBSET-of-axes exclude (names only "os") removes BOTH matching combos --
            # catches a build that only implements a full-axis-match exclude.
            {"id": "subset_exclude", "target": "expand_matrix",
             "args": [
                 {"os": ["linux", "windows"], "python": ["3.9", "3.10"]},
                 [{"os": "windows"}],
                 [],
             ], "kwargs": {}},
            # zero-argument-default exercise (EXT-036 REQ-45-style): `exclude`/`include` never
            # supplied at all, relying entirely on the `=None` defaults.
            {"id": "defaults_only", "target": "expand_matrix",
             "args": [{"env": ["dev", "prod"]}], "kwargs": {}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "full_matrix", "expected": [
                {"os": "linux", "python": "3.9"}, {"os": "linux", "python": "3.10"},
                {"os": "linux", "python": "3.11"}, {"os": "windows", "python": "3.10"},
                {"os": "windows", "python": "3.11"},
                {"os": "macos", "python": "3.11", "extra": "beta"},
            ]},
            {"kind": "returns_equals", "call_id": "subset_exclude", "expected": [
                {"os": "linux", "python": "3.9"}, {"os": "linux", "python": "3.10"},
            ]},
            {"kind": "returns_equals", "call_id": "defaults_only", "expected": [
                {"env": "dev"}, {"env": "prod"},
            ]},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(CI_MATRIX_TASK)
# #EXT-060-REQ-32 End


# #EXT-060-REQ-33 Start
# TASK-28: the canonical scoreboard's SECOND genuinely-SaaS-shaped "service" oracle_kind task (the
# first since REQ-9's items CRUD service) -- a stdlib REST/SQLite URL-shortener -- graded by the
# ALREADY-LANDED "service" oracle_kind dispatch REQ-9 lands (no new oracle code -- reuses
# `_grade_service` -> `harness.server_oracle.serve_and_check_stdlib` + the independent post-
# teardown SQLite row assertion verbatim). TWO measured limitations of `_do_request`'s plain
# `urllib.request.urlopen` client rule out grading the redirect endpoint for a KNOWN code
# directly: (1) `harness/server_oracle.py`'s `http_check` dict has no assertion for a response
# HEADER at all (only `status`/`json_contains`/`body_contains`/`json_body`, see that module's own
# docstring), so a `Location` value can never be checked; (2) MORE fundamentally, `urlopen`
# transparently FOLLOWS a real 3xx response (it has no way to observe `status == 301` either) --
# so even a bare status check on `GET /r/<known-code>` would make the check client dereference
# the arbitrary submitted URL, which is both unverifiable (the followed response has nothing to
# do with this service) and a hermeticity hazard in a sandboxed/no-egress subprocess. Per this
# requirement's own design note, the redirect TARGET is instead independently verified via the
# `GET /links/<code>` 200 `json_contains` check, and the redirect endpoint is exercised ONLY for
# an UNKNOWN code (`GET /r/999` -> 404, which never triggers a follow) -- the `Location`
# header/`301` contract is still pinned in full in the sentence (the built service must implement
# it correctly), it is simply not independently re-verifiable by this particular black-box oracle.
_URL_SHORTENER_SENTENCE = (
    "Write a Python web service in a file named main.py using only the standard library "
    "(http.server + sqlite3 + json). On startup it listens on the TCP port given by the PORT "
    "environment variable and stores data in a SQLite database file named data.db in the "
    "current directory (create the table if missing). It implements a URL-shortener API over a "
    "`links` resource, each link having an integer id (autoincrement) and the original `url` "
    "string it points to: `POST /links` with a JSON body `{\"url\": ...}` creates a new "
    "shortened link and responds 201 with a JSON body `{\"code\": ..., \"url\": ...}` -- the "
    "`code` is that link's newly assigned SQLite autoincrement `id`, converted to its plain "
    "decimal string form and used as nothing else (the first link ever created gets code "
    "`\"1\"`, the second gets code `\"2\"`, and so on -- never any other encoding, hashing, "
    "prefix, or randomness). `GET /links/<code>` responds 200 with that link's stored mapping "
    "as JSON `{\"code\": ..., \"url\": ...}` when `<code>` matches a previously created link's "
    "code, or 404 (with no meaningful body) when it does not. `GET /r/<code>` responds with "
    "HTTP status 301 and a `Location` response header set to exactly that link's original `url` "
    "when `<code>` matches a previously created link's code (redirecting a visitor to the "
    "original URL), or 404 (with no meaningful body) when it does not. Data must persist in "
    "data.db across process restarts."
)

URL_SHORTENER_TASK = RealSystemTask(
    name="url-shortener-http-service",
    cls="web",
    sentence=_URL_SHORTENER_SENTENCE,
    oracle_kind="service",
    oracle_spec={
        "entry": "main.py",
        "http_checks": [
            # ".invalid" is the RFC 2606-reserved TLD that is guaranteed never to resolve --
            # defense-in-depth so even an accidental follow-through can never reach a real host.
            {"method": "POST", "path": "/links", "json_body": {"url": "https://example.invalid/a"},
             "status": 201, "json_contains": {"code": "1", "url": "https://example.invalid/a"}},
            {"method": "POST", "path": "/links", "json_body": {"url": "https://example.invalid/b"},
             "status": 201, "json_contains": {"code": "2", "url": "https://example.invalid/b"}},
            {"method": "GET", "path": "/links/1", "status": 200,
             "json_contains": {"code": "1", "url": "https://example.invalid/a"}},
            {"method": "GET", "path": "/links/999", "status": 404},
            # the redirect endpoint IS exercised, but only for an UNKNOWN code -- a plain 404
            # response, never a 3xx the http_check client would transparently follow (see the
            # module-level note above for why a KNOWN code's redirect is never directly checked).
            {"method": "GET", "path": "/r/999", "status": 404},
        ],
        "db": {"path": "data.db", "min_rows": 2},
    },
)

REAL_SYSTEMS_TASKS.append(URL_SHORTENER_TASK)
# #EXT-060-REQ-33 End


# #EXT-060-REQ-34 Start
# TASK-29: a SECOND TIME-DEPENDENT ("clock" oracle_kind) CREATE task (the first since REQ-28's
# account lockout/backoff) -- an access-token validity-window issuer, in the auth vertical --
# graded by the ALREADY-LANDED `oracle_kind="clock"` dispatch REQ-28 lands (no new oracle code --
# reuses `_grade_clock` -> `harness.clock_oracle.grade_clock` verbatim). The sentence pins the
# `now_fn` injected-clock contract explicitly (mirroring REQ-28's `LOCKOUT_BACKOFF_TASK`) and
# deliberately says a token "is valid for 900 seconds" / its window has "elapsed", never
# "expires" -- that token trips `harness.adt_oracle`'s `ttl-store` keyword fingerprint and would
# falsely classify this unrelated auth class as the verified `ttl-store` leaf, breaking
# leaves-OFF (the exact same avoidance REQ-28's own module-level note already documents).
_TOKEN_VALIDITY_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named tokens.py, "
    "using only the standard library, defining exactly one public class named `TokenIssuer` "
    "modeling an access-token issuer. `TokenIssuer(now_fn)` accepts exactly one argument, the "
    "keyword `now_fn`: a zero-argument callable that returns the current time as an integer "
    "number of epoch seconds. The class must determine EVERY time-based decision by calling "
    "`now_fn()` at the moment it needs to know the current time -- it must never read the real "
    "system clock (`time.time()`, `datetime.datetime.now()`, or any other wall-clock source) "
    "for any purpose. It exposes exactly two methods: `issue(name)` (`name`: a string "
    "identifying the token's owner), which creates a new access token that is valid for exactly "
    "900 seconds starting from the `now_fn()` reading recorded at the moment `issue` is called, "
    "and returns that token's id -- for testability, the returned token id is EXACTLY the "
    "`name` string passed in, unchanged (issuing a second token for the SAME `name` simply "
    "replaces the previously issued token for that name with a fresh 900-second window starting "
    "from the new `now_fn()` reading); and `check(token)` (`token`: an id previously returned by "
    "`issue`), which returns `True` when `token` was issued by this same `TokenIssuer` instance "
    "and the current `now_fn()` reading is still strictly less than 900 seconds after the "
    "`now_fn()` reading recorded when that token was issued, and returns `False` in every other "
    "case -- including a `token` this instance never issued, and a token whose 900-second "
    "validity window has elapsed (the current `now_fn()` reading is 900 seconds or more after "
    "issuance). Once `check(token)` returns `False` for a given token because its 900-second "
    "window has elapsed, EVERY later `check(token)` call for that same token must also return "
    "`False` -- a token whose window has elapsed never becomes valid again."
)

TOKEN_VALIDITY_TASK = RealSystemTask(
    name="access-token-validity-window-lib",
    cls="auth",
    sentence=_TOKEN_VALIDITY_SENTENCE,
    oracle_kind="clock",
    oracle_spec={
        "module": "tokens",
        "entity": "TokenIssuer",
        "spec": {
            "clock_param": "now_fn",
            "construct_args": [],
            "construct_kwargs": {},
            # Hand-walked timeline: issue at t=0; t=899 is still inside the 900s window (True);
            # t=900 is the exact boundary (False -- "strictly less than 900" excludes it); t=3600
            # is a large jump well past the window, proving the SAME token stays False once its
            # window has elapsed rather than somehow re-validating.
            "timeline": [
                {"at": 0, "call": "issue", "args": ["alice"], "expect": {"returns": "alice"}},
                {"at": 899, "call": "check", "args": ["alice"], "expect": {"returns": True}},
                {"at": 900, "call": "check", "args": ["alice"], "expect": {"returns": False}},
                {"at": 3600, "call": "check", "args": ["alice"], "expect": {"returns": False}},
            ],
        },
    },
)

REAL_SYSTEMS_TASKS.append(TOKEN_VALIDITY_TASK)
# #EXT-060-REQ-34 End


# #EXT-060-REQ-35 Start
# TASK-30: growing the lopsided MODIFY half (26 CREATE vs only 6 MODIFY) -- a FIFTH
# LIFECYCLE-shaped MODIFY task, reusing HELPDESK_SLA_TASK's already-VERIFIED "state_machine"
# oracle_kind dispatch (REQ-13/REQ-24) verbatim, mirroring how REQ-14's ORDER_ADD_REFUND_MODIFY
# adds a transition to ORDER_LIFECYCLE_TASK's baseline. `start_system` is a hand-authored CORRECT
# baseline `helpdesk.py` matching REQ-24's `HELPDESK_SLA_TASK` contract exactly (no `hold()`/
# `release()` -- that is what this task adds); `mod_sentence` asks for a new `on_hold` state
# reachable via `hold()` from EITHER `triaged` OR `escalated`, with `release()` returning it to
# `triaged` -- legal only from those source states, the same "legal from two source states"
# shape REQ-18's `SUBSCRIPTION_LIFECYCLE_TASK.cancel()` already established for a CREATE task.
_HELPDESK_SLA_BASELINE_PY = (
    "class HelpdeskTicket:\n"
    "    _TRANSITIONS = {\n"
    "        (\"new\", \"triage\"): \"triaged\",\n"
    "        (\"triaged\", \"escalate\"): \"escalated\",\n"
    "        (\"triaged\", \"resolve\"): \"resolved\",\n"
    "        (\"escalated\", \"resolve\"): \"resolved\",\n"
    "        (\"triaged\", \"wait_on_customer\"): \"waiting_customer\",\n"
    "        (\"escalated\", \"wait_on_customer\"): \"waiting_customer\",\n"
    "        (\"waiting_customer\", \"resume\"): \"triaged\",\n"
    "        (\"resolved\", \"close\"): \"closed\",\n"
    "        (\"closed\", \"reopen\"): \"new\",\n"
    "    }\n"
    "\n"
    "    def __init__(self):\n"
    "        self._state = \"new\"\n"
    "\n"
    "    @property\n"
    "    def state(self):\n"
    "        return self._state\n"
    "\n"
    "    def _transition(self, action):\n"
    "        key = (self._state, action)\n"
    "        if key not in self._TRANSITIONS:\n"
    "            raise ValueError(f\"illegal transition: {action} from {self._state}\")\n"
    "        self._state = self._TRANSITIONS[key]\n"
    "\n"
    "    def triage(self):\n"
    "        self._transition(\"triage\")\n"
    "\n"
    "    def escalate(self):\n"
    "        self._transition(\"escalate\")\n"
    "\n"
    "    def resolve(self):\n"
    "        self._transition(\"resolve\")\n"
    "\n"
    "    def wait_on_customer(self):\n"
    "        self._transition(\"wait_on_customer\")\n"
    "\n"
    "    def resume(self):\n"
    "        self._transition(\"resume\")\n"
    "\n"
    "    def close(self):\n"
    "        self._transition(\"close\")\n"
    "\n"
    "    def reopen(self):\n"
    "        self._transition(\"reopen\")\n"
)

_HELPDESK_ADD_ONHOLD_MOD_SENTENCE = (
    "Modify helpdesk.py so that `HelpdeskTicket` ALSO supports two new zero-argument action "
    "methods: `hold()` and `release()`. `hold()` moves the ticket to a NEW state, the string "
    "`\"on_hold\"` (extend the `state` property so it can also report `\"on_hold\"`); `hold()` is "
    "legal from EITHER `\"triaged\"` OR `\"escalated\"` (whichever SLA tier the ticket was in when "
    "it went on hold), never from any other state (including `\"new\"`, `\"waiting_customer\"`, "
    "`\"resolved\"`, `\"closed\"`, or `\"on_hold\"` itself). `release()` moves the ticket from "
    "`\"on_hold\"` back to `\"triaged\"` (normal-tier handling resumes, regardless of which tier "
    "it was on hold from), and is legal ONLY from `\"on_hold\"`. Calling `hold()` or `release()` "
    "from any state where it is not legal must instead raise `ValueError` and must leave the "
    "ticket's `state` COMPLETELY UNCHANGED, exactly like every other illegal transition. Every "
    "other existing aspect of its behavior -- the `triage()`/`escalate()`/`wait_on_customer()`/"
    "`resume()`/`resolve()`/`close()`/`reopen()` methods, their exact legal source states, the "
    "`ValueError`-on-illegal-transition-with-unchanged-state contract, and the `state` property "
    "-- is completely unchanged."
)

HELPDESK_ADD_STATE_MODIFY = RealSystemModifyTask(
    name="helpdesk-sla-add-onhold-state-modify",
    cls="helpdesk-modify",
    start_system={"helpdesk.py": _HELPDESK_SLA_BASELINE_PY},
    mod_sentence=_HELPDESK_ADD_ONHOLD_MOD_SENTENCE,
    base_sentence=_HELPDESK_SLA_SENTENCE,
    oracle_kind="state_machine",
    oracle_spec={
        "module": "helpdesk",
        "entity": "HelpdeskTicket",
        "spec": {
            "states": ["new", "triaged", "escalated", "waiting_customer", "resolved", "closed",
                       "on_hold"],
            "initial": "new",
            "transitions": {
                "new:triage": "triaged",
                "triaged:escalate": "escalated",
                "triaged:resolve": "resolved",
                "escalated:resolve": "resolved",
                "triaged:wait_on_customer": "waiting_customer",
                "escalated:wait_on_customer": "waiting_customer",
                "waiting_customer:resume": "triaged",
                "resolved:close": "closed",
                "closed:reopen": "new",
                "triaged:hold": "on_hold",
                "escalated:hold": "on_hold",
                "on_hold:release": "triaged",
            },
            # An illegal hold-from-"new" FIRST (the ticket was never triaged), then the ORIGINAL
            # legal triage plus a regression of the ORIGINAL illegal close-from-triaged rejection,
            # then the NEW hold/release pair exercised from BOTH its legal source states
            # ("triaged" and, after escalating, "escalated"), then the ORIGINAL legal SLA path
            # back through resolve/close/reopen to "new" -- mixing the old legal path, the new
            # hold/release behavior, and an illegal-new-behavior rejection in one script.
            "drive": [
                {"action": "hold", "expect": "reject"},
                {"action": "triage", "expect": "accept"},
                {"action": "close", "expect": "reject"},
                {"action": "hold", "expect": "accept"},
                {"action": "release", "expect": "accept"},
                {"action": "escalate", "expect": "accept"},
                {"action": "hold", "expect": "accept"},
                {"action": "release", "expect": "accept"},
                {"action": "resolve", "expect": "accept"},
                {"action": "close", "expect": "accept"},
                {"action": "reopen", "expect": "accept"},
            ],
            "expect_final": "new",
        },
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(HELPDESK_ADD_STATE_MODIFY)
# #EXT-060-REQ-35 End


# #EXT-060-REQ-36 Start
# TASK-31: a SECOND "import" oracle_kind MODIFY task built on a payroll/tax CREATE task --
# reusing TAX_WITHHOLDING_TASK's already-VERIFIED "import" oracle_kind dispatch (REQ-3/REQ-26)
# verbatim, mirroring how REQ-7's RETRY_BASE_DELAY_MODIFY_TASK adds an optional keyword
# parameter to a reusable library. `start_system` is a hand-authored CORRECT baseline
# `withholding.py` matching REQ-26's `TAX_WITHHOLDING_TASK` contract exactly (no `cap_cents` --
# that is what this task adds); every regression value below is IDENTICAL to
# `TAX_WITHHOLDING_TASK.oracle_spec`'s own hand-verified values (re-derived, not re-imported, so
# this task's spec stays fully self-contained and independently readable).
_TAX_WITHHOLDING_BASELINE_PY = (
    "def compute_withholding_cents(income_cents, brackets):\n"
    "    total = 0\n"
    "    lower = 0\n"
    "    for upper, rate in brackets:\n"
    "        if upper is None:\n"
    "            portion = max(income_cents - lower, 0)\n"
    "        else:\n"
    "            portion = max(min(income_cents, upper) - lower, 0)\n"
    "        total += (portion * rate) // 100\n"
    "        if upper is not None:\n"
    "            lower = upper\n"
    "    return total\n"
)

_TAX_ADD_CAP_MOD_SENTENCE = (
    "Modify withholding.py so that `compute_withholding_cents` ALSO accepts an ADDITIONAL "
    "optional keyword parameter named `cap_cents`, with a default value of Python's `None` "
    "(meaning no cap -- when `cap_cents` is not supplied at all, or is `None`, behavior is "
    "completely unchanged from before). When `cap_cents` is supplied as an integer (not "
    "`None`), the function's return value is the SMALLER of (a) the withholding amount computed "
    "exactly as before from `income_cents` and `brackets`, and (b) `cap_cents` itself -- the "
    "computed withholding is never allowed to exceed `cap_cents`, no matter how high "
    "`income_cents` or the bracket rates are. Every other existing aspect of its behavior -- the "
    "progressive cumulative-bracket computation itself, integer floor division, no hardcoded "
    "jurisdiction/bracket table -- is completely unchanged."
)

TAX_ADD_CAP_MODIFY = RealSystemModifyTask(
    name="tax-withholding-add-annual-cap-modify",
    cls="payroll-modify",
    start_system={"withholding.py": _TAX_WITHHOLDING_BASELINE_PY},
    mod_sentence=_TAX_ADD_CAP_MOD_SENTENCE,
    base_sentence=_TAX_WITHHOLDING_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "withholding",
        "api_calls": [
            # Regression: the ORIGINAL four calls (REQ-26's exact hand-verified values), invoked
            # with no `cap_cents` at all -- a build that changed the `=None` default to anything
            # else, or that caps even when uncapped, fails one of these.
            {"id": "zero", "target": "compute_withholding_cents",
             "args": [0, _TAX_WITHHOLDING_BRACKETS], "kwargs": {}},
            {"id": "boundary", "target": "compute_withholding_cents",
             "args": [100000, _TAX_WITHHOLDING_BRACKETS], "kwargs": {}},
            {"id": "mid", "target": "compute_withholding_cents",
             "args": [225037, _TAX_WITHHOLDING_BRACKETS], "kwargs": {}},
            {"id": "top", "target": "compute_withholding_cents",
             "args": [500000, _TAX_WITHHOLDING_BRACKETS], "kwargs": {}},
            # New: the $2,250.37 income's NATURAL withholding is 35007 cents (see REQ-26's own
            # "mid" comment) -- a $200.00 (20000-cent) cap BINDS, capping the result down to
            # exactly 20000.
            {"id": "cap_binding", "target": "compute_withholding_cents",
             "args": [225037, _TAX_WITHHOLDING_BRACKETS], "kwargs": {"cap_cents": 20000}},
            # New: the SAME income with a $500.00 (50000-cent) cap -- ABOVE the natural 35007 --
            # is a no-op: the cap must never RAISE the result, only ever lower it.
            {"id": "cap_noop", "target": "compute_withholding_cents",
             "args": [225037, _TAX_WITHHOLDING_BRACKETS], "kwargs": {"cap_cents": 50000}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "zero", "expected": 0},
            {"kind": "returns_equals", "call_id": "boundary", "expected": 10000},
            {"kind": "returns_equals", "call_id": "mid", "expected": 35007},
            {"kind": "returns_equals", "call_id": "top", "expected": 100000},
            {"kind": "returns_equals", "call_id": "cap_binding", "expected": 20000},
            {"kind": "returns_equals", "call_id": "cap_noop", "expected": 35007},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(TAX_ADD_CAP_MODIFY)
# #EXT-060-REQ-36 End


# #EXT-060-REQ-37 Start
# TASK-32: a SECOND "cli-exact" oracle_kind MODIFY task, built on the elections CREATE task --
# reusing IRV_TALLY_TASK's already-VERIFIED "cli-exact" oracle_kind dispatch (REQ-25) verbatim,
# mirroring how REQ-10's INI_DEFAULT_FLAG_MODIFY_TASK reuses the same dispatch for a config CLI.
# `start_system` is a hand-authored CORRECT baseline `main.py` implementing REQ-25's ORIGINAL
# instant-runoff contract exactly, EXCEPT for one deliberately UNSPECIFIED behavior the original
# sentence explicitly disclaims ("the graded input never produces a tie for fewest"): on a tie
# for fewest votes, this baseline breaks it by eliminating the alphabetically EARLIER candidate
# (`min` over `(count, name)`) -- a plausible but WRONG guess, distinct from the new rule this
# task adds. `mod_sentence` pins the new rule explicitly: on a tie for fewest, eliminate the
# candidate LATER alphabetically instead.
_IRV_TALLY_BASELINE_PY = '''import sys
from collections import Counter


def main():
    ballots = []
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        ballots.append(line.split(","))

    candidates = set()
    for ballot in ballots:
        candidates.update(ballot)

    eliminated = set()
    round_num = 1
    while True:
        counts = Counter()
        for candidate in candidates - eliminated:
            counts[candidate] = 0
        for ballot in ballots:
            for name in ballot:
                if name not in eliminated:
                    counts[name] += 1
                    break

        remaining = sorted(counts.keys())
        line = ", ".join(f"{name}={counts[name]}" for name in remaining)
        print(f"Round {round_num}: {line}")

        total = sum(counts.values())
        winner = None
        for name in remaining:
            if counts[name] * 2 > total:
                winner = name
                break
        if winner is not None:
            print(f"Winner: {winner}")
            return

        # Tie-break: alphabetically EARLIEST of the fewest -- an unspecified (and, per this
        # task's mod_sentence, now WRONG) guess for the case REQ-25 never exercises.
        fewest = min(remaining, key=lambda name: (counts[name], name))
        eliminated.add(fewest)
        print(f"Eliminated: {fewest}")
        round_num += 1


if __name__ == "__main__":
    main()
'''

_IRV_ADD_TIE_RULE_MOD_SENTENCE = (
    "Modify main.py so that, when there is a TIE for fewest first-choice votes among two or "
    "more candidates still in the race in some round, it eliminates the candidate whose name "
    "is LATER in alphabetical order among those tied (instead of any other tie-breaking rule) "
    "-- printing `Eliminated: <name>` for that alphabetically-later candidate, exactly like any "
    "other elimination. When there is NO tie for fewest (a single candidate has strictly fewer "
    "votes than every other remaining candidate), behavior is completely unchanged: that "
    "single candidate is eliminated exactly as before. Every other existing aspect of its "
    "behavior -- the per-round tally and `Round <N>: ...` output format, the strict-majority "
    "`Winner: <name>` rule, ballot transfer to each ballot's next remaining ranked candidate, "
    "and a ballot with no remaining ranked candidate casting no further vote -- is completely "
    "unchanged."
)

# 22 ballots: 10 rank A alone (A is never eliminated, so a second choice is never needed); 6
# rank B first then C; 6 rank C first then B. Round 1: A=10, B=6, C=6 -- no majority (needs
# >11), and B/C TIE for fewest at 6 each. The new rule eliminates C (later alphabetically than
# B); C's 6 ballots transfer to their second choice, B. Round 2: A=10, B=12 -- B now has a
# strict majority (12 > 11) and wins -- breaking the tie the OTHER way (eliminating B instead)
# would transfer B's votes to C and hand C the win instead, proving the alphabetical rule (not
# an arbitrary tie-break) genuinely decides the outcome.
_IRV_TIE_STDIN = ("A\n" * 10) + ("B,C\n" * 6) + ("C,B\n" * 6)
_IRV_TIE_EXPECTED_STDOUT = (
    "Round 1: A=10, B=6, C=6\n"
    "Eliminated: C\n"
    "Round 2: A=10, B=12\n"
    "Winner: B\n"
)

IRV_ADD_TIE_RULE_MODIFY = RealSystemModifyTask(
    name="irv-tally-add-tie-elimination-rule-modify",
    cls="elections-modify",
    start_system={"main.py": _IRV_TALLY_BASELINE_PY},
    mod_sentence=_IRV_ADD_TIE_RULE_MOD_SENTENCE,
    base_sentence=_IRV_TALLY_SENTENCE,
    oracle_kind="cli-exact",
    oracle_spec={
        "argv": [],
        "stdin": _IRV_TIE_STDIN,
        "expected_stdout": _IRV_TIE_EXPECTED_STDOUT,
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(IRV_ADD_TIE_RULE_MODIFY)
# #EXT-060-REQ-37 End


# #EXT-060-REQ-38 Start
# TASK-33: a SECOND "service" oracle_kind MODIFY task, built on the web/URL-shortener CREATE
# task -- reusing URL_SHORTENER_TASK's already-VERIFIED "service" oracle_kind dispatch
# (REQ-9/REQ-33) verbatim, mirroring how REQ-10's REST_SQLITE_ADD_UPDATE_MODIFY adds an endpoint
# to the items CRUD service. `start_system` is a hand-authored CORRECT baseline `main.py`
# matching REQ-33's `URL_SHORTENER_TASK` contract exactly (no `DELETE` -- that is what this task
# adds); `mod_sentence` asks for a `DELETE /links/<code>` endpoint that actually removes the row
# (a subsequent `GET` for that same code must 404, not just report success).
_URL_SHORTENER_BASELINE_PY = '''import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

DB_PATH = "data.db"


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS links ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT)"
    )
    conn.commit()
    return conn


CONN = _init_db()


def _link_id(path, prefix):
    parts = urlparse(path).path.strip("/").split("/")
    if len(parts) == 2 and parts[0] == prefix:
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        link_id = _link_id(path, "links")
        if link_id is not None:
            cur = CONN.execute("SELECT id, url FROM links WHERE id = ?", (link_id,))
            row = cur.fetchone()
            if row is None:
                self.send_response(404)
                self.end_headers()
            else:
                self._send_json(200, {"code": str(row[0]), "url": row[1]})
            return
        redirect_id = _link_id(path, "r")
        if redirect_id is not None:
            cur = CONN.execute("SELECT id, url FROM links WHERE id = ?", (redirect_id,))
            row = cur.fetchone()
            if row is None:
                self.send_response(404)
                self.end_headers()
            else:
                self.send_response(301)
                self.send_header("Location", row[1])
                self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path != "/links":
            self.send_response(404)
            self.end_headers()
            return
        data = self._read_json()
        url = data.get("url")
        cur = CONN.execute("INSERT INTO links (url) VALUES (?)", (url,))
        CONN.commit()
        self._send_json(201, {"code": str(cur.lastrowid), "url": url})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ["PORT"])
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
'''

_SHORTENER_ADD_DELETE_MOD_SENTENCE = (
    "Add a `DELETE /links/<code>` endpoint: when `<code>` matches a previously created link's "
    "code, delete that link and respond 204 with no body; a subsequent `GET /links/<code>` for "
    "that SAME now-deleted code must respond 404 (exactly like a code that was never created). "
    "When `<code>` does NOT match any existing link (including one already deleted), "
    "`DELETE /links/<code>` responds 404 with no meaningful body and has no other effect. Every "
    "other existing endpoint (`POST /links`, `GET /links/<code>` for a code that still exists, "
    "and `GET /r/<code>`) is completely unchanged."
)

SHORTENER_ADD_DELETE_MODIFY = RealSystemModifyTask(
    name="url-shortener-add-delete-endpoint-modify",
    cls="web-modify",
    start_system={"main.py": _URL_SHORTENER_BASELINE_PY},
    mod_sentence=_SHORTENER_ADD_DELETE_MOD_SENTENCE,
    base_sentence=_URL_SHORTENER_SENTENCE,
    oracle_kind="service",
    oracle_spec={
        "entry": "main.py",
        "http_checks": [
            {"method": "POST", "path": "/links", "json_body": {"url": "https://example.invalid/a"},
             "status": 201, "json_contains": {"code": "1", "url": "https://example.invalid/a"}},
            {"method": "POST", "path": "/links", "json_body": {"url": "https://example.invalid/b"},
             "status": 201, "json_contains": {"code": "2", "url": "https://example.invalid/b"}},
            # Regression: the ORIGINAL GET/404 semantics, unchanged.
            {"method": "GET", "path": "/links/1", "status": 200,
             "json_contains": {"code": "1", "url": "https://example.invalid/a"}},
            {"method": "GET", "path": "/links/999", "status": 404},
            {"method": "GET", "path": "/r/999", "status": 404},
            # New: DELETE the first link, then confirm it is genuinely gone (not just a 204 with
            # no real effect), plus a DELETE of an already-deleted/unknown code stays 404.
            {"method": "DELETE", "path": "/links/1", "status": 204},
            {"method": "GET", "path": "/links/1", "status": 404},
            {"method": "DELETE", "path": "/links/1", "status": 404},
        ],
        # Link 1 was deleted; link 2 ("b") is left alone so the independent post-teardown row
        # assertion stays honestly satisfiable via the SURVIVING row.
        "db": {"path": "data.db", "min_rows": 1},
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(SHORTENER_ADD_DELETE_MODIFY)
# #EXT-060-REQ-38 End


# #EXT-060-REQ-39 Start
# TASK-34: a SECOND "clock" oracle_kind MODIFY task, built on the auth/lockout CREATE task --
# reusing LOCKOUT_BACKOFF_TASK's already-VERIFIED "clock" oracle_kind dispatch (REQ-28) verbatim,
# mirroring how REQ-14/REQ-16's MODIFY tasks add a new action method to their CREATE half's
# baseline. `start_system` is a hand-authored CORRECT baseline `lockout.py` matching REQ-28's
# `LOCKOUT_BACKOFF_TASK` contract exactly (no `admin_unlock()` -- that is what this task adds);
# `mod_sentence` asks for an `admin_unlock()` that clears an active lock IMMEDIATELY -- the
# driven timeline proves this by unlocking well BEFORE the lock's natural t=620 clear time (an
# `admin_unlock()` that is a no-op, or never wired up at all, is caught because the very next
# attempt at t=50 would still be inside the OLD lock window).
_LOCKOUT_BACKOFF_BASELINE_PY = '''class LockedOut(Exception):
    pass


class LoginAttemptTracker:
    def __init__(self, now_fn):
        self._now_fn = now_fn
        self._streak_count = 0
        self._streak_start = None
        self._locked_until = None

    def is_locked(self):
        if self._locked_until is None:
            return False
        return self._now_fn() < self._locked_until

    def record_attempt(self, success):
        now = self._now_fn()
        if self._locked_until is not None:
            if now < self._locked_until:
                raise LockedOut()
            self._locked_until = None

        if success:
            self._streak_count = 0
            self._streak_start = None
            return None

        if self._streak_start is None or (now - self._streak_start) > 300:
            self._streak_start = now
            self._streak_count = 1
        else:
            self._streak_count += 1

        if self._streak_count >= 3:
            self._locked_until = now + 600

        return None
'''

_LOCKOUT_ADMIN_UNLOCK_MOD_SENTENCE = (
    "Modify lockout.py so that `LoginAttemptTracker` ALSO supports a new zero-argument action "
    "method named `admin_unlock()`. Calling `admin_unlock()` immediately clears any currently "
    "active lock, exactly as if the account's recorded lock-clear time had already been "
    "reached: `is_locked()` must return `False` immediately after `admin_unlock()` is called, "
    "even when the previously recorded lock-clear time has NOT yet actually been reached, and "
    "the very next `record_attempt(...)` call after `admin_unlock()` must be processed like any "
    "other unlocked attempt (never raising `LockedOut` because of the old lock-clear time). "
    "Calling `admin_unlock()` while the account is NOT currently locked has no effect (it never "
    "raises, and leaves everything else unchanged). Every other existing aspect of "
    "`LoginAttemptTracker`'s behavior -- the failure-streak counting, the automatic lock after a "
    "third consecutive failure within 300 seconds, the automatic clearing once `now_fn()` "
    "reaches the recorded lock-clear time on its own, and `record_attempt`/`is_locked`'s "
    "existing contracts -- is completely unchanged."
)

LOCKOUT_ADMIN_UNLOCK_MODIFY = RealSystemModifyTask(
    name="lockout-add-admin-unlock-modify",
    cls="auth-modify",
    start_system={"lockout.py": _LOCKOUT_BACKOFF_BASELINE_PY},
    mod_sentence=_LOCKOUT_ADMIN_UNLOCK_MOD_SENTENCE,
    base_sentence=_LOCKOUT_BACKOFF_SENTENCE,
    oracle_kind="clock",
    oracle_spec={
        "module": "lockout",
        "entity": "LoginAttemptTracker",
        "spec": {
            "clock_param": "now_fn",
            "construct_args": [],
            "construct_kwargs": {},
            # t=0/10/20: three consecutive failures within the 300s window -- the third (t=20)
            # locks the account until t=20+600=620 (REQ-28's own timeline, a regression). t=30 is
            # still inside that lock (30 < 620) -> must raise LockedOut (regression). `admin_
            # unlock()` at t=40 must then clear the lock IMMEDIATELY -- t=50 is only 10
            # simulated seconds later, WAY before the natural t=620 clear, so a build whose
            # `admin_unlock` is a no-op (or never wired up) fails here: t=50's attempt would
            # still raise LockedOut under the OLD lock-clear time, but a genuinely-wired
            # `admin_unlock` lets it return None instead.
            "timeline": [
                {"at": 0, "call": "record_attempt", "args": [False], "expect": {"returns": None}},
                {"at": 10, "call": "record_attempt", "args": [False], "expect": {"returns": None}},
                {"at": 20, "call": "record_attempt", "args": [False], "expect": {"returns": None}},
                {"at": 30, "call": "record_attempt", "args": [True],
                 "expect": {"raises": "LockedOut"}},
                {"at": 40, "call": "admin_unlock", "args": [], "expect": {"returns": None}},
                {"at": 50, "call": "record_attempt", "args": [True], "expect": {"returns": None}},
            ],
            "expect_final": {"is_locked": False},
        },
    },
)

REAL_SYSTEMS_MODIFY_TASKS.append(LOCKOUT_ADMIN_UNLOCK_MODIFY)
# #EXT-060-REQ-39 End


# #EXT-060-REQ-40 Start
# TASK-35: a FIFTH import-oracle-shaped CREATE task, in a NEW reliability vertical -- a Stripe-style
# recovery-point request executor -- pulled from the atlas's wave-7 engineering-blog-mining
# "gradable-today" shortlist (docs/PRODUCTION-SYSTEMS-ATLAS.md EB9, simplified to the pure
# decision-table shape this shortlist targets: no new idempotency-replay/workflow-replay oracle,
# just the deterministic replay-decision logic itself), graded by the ALREADY-LANDED
# `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code -- reuses `_grade_import` ->
# `harness.import_driver.drive_import` verbatim). Every expected value below was hand-verified via
# a scratch walk of the exact same before/at-or-after-the-checkpoint rule the sentence pins, before
# being added to the roster.
_RECOVERY_POINT_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "recovery_point.py, using only the standard library, defining exactly one public function "
    "`replay_execution(steps, recovery_point)` that simulates resuming a crashed multi-step job "
    "from a saved recovery point (the Stripe-style pattern: a checkpoint is recorded at the step "
    "the job was AT when it stopped, not necessarily after that step finished). `steps` is a "
    "list of dicts, each `{\"name\": <string>, \"kind\": \"idempotent\"|\"non_idempotent\"}`, "
    "given in the exact order they must execute; `recovery_point` is an integer index into "
    "`steps` marking the saved checkpoint. Replay every step in `steps`' original order and "
    "decide, per step at index `i`, whether it actually runs: (1) if `i < recovery_point` (a "
    "step that is known to have run to completion in the earlier, interrupted attempt) -- when "
    "that step's `kind` is `\"idempotent\"`, run it again (it is safe to re-run, e.g. "
    "re-writing the same database row, so record it in the result); when its `kind` is "
    "`\"non_idempotent\"`, do NOT run it again (re-running it would have an unsafe duplicate "
    "side effect, e.g. charging a customer's card a second time, so it must be OMITTED from the "
    "result entirely); (2) if `i >= recovery_point` (the step the job was in the middle of when "
    "it stopped, or had never yet reached), run it unconditionally regardless of its `kind`, "
    "because a step at or after the checkpoint is not known to have completed. Return the list "
    "of the `name` strings of every step that was actually run (re-run or run for the first "
    "time), in `steps`' original order, never re-ordered and never deduplicated -- a step that "
    "is skipped per rule (1) is simply absent from the returned list. `recovery_point` may be "
    "`0` (nothing precedes it, so every step in `steps` runs unconditionally) or `len(steps) - "
    "1` (only the very last step runs unconditionally; every step before it is governed by rule "
    "(1))."
)

_RP_STEPS_ZERO = [
    {"name": "A", "kind": "idempotent"},
    {"name": "B", "kind": "non_idempotent"},
    {"name": "C", "kind": "idempotent"},
]
_RP_STEPS_MID = [
    {"name": "A", "kind": "idempotent"},
    {"name": "B", "kind": "non_idempotent"},
    {"name": "C", "kind": "idempotent"},
    {"name": "D", "kind": "non_idempotent"},
    {"name": "E", "kind": "idempotent"},
]
_RP_STEPS_END = [
    {"name": "A", "kind": "idempotent"},
    {"name": "B", "kind": "non_idempotent"},
    {"name": "C", "kind": "idempotent"},
    {"name": "D", "kind": "non_idempotent"},
]

RECOVERY_POINT_TASK = RealSystemTask(
    name="reliability-recovery-point-executor-lib",
    cls="reliability",
    sentence=_RECOVERY_POINT_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "recovery_point",
        "api_calls": [
            # recovery_point=0: nothing precedes it, every step runs unconditionally.
            {"id": "resume_from_zero", "target": "replay_execution",
             "args": [_RP_STEPS_ZERO, 0], "kwargs": {}},
            # recovery_point=3 (mid-list): before it, idempotent A/C re-run, non-idempotent B is
            # skipped; at/after it, D/E run unconditionally.
            {"id": "resume_mid_skip", "target": "replay_execution",
             "args": [_RP_STEPS_MID, 3], "kwargs": {}},
            # recovery_point=3 == len(steps)-1: only the trailing step D runs unconditionally;
            # A/C (idempotent) re-run, B (non-idempotent) is skipped.
            {"id": "resume_at_end", "target": "replay_execution",
             "args": [_RP_STEPS_END, 3], "kwargs": {}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "resume_from_zero",
             "expected": ["A", "B", "C"]},
            {"kind": "returns_equals", "call_id": "resume_mid_skip",
             "expected": ["A", "C", "D", "E"]},
            {"kind": "returns_equals", "call_id": "resume_at_end",
             "expected": ["A", "C", "D"]},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(RECOVERY_POINT_TASK)
# #EXT-060-REQ-40 End


# #EXT-060-REQ-41 Start
# TASK-36: a SIXTH import-oracle-shaped CREATE task, in a NEW authz vertical -- a Discord-style
# layered permission-overwrite resolver -- pulled from the SAME atlas wave-7 shortlist (§3.9's
# decision-table cluster), graded by the SAME ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3
# lands (no new oracle code). Every expected value below was hand-verified via a scratch
# clear-then-set bitmask walk of the exact same three-layer rule the sentence pins, before being
# added to the roster.
_PERMISSION_OVERWRITE_SENTENCE = (
    "Write a single-file Python module (never a script) in a file named "
    "permission_overwrite.py, using only the standard library, defining exactly one public "
    "function `resolve_permissions(everyone_allow, everyone_deny, role_overwrites, "
    "member_allow, member_deny)` that resolves a member's EFFECTIVE permission bitmask in one "
    "channel, modeled on a Discord-style layered permission-overwrite system. Every permission "
    "argument is a plain non-negative integer bitmask (each SET bit represents one distinct "
    "permission flag being present); `role_overwrites` is a list of zero or more "
    "`{\"allow\": <int bitmask>, \"deny\": <int bitmask>}` dicts, one per role the member holds "
    "that has an overwrite configured for this channel, in ANY order (the algorithm below "
    "unions every role's `deny` bits together and, separately, unions every role's `allow` bits "
    "together, so the relative order of entries in `role_overwrites` never affects the result). "
    "Starting from an all-clear permission value of `0`, apply exactly three layers IN THIS "
    "ORDER, each layer first CLEARING its deny bits from the running value, THEN SETTING its "
    "allow bits (deny-before-allow within each layer, so an allow bit in a layer always wins "
    "over a deny bit from that SAME layer, but a LATER layer's deny always overrides an EARLIER "
    "layer's allow): (1) the `@everyone` base layer -- clear every bit set in `everyone_deny`, "
    "then set every bit set in `everyone_allow`; (2) the combined role-overwrite layer -- let "
    "`role_deny` be the bitwise OR of every entry's `\"deny\"` in `role_overwrites` (`0` when "
    "the list is empty) and `role_allow` be the bitwise OR of every entry's `\"allow\"`; clear "
    "every bit set in `role_deny`, then set every bit set in `role_allow`; (3) the "
    "member-specific layer -- clear every bit set in `member_deny`, then set every bit set in "
    "`member_allow`. Return the final integer bitmask after all three layers have been applied "
    "in that order (`@everyone` base, then role denies-then-allows, then member deny-then-allow) "
    "-- a permission bit that no layer ever sets stays clear (denied) in the result."
)

PERMISSION_OVERWRITE_TASK = RealSystemTask(
    name="discord-permission-overwrite-resolution-lib",
    cls="authz",
    sentence=_PERMISSION_OVERWRITE_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "permission_overwrite",
        "api_calls": [
            # a role DENIES bit 2, but the MEMBER-specific overwrite explicitly ALLOWS bit 2 --
            # the later member layer must win: 0 -> role deny(2)->0 -> member allow(2) -> 2.
            {"id": "member_overrides_role_deny", "target": "resolve_permissions",
             "args": [0, 0, [{"allow": 0, "deny": 2}], 2, 0], "kwargs": {}},
            # @everyone DENIES bit 1, but a ROLE explicitly ALLOWS bit 1 -- the later role layer
            # must win over the earlier @everyone deny: 0 -> everyone deny(1)->0 -> role allow(1)->1.
            {"id": "role_overrides_everyone_deny", "target": "resolve_permissions",
             "args": [0, 1, [{"allow": 1, "deny": 0}], 0, 0], "kwargs": {}},
            # @everyone allows bits 1+2 (value 3); nothing ever mentions bit 4 at any layer -- it
            # must stay clear (denied) in the result, proving an ungranted permission is never
            # fabricated. Also exercises an EMPTY `role_overwrites` list (no role overwrites).
            {"id": "ungranted_permission_stays_denied", "target": "resolve_permissions",
             "args": [3, 0, [], 0, 0], "kwargs": {}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "member_overrides_role_deny", "expected": 2},
            {"kind": "returns_equals", "call_id": "role_overrides_everyone_deny", "expected": 1},
            {"kind": "returns_equals", "call_id": "ungranted_permission_stays_denied",
             "expected": 3},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(PERMISSION_OVERWRITE_TASK)
# #EXT-060-REQ-41 End


# #EXT-060-REQ-42 Start
# TASK-37: a SEVENTH import-oracle-shaped CREATE task, reusing the `cls="payroll"` vertical
# TAX_WITHHOLDING_TASK (REQ-26) already established -- an FLSA blended (weighted-average) overtime
# calculator, pulled from the SAME atlas wave-7 shortlist, graded by the SAME ALREADY-LANDED
# `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code). Every expected value below was
# hand-verified via scratch arithmetic of the exact same total-straight-pay + blended-rate +
# half-time-premium rule the sentence pins, before being added to the roster.
_BLENDED_OVERTIME_SENTENCE = (
    "Write a single-file Python module (never a script) in a file named blended_overtime.py, "
    "using only the standard library, defining exactly one public function "
    "`compute_blended_overtime_pay(entries)` that computes one week's total pay owed under the "
    "U.S. FLSA blended (weighted-average) overtime rule for an hourly worker who worked at more "
    "than one pay rate during the SAME workweek. `entries` is a list of `[rate_cents, hours]` "
    "two-element lists (`rate_cents`: a non-negative integer, the hourly rate in whole cents; "
    "`hours`: a non-negative int or float, the hours worked at that rate), covering every hour "
    "worked that week. Compute: `total_hours` = the sum of every entry's `hours`; "
    "`total_straight_pay_cents` = the sum, over every entry, of `rate_cents * hours` (each "
    "entry's own straight-time pay at its own rate; this value already pays EVERY hour, "
    "including any overtime hours, once at its own straight rate). When `total_hours` is less "
    "than or equal to `40`, no overtime premium is owed and the amount owed is simply "
    "`total_straight_pay_cents`. When `total_hours` is greater than `40`: the "
    "`blended_regular_rate` (in cents per hour) is `total_straight_pay_cents / total_hours` -- "
    "the weighted average of every rate actually worked that week, per 29 CFR 778.115; "
    "`overtime_hours` = `total_hours - 40`; the overtime PREMIUM owed on top of the straight pay "
    "already counted above is `0.5 * blended_regular_rate * overtime_hours` (only the extra "
    "HALF of the required time-and-a-half, since the other 1x was already paid via "
    "`total_straight_pay_cents`); the amount owed is `total_straight_pay_cents` plus that "
    "overtime premium. In every case (overtime or not), round the final amount owed to the "
    "nearest whole cent using ROUND-HALF-UP (a value ending in exactly `.5` cents rounds UP, "
    "e.g. `100.5` rounds to `101`, never Python's default round-half-to-even/'banker's "
    "rounding'), and return it as a single integer number of cents."
)

BLENDED_OVERTIME_TASK = RealSystemTask(
    name="flsa-blended-overtime-calculator-lib",
    cls="payroll",
    sentence=_BLENDED_OVERTIME_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "blended_overtime",
        "api_calls": [
            # under 40h -- no overtime at all: 2000 cents/hr * 30h = 60000 cents.
            {"id": "under_40_no_ot", "target": "compute_blended_overtime_pay",
             "args": [[[2000, 30]]], "kwargs": {}},
            # over 40h, a SINGLE rate: 1500*45=67500 straight; blended rate == the same 1500
            # (single rate); OT premium = 0.5*1500*5 = 3750; total = 71250.
            {"id": "over_40_single_rate", "target": "compute_blended_overtime_pay",
             "args": [[[1500, 45]]], "kwargs": {}},
            # over 40h, TWO rates (the blended case): straight = 1000*20 + 2000*25 = 70000;
            # total_hours=45; blended = 70000/45 = 1555.555...; OT premium =
            # 0.5*1555.555...*5 = 3888.888...; total = 73888.888... -> rounds (half-up) to 73889.
            {"id": "over_40_two_rates_blended", "target": "compute_blended_overtime_pay",
             "args": [[[1000, 20], [2000, 25]]], "kwargs": {}},
            # exactly 40h -- the boundary is NOT overtime ("greater than 40" required): 1200*40 =
            # 48000 straight, no premium.
            {"id": "exactly_40_boundary", "target": "compute_blended_overtime_pay",
             "args": [[[1200, 40]]], "kwargs": {}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "under_40_no_ot", "expected": 60000},
            {"kind": "returns_equals", "call_id": "over_40_single_rate", "expected": 71250},
            {"kind": "returns_equals", "call_id": "over_40_two_rates_blended", "expected": 73889},
            {"kind": "returns_equals", "call_id": "exactly_40_boundary", "expected": 48000},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(BLENDED_OVERTIME_TASK)
# #EXT-060-REQ-42 End


# #EXT-060-REQ-43 Start
# TASK-38: an EIGHTH import-oracle-shaped CREATE task, in a NEW comms vertical -- a Twilio-style
# SMS segmentation calculator -- pulled from the SAME atlas wave-7 shortlist (docs/PRODUCTION-
# SYSTEMS-ATLAS.md EB16), graded by the SAME ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3
# lands (no new oracle code). Every expected value below was hand-verified via scratch ceiling-
# division arithmetic of the exact same GSM-7-vs-UCS-2 + 160/153-vs-70/67 rule the sentence pins,
# before being added to the roster. Deliberately a SIMPLIFIED GSM-7 detection rule (plain visible
# ASCII + newline) rather than the real GSM 03.38 extension-table charset -- the sentence says so
# explicitly ("for THIS simplified... model"), so no oracle leak: every expected value is derived
# from that same simplified, visible contract.
_SMS_SEGMENT_SENTENCE = (
    "Write a single-file Python module (never a script) in a file named sms_segments.py, using "
    "only the standard library, defining exactly one public function `segment_sms(message)` "
    "that computes the SMS segmentation of a text message the way a carrier gateway (e.g. "
    "Twilio) would, for THIS simplified GSM-7-vs-UCS-2 model. `message` is a Python string. "
    "First classify its encoding: the message is GSM-7-ENCODABLE when every character in it is "
    "either a visible ASCII character (Unicode code point `0x20` through `0x7E` inclusive) or "
    "the newline character `\\n` (code point `0x0A`); if `message` contains ANY OTHER character "
    "(any accented letter, emoji, or other non-ASCII symbol), it must be sent as UCS-2 instead. "
    "The special case of the EMPTY string (`\"\"`, zero characters) is defined to be "
    "GSM-7-encodable (vacuously -- it contains no character outside the allowed set). Let `n` "
    "be the number of characters in `message` (Python's `len(message)`). Then compute the "
    "segment count: for GSM-7, a message with `n <= 160` fits in exactly 1 segment, and a "
    "message with `n > 160` is SPLIT across multiple concatenated segments of `153` characters' "
    "worth of payload each (segment count = the smallest integer `s` such that `s * 153 >= n`, "
    "i.e. ceiling division of `n` by `153`); for UCS-2, a message with `n <= 70` fits in exactly "
    "1 segment, and a message with `n > 70` is split across multiple concatenated segments of "
    "`67` characters' worth of payload each (segment count = the ceiling of `n` divided by "
    "`67`). The empty string is always exactly 1 segment (it is GSM-7-encodable per the rule "
    "above and `0 <= 160`). Return a 3-element sequence `(encoding, segment_count, n)` where "
    "`encoding` is the exact string `\"GSM-7\"` or `\"UCS-2\"`, `segment_count` is a positive "
    "integer, and `n` is `message`'s character count as defined above."
)

SMS_SEGMENT_TASK = RealSystemTask(
    name="sms-segmentation-calculator-lib",
    cls="comms",
    sentence=_SMS_SEGMENT_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "sms_segments",
        "api_calls": [
            # exactly 160 plain-ASCII chars -- fits in exactly 1 GSM-7 segment.
            {"id": "gsm_160", "target": "segment_sms", "args": ["A" * 160], "kwargs": {}},
            # 161 plain-ASCII chars -- one over the single-segment limit, must split at 153/seg:
            # ceil(161/153) = 2.
            {"id": "gsm_161", "target": "segment_sms", "args": ["A" * 161], "kwargs": {}},
            # a single BMP emoji (U+263A) plus 69 ASCII chars = 70 total -- the emoji forces
            # UCS-2, and 70 fits in exactly 1 UCS-2 segment.
            {"id": "ucs2_70", "target": "segment_sms",
             "args": ["☺" + "A" * 69], "kwargs": {}},
            # same emoji plus 70 ASCII chars = 71 total -- one over the UCS-2 single-segment
            # limit, must split at 67/seg: ceil(71/67) = 2.
            {"id": "ucs2_71", "target": "segment_sms",
             "args": ["☺" + "A" * 70], "kwargs": {}},
            # the empty string is always exactly 1 GSM-7 segment, 0 characters.
            {"id": "empty_message", "target": "segment_sms", "args": [""], "kwargs": {}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "gsm_160", "expected": ["GSM-7", 1, 160]},
            {"kind": "returns_equals", "call_id": "gsm_161", "expected": ["GSM-7", 2, 161]},
            {"kind": "returns_equals", "call_id": "ucs2_70", "expected": ["UCS-2", 1, 70]},
            {"kind": "returns_equals", "call_id": "ucs2_71", "expected": ["UCS-2", 2, 71]},
            {"kind": "returns_equals", "call_id": "empty_message", "expected": ["GSM-7", 1, 0]},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(SMS_SEGMENT_TASK)
# #EXT-060-REQ-43 End


# #EXT-060-REQ-44 Start
# TASK-39: a NINTH CREATE task, in a NEW background-job-processing vertical -- graded by the
# ALREADY-LANDED "state_machine" oracle_kind dispatch REQ-13 lands (no new oracle code: reuses
# `_grade_state_machine` -> `harness.state_machine_oracle.grade_state_machine` verbatim). Distinct
# from every prior "state_machine" task (ORDER_LIFECYCLE_TASK/HELPDESK_SLA_TASK): this models a
# background job's queued/running/succeeded/failed/retrying/dead lifecycle, including a RETRY
# CYCLE where the SAME `start()` action legally fires from TWO different source states
# (`"queued"` for the very first attempt, `"retrying"` after a failure) -- a shape none of the
# existing lifecycle tasks exercises. Deliberately phrased as a "background-job processor"
# throughout (never "job queue"/"task queue") so the state name `"queued"` (an ordinary status
# adjective, required by the task spec) can never be mistaken for the FIFO-queue leaf's own
# vocabulary -- see the leaf-fingerprint note on the banned-keyword test in this REQ's test module
# for why this is provably safe, not just cautious phrasing.
_JOB_LIFECYCLE_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named job.py, "
    "using only the standard library, defining exactly one public class named `Job` modeling "
    "the lifecycle of one unit of work inside a background-job processor (the kind of "
    "asynchronous worker system that runs deferred tasks outside an HTTP request, distinct from "
    "a simple pay/ship/deliver order workflow). `Job()` (no constructor arguments) creates a "
    "new job whose initial state is the string `\"queued\"`. The class exposes a real Python "
    "`@property` named `state` that returns the job's current state as one of the strings "
    "`\"queued\"`, `\"running\"`, `\"succeeded\"`, `\"failed\"`, `\"retrying\"`, or `\"dead\"`. "
    "It defines exactly five zero-argument action methods: `start()` moves the job to "
    "`\"running\"` -- legal from EITHER `\"queued\"` (the job's very first start) OR "
    "`\"retrying\"` (resuming after a retry) -- the SAME method resumes a retried job that "
    "originally started it; `succeed()` moves the job from `\"running\"` to `\"succeeded\"`; "
    "`fail()` moves the job from `\"running\"` to `\"failed\"`; `retry()` moves the job from "
    "`\"failed\"` to `\"retrying\"` -- a failed job is scheduled for another attempt, and "
    "calling `start()` again then moves it from `\"retrying\"` back to `\"running\"` exactly "
    "like the original start, so a job cycles through this bounded failed/retrying/running loop "
    "as many times as `retry()`/`start()` are legally called before finally succeeding or being "
    "killed; `kill()` moves the job to `\"dead\"` -- legal from `\"queued\"`, `\"running\"`, "
    "`\"failed\"`, OR `\"retrying\"` (a job is force-killed before it ever reaches a terminal "
    "`\"succeeded\"` state). Each of these five methods is legal ONLY from the exact source "
    "state(s) named above; calling any of them from any OTHER current state (for example "
    "calling `succeed()` on a job that has never been started, or calling `retry()` on a job "
    "that already succeeded) must instead raise `ValueError` and must leave the job's `state` "
    "COMPLETELY UNCHANGED -- no partial mutation before the raise."
)

JOB_QUEUE_LIFECYCLE_TASK = RealSystemTask(
    name="background-job-lifecycle-state-machine",
    cls="jobs",
    sentence=_JOB_LIFECYCLE_SENTENCE,
    oracle_kind="state_machine",
    oracle_spec={
        "module": "job",
        "entity": "Job",
        "spec": {
            "states": ["queued", "running", "succeeded", "failed", "retrying", "dead"],
            "initial": "queued",
            "transitions": {
                "queued:start": "running",
                "retrying:start": "running",
                "running:succeed": "succeeded",
                "running:fail": "failed",
                "failed:retry": "retrying",
                "queued:kill": "dead",
                "running:kill": "dead",
                "failed:kill": "dead",
                "retrying:kill": "dead",
            },
            # Illegal succeed-from-"queued" FIRST (must be rejected -- succeed() requires
            # "running"), then the full legal path through ONE retry cycle (start -> fail ->
            # retry -> start -> succeed, exercising the SAME start() action from both "queued"
            # AND "retrying"), then a SECOND illegal transition -- retry-from-"succeeded" (must
            # ALSO be rejected, proving the guard holds after the job has already reached its
            # terminal state, not just at construction).
            "drive": [
                {"action": "succeed", "expect": "reject"},
                {"action": "start", "expect": "accept"},
                {"action": "fail", "expect": "accept"},
                {"action": "retry", "expect": "accept"},
                {"action": "start", "expect": "accept"},
                {"action": "succeed", "expect": "accept"},
                {"action": "retry", "expect": "reject"},
            ],
            "expect_final": "succeeded",
        },
    },
)

REAL_SYSTEMS_TASKS.append(JOB_QUEUE_LIFECYCLE_TASK)
# #EXT-060-REQ-44 End


# #EXT-060-REQ-45 Start
# TASK-40: a TENTH CREATE task, in the SAME `cls="ticketing"` vertical SEAT_BOOKING_TASK (REQ-21)
# already established -- but DISTINCT from it: SEAT_BOOKING_TASK is a plain two-quantity
# reserve/release flow, while this models a THREE-quantity HOLD/confirm/release workflow (a
# temporary hold that must be explicitly confirmed into a final sale, or released back to
# inventory) -- graded by the ALREADY-LANDED "conservation" oracle_kind dispatch REQ-15 lands (no
# new oracle code: reuses `_grade_conservation` -> `harness.conservation_oracle.grade_conservation`
# verbatim). Every driven delta below was hand-verified via a scratch walk of the exact same
# available/held/sold mirror-pair bookkeeping the sentence pins (their sum always equals
# `total_seats`, the conservation invariant) before this task was added to the roster.
_SEAT_HOLD_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "seat_hold.py, using only the standard library, defining exactly one public class named "
    "`SeatHold` modeling an event's seat inventory through a HOLD/confirm/release workflow -- "
    "distinct from a plain reserve/release booking flow in that a seat passes through an "
    "intermediate TEMPORARY HOLD (e.g. while a buyer is completing checkout) before being "
    "permanently SOLD. `SeatHold(total_seats)` (exactly one positional constructor argument, a "
    "non-negative integer) creates tracking for an event whose `available` seats start at "
    "`total_seats`, whose `held` seats start at `0`, and whose `sold` seats start at `0`. It "
    "exposes three zero-argument reader methods, `available()`, `held()`, and `sold()`, each "
    "returning the current integer value of that quantity; `available() + held() + sold()` "
    "must always equal `total_seats`, since a seat is only ever MOVED between these three "
    "buckets, never created or destroyed. It defines three methods that each take one "
    "positional integer argument, `n`: `hold(n)` moves `n` seats from `available` to `held` "
    "(decreasing `available` by `n` and increasing `held` by `n`) -- but if `n` is GREATER than "
    "the CURRENT `available` count, it must instead raise `ValueError` and leave "
    "`available`/`held`/`sold` COMPLETELY UNCHANGED; `confirm(n)` moves `n` seats from `held` "
    "to `sold` (decreasing `held` by `n` and increasing `sold` by `n`) -- the buyer has "
    "completed checkout and the hold becomes a final sale -- but if `n` is GREATER than the "
    "CURRENT `held` count, it must instead raise `ValueError` and leave "
    "`available`/`held`/`sold` COMPLETELY UNCHANGED; `release(n)` moves `n` seats from `held` "
    "back to `available` (increasing `available` by `n` and decreasing `held` by `n`) -- a "
    "stale or abandoned hold is released back into inventory."
)

SEAT_HOLD_TASK = RealSystemTask(
    name="event-seat-hold-conservation",
    cls="ticketing",
    sentence=_SEAT_HOLD_SENTENCE,
    oracle_kind="conservation",
    oracle_spec={
        "module": "seat_hold",
        "entity": "SeatHold",
        "spec": {
            "quantities": ["available", "held", "sold"],
            "initial": {"available": 100, "held": 0, "sold": 0},
            "construct_args": [100],
            # Illegal over-hold FIRST (150 of 100 available -- must be rejected), then a legal
            # hold (60) and a legal partial confirm (40 of the 60 held), then a SECOND illegal
            # op -- confirming 30 when only 20 remain held (must ALSO be rejected, proving the
            # guard holds after legal ops have moved the balance too), then a legal release (10)
            # and a legal final confirm (10) landing on a concrete expect_final.
            "drive": [
                {"action": "hold", "args": [150], "expect": "reject"},
                {"action": "hold", "args": [60], "expect": "accept",
                 "deltas": {"available": -60, "held": 60}},
                {"action": "confirm", "args": [40], "expect": "accept",
                 "deltas": {"held": -40, "sold": 40}},
                {"action": "confirm", "args": [30], "expect": "reject"},
                {"action": "release", "args": [10], "expect": "accept",
                 "deltas": {"held": -10, "available": 10}},
                {"action": "confirm", "args": [10], "expect": "accept",
                 "deltas": {"held": -10, "sold": 10}},
            ],
            "expect_final": {"available": 50, "held": 0, "sold": 50},
        },
    },
)

REAL_SYSTEMS_TASKS.append(SEAT_HOLD_TASK)
# #EXT-060-REQ-45 End


# #EXT-060-REQ-46 Start
# TASK-41: an ELEVENTH CREATE task, in the SAME `cls="fintech"` double-entry vertical
# INVOICE_AR_TASK (REQ-22) already established -- but DISTINCT from it: INVOICE_AR_TASK issues
# two invoices then ONE full payment, while this models MULTIPLE PARTIAL payments applied against
# a SINGLE invoice over time until it is fully paid off -- graded by the ALREADY-LANDED
# "double_entry" oracle_kind dispatch REQ-17 lands (no new oracle code: reuses
# `_grade_double_entry` -> `harness.double_entry_oracle.grade_double_entry` verbatim, and the SAME
# `accounts_receivable`/`revenue`/`cash` three-account shape/debit-positive-credit-negative sign
# convention INVOICE_AR_TASK already uses). `expect_final` is hand-derived from the debit-
# positive/credit-negative shadow math (verified via `harness.double_entry_oracle.validate_spec`
# before this task was added to the roster): an unbalanced posting is rejected FIRST, then one
# invoice is issued, then TWO separate partial payments are posted that together exactly clear
# the invoice's outstanding `accounts_receivable` balance down to `0`.
_AR_PAYMENT_APPLICATION_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "ar_payment_application.py, using only the standard library, defining exactly one public "
    "class named `ARPaymentLedger` modeling an accounts-receivable double-entry ledger over "
    "exactly three named accounts -- `accounts_receivable`, `revenue`, and `cash` -- with a "
    "focus on applying MULTIPLE PARTIAL payments against a single invoice until it is fully "
    "paid off (distinct from a simple single-payment invoice flow). `ARPaymentLedger()` (no "
    "constructor arguments) creates a ledger where all three accounts start at a balance of `0` "
    "(an exact integer number of cents). It exposes three zero-argument reader methods, "
    "`accounts_receivable()`, `revenue()`, and `cash()`, each returning that account's CURRENT "
    "integer balance in cents. It defines exactly one method, `post(legs)`, taking one "
    "positional argument -- a list of leg dicts, each either `{\"account\": <name>, \"debit\": "
    "<cents>}` or `{\"account\": <name>, \"credit\": <cents>}`, where `<name>` is one of "
    "`accounts_receivable`/`revenue`/`cash` and `<cents>` is a positive integer. Posting a leg "
    "to an account with `debit` ADDS that many cents to the account's balance; posting a leg "
    "with `credit` SUBTRACTS that many cents from the account's balance. Issuing an invoice is "
    "recorded by posting legs that DEBIT `accounts_receivable` and CREDIT `revenue` for the "
    "same amount. Receiving a PARTIAL payment against an outstanding invoice is recorded by "
    "posting legs that DEBIT `cash` and CREDIT `accounts_receivable` for the amount actually "
    "received (which may be less than the full invoice amount) -- a caller may post several "
    "such partial-payment entries over time, one per payment received, until the invoice's "
    "`accounts_receivable` balance is fully paid down to zero. If the legs in one call to "
    "`post(legs)` are BALANCED (the sum of every `debit` amount in the list equals the sum of "
    "every `credit` amount in the list), `post(legs)` must apply EVERY leg to its account's "
    "balance and return normally. If the legs are UNBALANCED (the sum of the `debit` amounts "
    "does not equal the sum of the `credit` amounts), `post(legs)` must instead raise "
    "`ValueError` and leave EVERY account's balance COMPLETELY UNCHANGED -- no partial posting "
    "of any leg from an unbalanced call."
)

INVOICE_AR_AGING_TASK = RealSystemTask(
    name="accounts-receivable-payment-application-ledger",
    cls="fintech",
    sentence=_AR_PAYMENT_APPLICATION_SENTENCE,
    oracle_kind="double_entry",
    oracle_spec={
        "module": "ar_payment_application",
        "entity": "ARPaymentLedger",
        "spec": {
            "accounts": ["accounts_receivable", "revenue", "cash"],
            "initial": {"accounts_receivable": 0, "revenue": 0, "cash": 0},
            "post_method": "post",
            # Unbalanced entry FIRST (debit accounts_receivable 100000, credit revenue 90000 --
            # off by 10000 cents, must be rejected), then one balanced $1000.00 invoice posting
            # (debit accounts_receivable / credit revenue), then TWO balanced partial-payment
            # postings ($400.00 then $600.00, each debiting cash / crediting
            # accounts_receivable) that together exactly clear the invoice -- landing on
            # accounts_receivable=0 (fully applied), revenue=-100000, cash=100000.
            "drive": [
                {"legs": [{"account": "accounts_receivable", "debit": 100000},
                          {"account": "revenue", "credit": 90000}],
                 "expect": "reject"},
                {"legs": [{"account": "accounts_receivable", "debit": 100000},
                          {"account": "revenue", "credit": 100000}],
                 "expect": "accept"},
                {"legs": [{"account": "cash", "debit": 40000},
                          {"account": "accounts_receivable", "credit": 40000}],
                 "expect": "accept"},
                {"legs": [{"account": "cash", "debit": 60000},
                          {"account": "accounts_receivable", "credit": 60000}],
                 "expect": "accept"},
            ],
            "expect_final": {"accounts_receivable": 0, "revenue": -100000, "cash": 100000},
        },
    },
)

REAL_SYSTEMS_TASKS.append(INVOICE_AR_AGING_TASK)
# #EXT-060-REQ-46 End


# #EXT-060-REQ-47 Start
# TASK-42: a TWELFTH CREATE task, in a NEW validation-library vertical -- a check-digit
# identifier validator -- graded by the ALREADY-LANDED "import" oracle_kind dispatch REQ-3 lands
# (no new oracle code: reuses `_grade_import` -> `harness.import_driver.drive_import` verbatim).
# Every expected boolean below was hand-verified via scratch Luhn/EAN-13 checksum arithmetic
# against real published test vectors (Luhn: 4539148803436467 is a well-known valid test credit-
# card number; ISBN-13 9780306406157 and EAN-13 4006381333931 are the canonical valid examples
# from the ISBN-13/EAN-13 Wikipedia articles) before this task was added to the roster.
_CHECK_DIGIT_SENTENCE = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named "
    "check_digits.py, using only the standard library, defining exactly three public functions "
    "that each validate one kind of numeric identifier by its CHECK DIGIT and return a plain "
    "Python `bool`. Every argument is a Python `str` of ONLY decimal digit characters (never "
    "converted to `int` internally in a way that would drop leading zeros); an argument "
    "containing any non-digit character, or of the wrong length for that function, must make "
    "the function return `False` (never raise). (1) `luhn_valid(number)` validates `number` "
    "(any length of 2 or more digits, e.g. a credit-card number) using the standard Luhn "
    "checksum algorithm: starting from the RIGHTMOST digit (the check digit itself, NOT "
    "doubled) and moving left, double the value of every SECOND digit (the digits at position "
    "2, 4, 6, ... counting from the right); whenever doubling a digit produces a value greater "
    "than 9, replace it with the sum of ITS two digits (equivalently, subtract 9); sum EVERY "
    "digit of the number (the untouched odd-position digits plus the possibly-replaced "
    "even-position digits); `number` is valid when that total sum is evenly divisible by 10. "
    "(2) `isbn13_valid(s)` and (3) `ean13_valid(s)` each validate a 13-digit identifier (`s` "
    "must be EXACTLY 13 digit characters, else return `False`) using the IDENTICAL EAN-13 "
    "weighted checksum algorithm (a real ISBN-13 code IS a valid EAN-13 barcode number, so both "
    "functions apply the same formula here, with no extra prefix restriction in this "
    "simplified library): number the 13 digits left-to-right as positions 1 through 13; "
    "multiply each digit at an ODD position (1, 3, 5, 7, 9, 11, 13) by weight `1` and each "
    "digit at an EVEN position (2, 4, 6, 8, 10, 12) by weight `3`; sum all 13 weighted values "
    "(the 13th digit, the check digit itself, is included in the sum at weight `1` just like "
    "every other odd position); the identifier is valid when that total weighted sum is evenly "
    "divisible by 10."
)

CHECK_DIGIT_TASK = RealSystemTask(
    name="check-digit-validator-lib",
    cls="validation",
    sentence=_CHECK_DIGIT_SENTENCE,
    oracle_kind="import",
    oracle_spec={
        "module": "check_digits",
        "api_calls": [
            # Luhn: 4539148803436467 is a well-known VALID test credit-card number (sum of
            # digits after doubling every second digit from the right == 80, divisible by 10).
            {"id": "luhn_good", "target": "luhn_valid",
             "args": ["4539148803436467"], "kwargs": {}},
            # Luhn: 1234567890123456 is INVALID (the same checksum walk sums to 64, NOT
            # divisible by 10).
            {"id": "luhn_bad", "target": "luhn_valid",
             "args": ["1234567890123456"], "kwargs": {}},
            # ISBN-13: 9780306406157 is a well-known VALID ISBN-13 (weighted 1/3 checksum sums
            # to 100, divisible by 10).
            {"id": "isbn13_good", "target": "isbn13_valid",
             "args": ["9780306406157"], "kwargs": {}},
            # ISBN-13: 9780306406158 (the valid one with its check digit incremented by 1) is
            # INVALID (weighted sum becomes 101, NOT divisible by 10).
            {"id": "isbn13_bad", "target": "isbn13_valid",
             "args": ["9780306406158"], "kwargs": {}},
            # EAN-13: 4006381333931 is the canonical VALID EAN-13 example (weighted 1/3 checksum
            # sums to 90, divisible by 10).
            {"id": "ean13_good", "target": "ean13_valid",
             "args": ["4006381333931"], "kwargs": {}},
            # EAN-13: 4006381333932 (the valid one with its check digit incremented by 1) is
            # INVALID (weighted sum becomes 91, NOT divisible by 10).
            {"id": "ean13_bad", "target": "ean13_valid",
             "args": ["4006381333932"], "kwargs": {}},
        ],
        "checks": [
            {"kind": "returns_equals", "call_id": "luhn_good", "expected": True},
            {"kind": "returns_equals", "call_id": "luhn_bad", "expected": False},
            {"kind": "returns_equals", "call_id": "isbn13_good", "expected": True},
            {"kind": "returns_equals", "call_id": "isbn13_bad", "expected": False},
            {"kind": "returns_equals", "call_id": "ean13_good", "expected": True},
            {"kind": "returns_equals", "call_id": "ean13_bad", "expected": False},
        ],
        "timeout": IMPORT_DEFAULT_TIMEOUT_S,
    },
)

REAL_SYSTEMS_TASKS.append(CHECK_DIGIT_TASK)
# #EXT-060-REQ-47 End
