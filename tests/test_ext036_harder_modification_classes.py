"""EXT-036 TASK-51: HARDER_SLICE -- a genuinely-hard modification tier (REQ-21 ratchet).

OFFLINE -- no live model, no network beyond 127.0.0.1-free subprocess execution of the
generated Python programs themselves (via ``harness.system_suite._run_single_check`` /
``run_sandboxed``, the SAME oracle mechanism ``run_modification_suite`` uses in production).

MEASURED (docs/GAP-MAP.md, 2026-07-08): ``FIRST_SLICE`` + ``MULTIFILE_SLICE`` are ~35/36
saturated -- gemma aces nearly every task including the multi-file tier, so the suite no longer
DISCRIMINATES (PRIME-001's difficulty ratchet). ``HARDER_SLICE`` (``harness/modification_suite.py``)
instead starts each task from a COMPLEX, already-non-trivial ``start_system`` (a real infix
expression evaluator, an in-memory SQL-like engine, a JSON-path resolver, a multi-file stats CLI)
and requires a precise EXTENSION of intricate existing logic.

This file proves the HARDER_SLICE fixtures are HONEST (Tenet 3), exactly mirroring the rigor
already applied to FIRST_SLICE/MULTIFILE_SLICE in ``tests/test_ext036_modsuite.py``:
  (a) each ``start_system`` is KNOWN-GOOD -- it already passes its own ``regression_checks``
      BEFORE any modification is attempted;
  (b) a hand-written, genuinely-correct REFERENCE MODIFICATION for each task, driven through the
      REAL ``run_modification_suite`` oracle, satisfies BOTH ``new_checks`` AND
      ``regression_checks`` (``accepted=True``) -- proving the checks are actually satisfiable by
      (and thus genuinely determined by) the stated ``mod_sentence``;
  (c) a NO-OP ``modify_fn`` (never touches ``root`` -- the start_system stands unmodified) FAILS
      every task's ``new_checks`` -- proving the checks genuinely test the requested change and
      are not trivially/accidentally satisfiable by the pre-modification system (no leak).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from harness.modification_suite import HARDER_SLICE, run_modification_suite
from harness.system_suite import _run_single_check

# --- hand-written, genuinely-correct REFERENCE MODIFICATIONS (the start_system with the
# requested change applied), one per HARDER_SLICE task -----------------------------------------

_INFIX_EVAL_WITH_MODULO = (
    "import sys\n"
    "\n"
    "\n"
    "def _parse_expr(tokens, pos):\n"
    "    value, pos = _parse_term(tokens, pos)\n"
    "    while pos < len(tokens) and tokens[pos] in (\"+\", \"-\"):\n"
    "        op = tokens[pos]\n"
    "        pos += 1\n"
    "        rhs, pos = _parse_term(tokens, pos)\n"
    "        value = value + rhs if op == \"+\" else value - rhs\n"
    "    return value, pos\n"
    "\n"
    "\n"
    "def _parse_term(tokens, pos):\n"
    "    value, pos = _parse_factor(tokens, pos)\n"
    "    while pos < len(tokens) and tokens[pos] in (\"*\", \"/\", \"%\"):\n"
    "        op = tokens[pos]\n"
    "        pos += 1\n"
    "        rhs, pos = _parse_factor(tokens, pos)\n"
    "        if op == \"*\":\n"
    "            value = value * rhs\n"
    "        elif op == \"/\":\n"
    "            value = int(value / rhs)\n"
    "        else:\n"
    "            value = value % rhs\n"
    "    return value, pos\n"
    "\n"
    "\n"
    "def _parse_factor(tokens, pos):\n"
    "    tok = tokens[pos]\n"
    "    if tok == \"(\":\n"
    "        value, pos = _parse_expr(tokens, pos + 1)\n"
    "        return value, pos + 1\n"
    "    return int(tok), pos + 1\n"
    "\n"
    "\n"
    "def evaluate(line):\n"
    "    tokens = line.split()\n"
    "    value, _ = _parse_expr(tokens, 0)\n"
    "    return value\n"
    "\n"
    "\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    print(evaluate(line))\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_SQL_MINI_WITH_PROJECTION = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    tables = {}\n"
    "    for line in sys.stdin:\n"
    "        line = line.rstrip(\"\\n\")\n"
    "        if not line:\n"
    "            continue\n"
    "        if line.startswith(\"CREATE TABLE \"):\n"
    "            rest = line[len(\"CREATE TABLE \"):]\n"
    "            name, cols_part = rest.split(\" (\", 1)\n"
    "            cols = cols_part.rstrip(\")\").split(\",\")\n"
    "            tables[name] = {\"columns\": cols, \"rows\": []}\n"
    "            print(\"ok\")\n"
    "        elif line.startswith(\"INSERT INTO \"):\n"
    "            rest = line[len(\"INSERT INTO \"):]\n"
    "            name, values_part = rest.split(\" VALUES (\", 1)\n"
    "            values = values_part.rstrip(\")\").split(\",\")\n"
    "            tables[name][\"rows\"].append(values)\n"
    "            print(\"ok\")\n"
    "        elif line.startswith(\"SELECT * FROM \"):\n"
    "            rest = line[len(\"SELECT * FROM \"):]\n"
    "            name, cond = rest.split(\" WHERE \", 1)\n"
    "            col, val = cond.split(\"=\", 1)\n"
    "            table = tables[name]\n"
    "            idx = table[\"columns\"].index(col)\n"
    "            for row in table[\"rows\"]:\n"
    "                if row[idx] == val:\n"
    "                    print(\",\".join(row))\n"
    "        elif line.startswith(\"SELECT \") and \" FROM \" in line:\n"
    "            rest = line[len(\"SELECT \"):]\n"
    "            col_part, rest2 = rest.split(\" FROM \", 1)\n"
    "            name, cond = rest2.split(\" WHERE \", 1)\n"
    "            cond_col, val = cond.split(\"=\", 1)\n"
    "            table = tables[name]\n"
    "            cond_idx = table[\"columns\"].index(cond_col)\n"
    "            proj_idx = table[\"columns\"].index(col_part)\n"
    "            for row in table[\"rows\"]:\n"
    "                if row[cond_idx] == val:\n"
    "                    print(row[proj_idx])\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_JSONPATH_WITH_NEGATIVE_INDEX = (
    "import sys\n"
    "import json\n"
    "\n"
    "\n"
    "def resolve(value, path):\n"
    "    if not path:\n"
    "        return value, True\n"
    "    current = value\n"
    "    for part in path.split(\".\"):\n"
    "        if isinstance(current, dict):\n"
    "            if part not in current:\n"
    "                return None, False\n"
    "            current = current[part]\n"
    "        elif isinstance(current, list):\n"
    "            if not part.lstrip(\"-\").isdigit():\n"
    "                return None, False\n"
    "            idx = int(part)\n"
    "            if idx < 0:\n"
    "                idx = idx + len(current)\n"
    "            if idx < 0 or idx >= len(current):\n"
    "                return None, False\n"
    "            current = current[idx]\n"
    "        else:\n"
    "            return None, False\n"
    "    return current, True\n"
    "\n"
    "\n"
    "def main():\n"
    "    path = sys.argv[1]\n"
    "    try:\n"
    "        doc = json.loads(sys.stdin.read())\n"
    "    except Exception:\n"
    "        print(\"null\")\n"
    "        return\n"
    "    value, ok = resolve(doc, path)\n"
    "    if ok:\n"
    "        print(json.dumps(value))\n"
    "    else:\n"
    "        print(\"null\")\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

_STATLIB_WITH_MODE = (
    "\"\"\"Small stats helpers.\"\"\"\n"
    "\n"
    "\n"
    "def mean(nums):\n"
    "    return sum(nums) / len(nums) if nums else 0\n"
    "\n"
    "\n"
    "def median(nums):\n"
    "    s = sorted(nums)\n"
    "    n = len(s)\n"
    "    if n == 0:\n"
    "        return 0\n"
    "    mid = n // 2\n"
    "    if n % 2 == 1:\n"
    "        return s[mid]\n"
    "    return (s[mid - 1] + s[mid]) / 2\n"
    "\n"
    "\n"
    "def mode(nums):\n"
    "    counts = {}\n"
    "    for n in nums:\n"
    "        counts[n] = counts.get(n, 0) + 1\n"
    "    best = None\n"
    "    best_count = -1\n"
    "    for n in sorted(counts):\n"
    "        c = counts[n]\n"
    "        if c > best_count:\n"
    "            best = n\n"
    "            best_count = c\n"
    "    return best\n"
)

_STATS_MODE_MAIN_WIRED = (
    "import sys\n"
    "from statlib import mean, median, mode\n"
    "\n"
    "\n"
    "def main():\n"
    "    args = sys.argv[1:]\n"
    "    nums = [int(x) for x in sys.stdin.readline().split()]\n"
    "    if args and args[0] == \"median\":\n"
    "        print(median(nums))\n"
    "    elif args and args[0] == \"mode\":\n"
    "        print(mode(nums))\n"
    "    else:\n"
    "        print(mean(nums))\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)


def _correct_infix_modulo_modify_fn(modules, mod_sentence, root):
    (Path(root) / "main.py").write_text(_INFIX_EVAL_WITH_MODULO, encoding="utf-8")
    return {"modules": {"main.py": _INFIX_EVAL_WITH_MODULO}, "applied": True}


def _correct_sql_projection_modify_fn(modules, mod_sentence, root):
    (Path(root) / "main.py").write_text(_SQL_MINI_WITH_PROJECTION, encoding="utf-8")
    return {"modules": {"main.py": _SQL_MINI_WITH_PROJECTION}, "applied": True}


def _correct_jsonpath_negative_index_modify_fn(modules, mod_sentence, root):
    (Path(root) / "main.py").write_text(_JSONPATH_WITH_NEGATIVE_INDEX, encoding="utf-8")
    return {"modules": {"main.py": _JSONPATH_WITH_NEGATIVE_INDEX}, "applied": True}


def _correct_stats_mode_modify_fn(modules, mod_sentence, root):
    root = Path(root)
    (root / "statlib.py").write_text(_STATLIB_WITH_MODE, encoding="utf-8")
    (root / "main.py").write_text(_STATS_MODE_MAIN_WIRED, encoding="utf-8")
    return {"modules": {"statlib.py": _STATLIB_WITH_MODE, "main.py": _STATS_MODE_MAIN_WIRED},
            "applied": True}


_CORRECT_MODIFY_FN_BY_NAME = {
    "infix-eval-add-modulo": _correct_infix_modulo_modify_fn,
    "sql-mini-add-projection": _correct_sql_projection_modify_fn,
    "jsonpath-add-negative-index": _correct_jsonpath_negative_index_modify_fn,
    "stats-add-mode-subcmd": _correct_stats_mode_modify_fn,
}


def _no_op_modify_fn(modules, mod_sentence, root):
    """Never touches ``root`` -- the ``start_system`` stands completely unmodified. Proves
    ``new_checks`` are not trivially/accidentally satisfiable by the pre-modification system
    (no leak, Tenet 3)."""
    return {"modules": dict(modules), "applied": False, "note": "no-op"}


# --- (a) structural shape --------------------------------------------------------------------

def test_harder_slice_registry_shape():
    assert len(HARDER_SLICE) == 4
    names = [t.name for t in HARDER_SLICE]
    assert len(names) == len(set(names))   # unique names
    for task in HARDER_SLICE:
        assert task.tier == "highly-complex"
        assert task.cls and isinstance(task.cls, str)
        assert task.mod_sentence.strip()
        assert task.start_system and "main.py" in task.start_system
        assert 'if __name__ == "__main__"' in task.start_system["main.py"]
        assert task.new_checks       # at least one deterministic new-behavior check
        assert task.regression_checks   # at least one deterministic regression check
        for check in task.new_checks + task.regression_checks:
            assert len(check) == 3


# --- (b) TENET-3 PRECONDITION: every start_system is KNOWN-GOOD BEFORE any modification -------

def test_harder_slice_start_systems_pass_their_own_regression_checks_unmodified():
    python_exe = sys.executable or "python"
    for task in HARDER_SLICE:
        with tempfile.TemporaryDirectory(prefix="s2s_modsuite_harder_coherence_") as tmp:
            root = Path(tmp)
            for fname, code in task.start_system.items():
                (root / fname).write_text(code, encoding="utf-8", newline="\n")
            for check in task.regression_checks:
                assert _run_single_check(check, root, None, python_exe), (
                    f"{task.name}: unmodified start_system failed regression check {check}"
                )


# --- (c) THE HONESTY CORE: a genuinely-correct reference modification satisfies BOTH
# new_checks AND regression_checks, driven through the REAL run_modification_suite oracle -------

def test_harder_slice_tasks_are_internally_coherent_reference_modification_accepted():
    for task in HARDER_SLICE:
        modify_fn = _CORRECT_MODIFY_FN_BY_NAME[task.name]
        result = run_modification_suite(modify_fn, tasks=[task])
        rec = result["results"][0]
        assert rec["applied"] is True, f"{task.name}: {rec}"
        assert rec["new_behavior_ok"] is True, f"{task.name}: {rec}"
        assert rec["no_regression"] is True, f"{task.name}: {rec}"
        assert rec["accepted"] is True, f"{task.name}: {rec}"


# --- (d) NO LEAK: a no-op modification (start_system left unchanged) must FAIL new_checks
# for EVERY task -- proving the checks genuinely test the requested change ---------------------

def test_harder_slice_no_op_modification_fails_new_checks_no_leak():
    result = run_modification_suite(_no_op_modify_fn, tasks=HARDER_SLICE)
    assert len(result["results"]) == len(HARDER_SLICE)
    for rec in result["results"]:
        assert rec["applied"] is False, rec
        assert rec["new_behavior_ok"] is False, rec
        assert rec["accepted"] is False, rec
