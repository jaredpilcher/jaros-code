"""EXT-036 TASK-50: Ratchet the creation-suite frontier -- 4 real-system HARDER_SLICE classes
(REQ-20).

MEASURED (docs/GAP-MAP.md, 2026-07-08): the toy-CLI tier is ~92% mastered (all 20
``ALL_CREATION_TASKS`` classes buildable), so it no longer discriminates. This task adds 4 MORE
``"highly-complex"`` classes to ``harness.system_suite.HARDER_SLICE`` drawn from the real-systems
frontier (PRIME-001's reframe: build REAL systems -- real persistence, real parsing, real state
-- not just harder toy logic): a SQLite-backed persistent key-value store (genuine cross-process
persistence), a minimal in-memory SQL-like query engine (CREATE TABLE / INSERT / SELECT WHERE), an
infix arithmetic expression evaluator with operator precedence + parentheses (a real parser, not
RPN), and a nested-JSON dotted-path query tool.

OFFLINE ONLY -- no live model, no network. This file does not call ``harness.system_builder`` or
any model; it validates:

1. STRUCTURE: each of the 4 new tasks has a non-empty, contract-precise sentence and 3+
   well-formed checks.
2. SATISFIABILITY (Tenet 3, no oracle leak): a hand-written, genuinely-correct reference
   implementation of EACH new task's OWN stated contract is run through the REAL
   ``run_creation_suite`` independent black-box CLI oracle and is ``accepted=True`` -- proving
   every check is actually determined by the sentence's declared contract (not trivially-always-
   true, not accidentally unsatisfiable), never by peeking at any implementation detail.
"""

from __future__ import annotations

from harness.system_suite import HARDER_SLICE, run_creation_suite

NEW_TASK_NAMES = {
    "sqlite-persistent-kv-cli",
    "sql-mini-query-cli",
    "infix-expr-eval-cli",
    "json-path-query-cli",
}


def _new_tasks():
    tasks = [t for t in HARDER_SLICE if t.name in NEW_TASK_NAMES]
    assert len(tasks) == 4, f"expected 4 new tasks in HARDER_SLICE, found {len(tasks)}"
    return tasks


# --- (1) structure -------------------------------------------------------------------------

def test_new_tasks_present_and_highly_complex():
    tasks = _new_tasks()
    names = {t.name for t in tasks}
    assert names == NEW_TASK_NAMES
    for task in tasks:
        assert task.tier == "highly-complex"
        assert task.cls and isinstance(task.cls, str)


def test_new_tasks_have_contract_precise_sentences():
    for task in _new_tasks():
        assert task.sentence.strip()
        assert "main.py" in task.sentence
        assert '__name__ == "__main__"' in task.sentence


def test_new_tasks_have_at_least_three_well_formed_checks():
    for task in _new_tasks():
        assert len(task.checks) >= 3, f"{task.name}: only {len(task.checks)} checks"
        for check in task.checks:
            assert callable(check) or len(check) == 3


def test_new_task_names_disjoint_from_rest_of_suite():
    other_names = {t.name for t in HARDER_SLICE if t.name not in NEW_TASK_NAMES}
    assert NEW_TASK_NAMES.isdisjoint(other_names)


# --- (2) satisfiability: a hand-written correct reference impl for EACH new task -----------

