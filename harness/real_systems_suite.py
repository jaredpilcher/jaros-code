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


@dataclass
class RealSystemTask:
    """One held-out sentence->system REAL-systems task. ``oracle_kind`` selects the grading
    dispatch (``"fs"`` -> ``harness.fs_oracle``, ``"cli-exact"`` -> the exact-stdout check variant
    reused from ``harness.system_suite``); ``oracle_spec`` is a plain declarative dict whose shape
    depends on ``oracle_kind`` (see :func:`grade_real_system_task`). Kept intentionally simple and
    fully declarative -- no check here is ever a live callable closing over test-internal state, so
    a task can be inspected/serialized/logged without executing anything."""

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

REAL_SYSTEMS_TASKS: "list[RealSystemTask]" = [CSV_GROUPBY_ETL_TASK]
# #EXT-060-REQ-2 End
