"""EXT-058 TASK-9: offline (no model call) tests for the leaf-as-differential-oracle mechanism
(REQ-6) that closes a MEASURED false-done in ``harness.system_builder.build_system``'s leaf-repair
block.

MEASURED BUG (on-Jetson, 2/2 samples, 2026-07-08): for ``sql-mini-query-cli``, ``build_system``
ships gemma's free-form build and reports ``done=True`` even though the INDEPENDENT task oracle
scores 0/3 (a false-done). The existing leaf-repair adopt block only fired when the build was
``not done``, so the verified ``sql-query-engine`` leaf (committed, passes 3/3 in isolation) never
fired and the class stayed broken -- the deterministic-minimum + ADT-oracle acceptance floor
doesn't cover the stdin-line SQL protocol (``select`` is not one of ``_MINIMUM_COMMAND_VERBS`` and
the class has no ADT reference model), so ``done`` rode on a build that never crashes but silently
mis-implements ``SELECT``.

FIX under test: a verified leaf is a spec-faithful reference, so it doubles as a DIFFERENTIAL
ORACLE for its own class -- run the shipped free-form build and the leaf on the SAME deterministic
seeded stdin (``graph_dsl.seeded_driver_input``) and compare stdout; a divergence (or a free-form
run error) triggers the SAME ship-clean adopt path EVEN WHEN the free-form build already reports
``done=True``.

Covers TASK-9's required cases:
  1. A stub free-form build that DIVERGES from the leaf on the seeded input (botches SELECT,
     ignoring the WHERE clause) -- the leaf-repair adopt fires and the shipped system is the leaf
     (``build_path == "leaf:sql-query-engine"``), even though the deterministic-minimum floor
     alone already reported ``done=True`` for the free-form build.
  2. A stub free-form build that MATCHES the leaf on the seeded input -- NOT adopted, the
     free-form build is kept unchanged (``build_path == "free-form"``).
  3. Over-trigger guard: a non-leaf-class spec (a plain calculator CLI) never runs the
     differential and never adopts a leaf (``leaf_for_spec`` returns ``None``).
  4. Honesty: the differential uses only the spec-derived leaf's own seeded input, never any
     task's hidden ``checks`` -- proven both by source inspection (the new functions never
     reference the task registry) and functionally (a differential-triggered adopt still succeeds
     even with ``harness.system_suite`` poisoned/unimportable during the call).

Entirely offline and deterministic: no ``llm``/model call anywhere in this file (every ``llm`` is
a canned stub), no on-Jetson build.
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness import graph_dsl
from harness import system_builder
from harness.system_builder import build_system
from harness.system_suite import FIRST_SLICE, HARDER_SLICE, _run_single_check

PY = sys.executable

# #EXT-058-REQ-6 Start

# --- fixtures ------------------------------------------------------------------------------


def _sql_task():
    return next(t for t in list(FIRST_SLICE) + list(HARDER_SLICE) if t.name == "sql-mini-query-cli")


# The REAL, held-out `sql-mini-query-cli` sentence (already independently proven by
# `tests/test_ext058_sql_leaf.py` to fingerprint `leaf_for_spec` -> "sql-query-engine") -- no
# self-authored variant needed here.
SQL_SPEC = _sql_task().sentence

_SQL_PLAN_JSON = """{
  "modules": [
    {"name": "main.py", "responsibility": "mini SQL query engine CLI",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "SQL-like query engine semantics"
}"""

# A free-form build that never crashes and clears the deterministic-minimum floor (`select` is
# not a MINIMUM command verb, and this spec names no LIST-like word so no round-trip check is
# derived either) -- but silently ignores the WHERE clause entirely, always printing EVERY row
# for any SELECT. This is the exact MEASURED false-done shape: 0/3 on the real, independent task
# oracle while the deterministic-minimum floor alone already reports `done=True`.
_DIVERGENT_SQL_CLI = '''\
import sys


def main():
    tables = {}
    for line in sys.stdin:
        line = line.rstrip("\\n")
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
            # BUG: ignores the WHERE clause entirely -- always prints every row currently in
            # the table, regardless of whether it actually matches.
            for row in tables[name]["rows"]:
                print(",".join(row))


if __name__ == "__main__":
    main()
'''


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _SqlDiffLlm:
    """Canned `llm` (`.complete(LlmRequest) -> .text`) for the differential scenarios: always
    plans the same single-module SQL CLI, proposes an EMPTY acceptance checklist (so the composed
    checklist is exactly the deterministic minimum -- no extra model-proposed check could
    accidentally catch the SELECT bug), and builds whichever module body `module_code` says."""

    def __init__(self, module_code: str) -> None:
        self.module_code = module_code

    def complete(self, request):
        prompt = request.prompt
        if "build PLAN" in prompt:
            return _Resp(_SQL_PLAN_JSON)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")
        if "COMPLETE Python module" in prompt:
            return _Resp(self.module_code)
        return _Resp("")


# --- (1) a free-form build that DIVERGES from the leaf is adopted, even when done=True already --

def test_divergent_free_form_build_is_adopted_even_when_minimum_floor_reports_done():
    llm = _SqlDiffLlm(_DIVERGENT_SQL_CLI)
    with tempfile.TemporaryDirectory(prefix="ext058_diff_divergent_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(SQL_SPEC, root, llm=llm)

        assert result["done"] is True
        assert result["unmet"] == []
        assert result.get("build_path") == "leaf:sql-query-engine"
        assert result["modules"] == {"main.py": graph_dsl.SQL_MINI_LEAF}

        # (mirrors TASK-7's ship-clean guarantee) root SHIPS EXACTLY the leaf, plan points at it.
        assert sorted(p.name for p in root.glob("*.py")) == ["main.py"]
        assert (root / "main.py").read_text(encoding="utf-8") == graph_dsl.SQL_MINI_LEAF
        assert result["plan"]["entrypoint"] == "main.py"

        # passes the REAL, independent sql-mini-query-cli task oracle too (no reimplemented
        # grading logic), against the SHIPPED root -- the class this session measured 0/3 for
        # gemma's free-form output now genuinely ships a working system.
        task = _sql_task()
        results = [_run_single_check(c, root, result.get("plan"), PY) for c in task.checks]
        assert all(results), results


# --- (2) a free-form build that MATCHES the leaf on the seeded input is left unchanged ----------

def test_matching_free_form_build_is_kept_unchanged():
    free_form_code = graph_dsl.SQL_MINI_LEAF
    llm = _SqlDiffLlm(free_form_code)
    with tempfile.TemporaryDirectory(prefix="ext058_diff_match_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(SQL_SPEC, root, llm=llm)

        assert result["done"] is True
        assert result["unmet"] == []
        assert result.get("build_path") == "free-form"
        assert result["modules"]["main.py"].strip() == free_form_code.strip()


# --- (3) over-trigger guard: a non-leaf-class spec never runs the differential -------------------

def test_non_leaf_spec_never_triggers_differential():
    plan = '''{
  "modules": [
    {"name": "main.py", "responsibility": "calculator CLI",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "sum semantics"
}'''
    calc_cli = '''\
import sys


def main():
    if len(sys.argv) == 3:
        print(int(sys.argv[1]) + int(sys.argv[2]))


if __name__ == "__main__":
    main()
'''

    class _CalcLlm:
        def complete(self, request):
            prompt = request.prompt
            if "build PLAN" in prompt:
                return _Resp(plan)
            if "ACCEPTANCE CHECKS" in prompt:
                return _Resp("[]")
            if "COMPLETE Python module" in prompt:
                return _Resp(calc_cli)
            return _Resp("")

    spec = ("Write a single-file Python CLI program named main.py: `python main.py <a> <b>` "
            "prints the sum of the two integer command-line arguments.")
    assert graph_dsl.leaf_for_spec(spec) is None

    with tempfile.TemporaryDirectory(prefix="ext058_diff_nonleaf_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(spec, root, llm=_CalcLlm())
        assert result.get("build_path") == "free-form"
        assert result["done"] is True


# --- (4) Honesty: the differential uses only the spec-derived leaf, never task.checks -----------

def test_differential_source_never_references_task_registry_or_checks():
    """Source-level proof: none of the new differential functions reference `harness.system_suite`
    (the task registry module) or its `CreationTask`/`FIRST_SLICE`/`HARDER_SLICE` symbols -- the
    only input to the differential is `graph_dsl.seeded_driver_input`'s own, spec-derived seeded
    stdin, authored from the leaf's VISIBLE contract."""
    for fn in (graph_dsl.seeded_driver_input, system_builder._leaf_differential_diverges,
               system_builder._run_with_stdin):
        src = inspect.getsource(fn)
        for forbidden in ("system_suite", "FIRST_SLICE", "HARDER_SLICE", "CreationTask"):
            assert forbidden not in src, f"{fn.__name__} unexpectedly references {forbidden!r}"


def test_differential_adopt_never_imports_system_suite_at_runtime(monkeypatch):
    """Functional honesty proof: poison `harness.system_suite` in `sys.modules` (any fresh
    `import harness.system_suite` raises ImportError, per Python's documented `sys.modules[name]
    = None` behavior) for the duration of a differential-triggered leaf adopt. If the
    differential/adopt path ever consulted the task registry or a task's hidden `checks`, this
    build would silently fail to adopt (the surrounding `except Exception: pass` would swallow
    the ImportError and leave `build_path == "free-form"`); it doesn't -- the leaf is still
    adopted, proving the path never touches `harness.system_suite`."""
    monkeypatch.setitem(sys.modules, "harness.system_suite", None)
    llm = _SqlDiffLlm(_DIVERGENT_SQL_CLI)
    with tempfile.TemporaryDirectory(prefix="ext058_diff_honesty_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(SQL_SPEC, root, llm=llm)
        assert result["done"] is True
        assert result.get("build_path") == "leaf:sql-query-engine"
# #EXT-058-REQ-6 End