_SQLITE_KV_CODE = (
    "import sys\n"
    "import sqlite3\n"
    "def main():\n"
    "    conn = sqlite3.connect('store.db')\n"
    "    conn.execute('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)')\n"
    "    conn.commit()\n"
    "    cmd = sys.argv[1]\n"
    "    if cmd == 'set':\n"
    "        key, value = sys.argv[2], sys.argv[3]\n"
    "        conn.execute('INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)', (key, value))\n"
    "        conn.commit()\n"
    "        print('ok')\n"
    "    elif cmd == 'get':\n"
    "        key = sys.argv[2]\n"
    "        row = conn.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()\n"
    "        print(row[0] if row else 'none')\n"
    "    conn.close()\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_SQL_MINI_QUERY_CODE = (
    "import sys\n"
    "def main():\n"
    "    tables = {}\n"
    "    for line in sys.stdin:\n"
    "        line = line.rstrip('\\n')\n"
    "        if not line:\n"
    "            continue\n"
    "        if line.startswith('CREATE TABLE'):\n"
    "            rest = line[len('CREATE TABLE '):]\n"
    "            name, cols_part = rest.split(' (', 1)\n"
    "            cols = cols_part.rstrip(')').split(',')\n"
    "            tables[name] = {'cols': cols, 'rows': []}\n"
    "            print('ok')\n"
    "        elif line.startswith('INSERT INTO'):\n"
    "            rest = line[len('INSERT INTO '):]\n"
    "            name, vals_part = rest.split(' VALUES (', 1)\n"
    "            vals = vals_part.rstrip(')').split(',')\n"
    "            tables[name]['rows'].append(vals)\n"
    "            print('ok')\n"
    "        elif line.startswith('SELECT * FROM'):\n"
    "            rest = line[len('SELECT * FROM '):]\n"
    "            name, where_part = rest.split(' WHERE ', 1)\n"
    "            col, val = where_part.split('=', 1)\n"
    "            table = tables[name]\n"
    "            col_idx = table['cols'].index(col)\n"
    "            for row in table['rows']:\n"
    "                if row[col_idx] == val:\n"
    "                    print(','.join(row))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_INFIX_EVAL_CODE = (
    "import sys\n"
    "PREC = {'+': 1, '-': 1, '*': 2, '/': 2}\n"
    "def to_rpn(tokens):\n"
    "    output, ops = [], []\n"
    "    for tok in tokens:\n"
    "        if tok == '(':\n"
    "            ops.append(tok)\n"
    "        elif tok == ')':\n"
    "            while ops[-1] != '(':\n"
    "                output.append(ops.pop())\n"
    "            ops.pop()\n"
    "        elif tok in PREC:\n"
    "            while ops and ops[-1] != '(' and PREC[ops[-1]] >= PREC[tok]:\n"
    "                output.append(ops.pop())\n"
    "            ops.append(tok)\n"
    "        else:\n"
    "            output.append(tok)\n"
    "    while ops:\n"
    "        output.append(ops.pop())\n"
    "    return output\n"
    "def eval_rpn(rpn):\n"
    "    stack = []\n"
    "    for tok in rpn:\n"
    "        if tok in PREC:\n"
    "            b = stack.pop()\n"
    "            a = stack.pop()\n"
    "            if tok == '+':\n"
    "                stack.append(a + b)\n"
    "            elif tok == '-':\n"
    "                stack.append(a - b)\n"
    "            elif tok == '*':\n"
    "                stack.append(a * b)\n"
    "            else:\n"
    "                q = abs(a) // abs(b)\n"
    "                stack.append(-q if (a < 0) != (b < 0) else q)\n"
    "        else:\n"
    "            stack.append(int(tok))\n"
    "    return stack.pop()\n"
    "def main():\n"
    "    line = sys.stdin.readline().strip()\n"
    "    tokens = line.split()\n"
    "    print(eval_rpn(to_rpn(tokens)))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_JSON_PATH_QUERY_CODE = (
    "import sys\n"
    "import json\n"
    "def main():\n"
    "    path = sys.argv[1]\n"
    "    data = sys.stdin.read()\n"
    "    try:\n"
    "        obj = json.loads(data)\n"
    "    except Exception:\n"
    "        print('null')\n"
    "        return\n"
    "    cur = obj\n"
    "    for seg in path.split('.'):\n"
    "        if isinstance(cur, dict):\n"
    "            if seg in cur:\n"
    "                cur = cur[seg]\n"
    "            else:\n"
    "                print('null')\n"
    "                return\n"
    "        elif isinstance(cur, list):\n"
    "            if seg.lstrip('-').isdigit():\n"
    "                idx = int(seg)\n"
    "                if 0 <= idx < len(cur):\n"
    "                    cur = cur[idx]\n"
    "                else:\n"
    "                    print('null')\n"
    "                    return\n"
    "            else:\n"
    "                print('null')\n"
    "                return\n"
    "        else:\n"
    "            print('null')\n"
    "            return\n"
    "    print(json.dumps(cur, separators=(',', ':')))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_REFERENCE_CODE = {
    "sqlite-persistent-kv-cli": _SQLITE_KV_CODE,
    "sql-mini-query-cli": _SQL_MINI_QUERY_CODE,
    "infix-expr-eval-cli": _INFIX_EVAL_CODE,
    "json-path-query-cli": _JSON_PATH_QUERY_CODE,
}


def _reference_build_fn(code):
    def build_fn(sentence, root):
        from pathlib import Path
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "main.py").write_text(code, encoding="utf-8")
        return {"modules": {"main.py": code}, "shipped": True, "done": True,
                "unmet": [], "plan": {"entrypoint": "main.py"}, "note": "DONE"}
    return build_fn


def test_reference_impls_cover_every_new_task():
    assert set(_REFERENCE_CODE) == NEW_TASK_NAMES


def test_new_tasks_are_internally_coherent_via_real_oracle():
    """Each new task's checks are satisfied by a straightforward, correct reference
    implementation of its OWN stated contract, run through the REAL run_creation_suite
    black-box oracle -- proving the checks are genuinely determined by the sentence, not
    trivially-always-true or accidentally unsatisfiable (Tenet 3)."""
    for task in _new_tasks():
        code = _REFERENCE_CODE[task.name]
        result = run_creation_suite(_reference_build_fn(code), tasks=[task])
        rec = result["results"][0]
        assert rec["accepted"] is True, f"{task.name}: {rec}"
        assert rec["n_checks_passed"] == rec["n_checks"] == len(task.checks)


def test_a_noop_program_scores_zero_on_new_tasks():
    """No-leak control: a program that does nothing satisfies none of the new checks -- the
    contract, not an accidentally-trivial oracle, is what's being tested."""
    noop_code = "if __name__ == '__main__':\n    pass\n"
    for task in _new_tasks():
        result = run_creation_suite(_reference_build_fn(noop_code), tasks=[task])
        rec = result["results"][0]
        assert rec["accepted"] is False, f"{task.name} unexpectedly accepted a no-op"
        assert rec["n_checks_passed"] == 0
