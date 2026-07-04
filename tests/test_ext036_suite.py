"""EXT-036 TASK-14: Creation-suite framework + first slice (REQ-20).

OFFLINE -- no live model, no network. ``run_creation_suite`` itself never calls a model (the
suite's whole job is to drive an arbitrary ``build_fn`` and check the result with an INDEPENDENT
black-box CLI oracle); these tests use STUB ``build_fn`` callables that play the role of a real
``harness.system_builder.build_system`` call by writing files directly to ``root``, so they prove
the suite's plumbing (build -> black-box check -> aggregate, never-raise robustness) without
needing a live model.
"""

from __future__ import annotations

from pathlib import Path

from harness.system_suite import (
    ALL_CREATION_TASKS,
    CreationTask,
    FIRST_SLICE,
    HARDER_SLICE,
    run_creation_suite,
)

SUM_CLI_CODE = (
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    print(sum(int(x) for x in line.split()))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

BROKEN_CLI_CODE = "raise SystemExit(1)\n"

ONE_TASK = [CreationTask(
    name="sum-cli-test", cls="cli-tool", tier="easy",
    sentence="a CLI that sums numbers from stdin",
    checks=[([], "1 2 3\n", "6"), ([], "4 5\n", "9")],
)]


def _good_build_fn(sentence, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(SUM_CLI_CODE, encoding="utf-8")
    return {"modules": {"main.py": SUM_CLI_CODE}, "shipped": True, "done": True,
            "unmet": [], "plan": {"entrypoint": "main.py"}, "note": "DONE"}


def _broken_build_fn(sentence, root):
    """Ships (writes a file, plan names it), but the entrypoint itself is broken -- a real
    non-zero exit on every invocation."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(BROKEN_CLI_CODE, encoding="utf-8")
    return {"modules": {"main.py": BROKEN_CLI_CODE}, "shipped": True, "done": False,
            "unmet": ["x"], "plan": {"entrypoint": "main.py"}, "note": "NOT DONE"}


def _missing_entrypoint_build_fn(sentence, root):
    """The plan CLAIMS an entrypoint that was never actually written to root."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return {"modules": {}, "shipped": True, "done": False, "unmet": [],
            "plan": {"entrypoint": "nope.py"}, "note": "shipped but entrypoint missing"}


def _mixed_build_fn(sentence, root):
    """Raises for a sentinel sentence, otherwise delegates to the good stub -- lets a single
    build_fn drive a mix of crashing/succeeding tasks in one suite run."""
    if sentence == "CRASH":
        raise RuntimeError("simulated build crash")
    return _good_build_fn(sentence, root)


# --- (b) a passing stub system -> accepted=True --------------------------------------------

def test_passing_stub_system_is_accepted():
    result = run_creation_suite(_good_build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["shipped"] is True
    assert rec["accepted"] is True
    assert rec["n_checks_passed"] == 2
    assert rec["n_checks"] == 2


# --- (c) broken / missing-entrypoint stub -> accepted=False, suite does NOT raise ----------

def test_broken_entrypoint_stub_not_accepted_no_raise():
    result = run_creation_suite(_broken_build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["shipped"] is True          # the build itself reported shipped
    assert rec["accepted"] is False        # but the independent oracle catches the broken CLI
    assert rec["n_checks_passed"] == 0


def test_missing_entrypoint_stub_not_accepted_no_raise():
    result = run_creation_suite(_missing_entrypoint_build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["accepted"] is False
    assert rec["n_checks_passed"] == 0


def test_no_plan_never_accepted_no_raise():
    def build_fn(sentence, root):
        return {"modules": {}, "shipped": False, "done": False, "unmet": [],
                "plan": None, "note": "no plan"}
    result = run_creation_suite(build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["shipped"] is False
    assert rec["accepted"] is False


def test_build_fn_returns_non_dict_never_raises():
    def build_fn(sentence, root):
        return None
    result = run_creation_suite(build_fn, tasks=ONE_TASK)
    rec = result["results"][0]
    assert rec["accepted"] is False
    assert rec["shipped"] is False


# --- (d) a build_fn that raises for a task -> accepted=False, suite continues --------------

def test_build_fn_raises_task_continues_and_records_not_accepted():
    tasks = [
        CreationTask(name="crash-task", cls="cli-tool", tier="easy", sentence="CRASH",
                     checks=[([], "1 2\n", "3")]),
        CreationTask(name="ok-task", cls="cli-tool", tier="easy",
                     sentence="a CLI that sums numbers from stdin",
                     checks=[([], "1 2 3\n", "6")]),
    ]
    result = run_creation_suite(_mixed_build_fn, tasks=tasks)
    assert len(result["results"]) == 2   # the suite continued past the crash
    by_name = {r["name"]: r for r in result["results"]}
    assert by_name["crash-task"]["accepted"] is False
    assert by_name["ok-task"]["accepted"] is True


# --- (a) aggregation: accept-rate + per-tier breakdown --------------------------------------

def test_aggregate_accept_rate_and_per_tier_breakdown():
    tasks = [
        CreationTask(name="easy-ok", cls="cli-tool", tier="easy",
                     sentence="a CLI that sums numbers from stdin",
                     checks=[([], "1 2 3\n", "6")]),
        CreationTask(name="easy-bad", cls="cli-tool", tier="easy", sentence="CRASH",
                     checks=[([], "1 2\n", "3")]),
        CreationTask(name="hard-ok", cls="cli-tool", tier="hard",
                     sentence="a CLI that sums numbers from stdin",
                     checks=[([], "10 20\n", "30")]),
    ]
    result = run_creation_suite(_mixed_build_fn, tasks=tasks)
    agg = result["aggregate"]
    assert agg["overall"]["n"] == 3
    assert agg["overall"]["accept_rate"] == 2 / 3
    assert agg["overall"]["ship_rate"] == 2 / 3
    assert agg["by_tier"]["easy"]["n"] == 2
    assert agg["by_tier"]["easy"]["accept_rate"] == 0.5
    assert agg["by_tier"]["hard"]["n"] == 1
    assert agg["by_tier"]["hard"]["accept_rate"] == 1.0


def test_empty_task_list_aggregates_without_raising():
    result = run_creation_suite(_good_build_fn, tasks=[])
    assert result["results"] == []
    assert result["aggregate"]["overall"]["n"] == 0
    assert result["aggregate"]["overall"]["accept_rate"] == 0.0


# --- callable check support (the non-CLI escape hatch) -------------------------------------

def test_callable_check_supported():
    def _entrypoint_exists(root, plan):
        return (Path(root) / "main.py").is_file()

    tasks = [CreationTask(name="callable-task", cls="cli-tool", tier="easy",
                           sentence="a CLI that sums numbers from stdin",
                           checks=[_entrypoint_exists])]
    result = run_creation_suite(_good_build_fn, tasks=tasks)
    assert result["results"][0]["accepted"] is True


def test_callable_check_failure_not_accepted_no_raise():
    def _always_false(root, plan):
        return False

    tasks = [CreationTask(name="callable-task-2", cls="cli-tool", tier="easy",
                           sentence="a CLI that sums numbers from stdin",
                           checks=[_always_false])]
    result = run_creation_suite(_good_build_fn, tasks=tasks)
    assert result["results"][0]["accepted"] is False


# --- (e) the first-slice CreationTask registry ----------------------------------------------

def test_first_slice_registry_shape():
    assert len(FIRST_SLICE) == 12
    tiers = [t.tier for t in FIRST_SLICE]
    assert tiers.count("easy") == 4
    assert tiers.count("medium") == 4
    assert tiers.count("hard") == 4
    names = [t.name for t in FIRST_SLICE]
    assert len(names) == len(set(names))   # unique names
    for task in FIRST_SLICE:
        assert task.tier in ("easy", "medium", "hard")
        assert task.cls and isinstance(task.cls, str)
        assert task.sentence.strip()
        assert task.checks   # every task has at least one deterministic check
        for check in task.checks:
            assert callable(check) or len(check) == 3


def test_first_slice_actually_runs_offline_with_real_stub_entrypoint():
    """Sanity: at least one real first-slice task (sum-cli) is satisfied by a straightforward
    correct implementation of its own stated CLI contract -- proves the checks are internally
    coherent with the sentence they describe, not just well-formed."""
    sum_task = next(t for t in FIRST_SLICE if t.name == "sum-cli")

    def build_fn(sentence, root):
        return _good_build_fn(sentence, root)

    result = run_creation_suite(build_fn, tasks=[sum_task])
    assert result["results"][0]["accepted"] is True


# --- TASK-17: coherence of the +6 grown-suite tasks -----------------------------------------
# Each new FIRST_SLICE task gets a straightforward, correct reference implementation of its
# OWN stated CLI contract, run through the real suite oracle -- proving the checks are
# internally coherent with the sentence they describe (not just well-formed), the same way
# ``test_first_slice_actually_runs_offline_with_real_stub_entrypoint`` proves it for sum-cli.

_REVERSE_LINES_CODE = (
    "import sys\n"
    "def main():\n"
    "    for line in sys.stdin:\n"
    "        print(line.rstrip(chr(10))[::-1])\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_MAX_CLI_CODE = (
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    print(max(int(x) for x in line.split()))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_RPN_CODE = (
    "import sys\n"
    "def main():\n"
    "    tokens = sys.stdin.readline().split()\n"
    "    stack = []\n"
    "    for tok in tokens:\n"
    "        if tok in ('+', '-', '*', '/'):\n"
    "            b = stack.pop()\n"
    "            a = stack.pop()\n"
    "            if tok == '+':\n"
    "                stack.append(a + b)\n"
    "            elif tok == '-':\n"
    "                stack.append(a - b)\n"
    "            elif tok == '*':\n"
    "                stack.append(a * b)\n"
    "            else:\n"
    "                stack.append(int(a / b))\n"
    "        else:\n"
    "            stack.append(int(tok))\n"
    "    print(stack.pop())\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_KV_SORTED_CODE = (
    "import sys\n"
    "def main():\n"
    "    store = {}\n"
    "    for line in sys.stdin:\n"
    "        line = line.strip()\n"
    "        if not line:\n"
    "            continue\n"
    "        key, _, value = line.partition('=')\n"
    "        store[key] = value\n"
    "    for key in sorted(store):\n"
    "        print(key + '=' + store[key])\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_PUBSUB_CODE = (
    "import sys\n"
    "from collections import defaultdict\n"
    "def main():\n"
    "    subs = defaultdict(list)\n"
    "    for line in sys.stdin:\n"
    "        parts = line.split()\n"
    "        if not parts:\n"
    "            continue\n"
    "        cmd = parts[0]\n"
    "        if cmd == 'subscribe':\n"
    "            _, name, topic = parts\n"
    "            subs[topic].append(name)\n"
    "            print('subscribed ' + name + ' ' + topic)\n"
    "        elif cmd == 'publish':\n"
    "            _, topic, message = parts\n"
    "            names = subs.get(topic, [])\n"
    "            if not names:\n"
    "                print('no subscribers')\n"
    "            else:\n"
    "                for name in names:\n"
    "                    print(name + ' received ' + message)\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_RATE_LIMITER_CODE = (
    "import sys\n"
    "def main():\n"
    "    limit = int(sys.argv[1])\n"
    "    count = 0\n"
    "    for line in sys.stdin:\n"
    "        parts = line.split()\n"
    "        if not parts:\n"
    "            continue\n"
    "        _, rid = parts\n"
    "        count += 1\n"
    "        if count <= limit:\n"
    "            print('allow ' + rid)\n"
    "        else:\n"
    "            print('deny ' + rid)\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_NEW_TASK_REFERENCE_CODE = {
    "reverse-lines-cli": _REVERSE_LINES_CODE,
    "max-of-stdin-cli": _MAX_CLI_CODE,
    "rpn-calc-cli": _RPN_CODE,
    "kv-lines-sorted-cli": _KV_SORTED_CODE,
    "pubsub-cli": _PUBSUB_CODE,
    "rate-limiter-cli": _RATE_LIMITER_CODE,
}


def _reference_build_fn(code):
    def build_fn(sentence, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "main.py").write_text(code, encoding="utf-8")
        return {"modules": {"main.py": code}, "shipped": True, "done": True,
                "unmet": [], "plan": {"entrypoint": "main.py"}, "note": "DONE"}
    return build_fn


def test_grown_suite_tasks_are_internally_coherent():
    """TASK-17: each of the +6 grown-suite tasks' ``checks`` are satisfied by a straightforward
    correct implementation of its OWN stated contract -- proves the checks are genuinely
    determined by the sentence, not accidentally unsatisfiable or trivially-always-true."""
    assert set(_NEW_TASK_REFERENCE_CODE) == {
        t.name for t in FIRST_SLICE
        if t.name not in {"sum-cli", "wordcount-cli", "todo-list-cli",
                           "temp-converter-cli", "kv-store-ttl-cli",
                           "priority-jobqueue-cli"}
    }
    for task in FIRST_SLICE:
        code = _NEW_TASK_REFERENCE_CODE.get(task.name)
        if code is None:
            continue
        result = run_creation_suite(_reference_build_fn(code), tasks=[task])
        rec = result["results"][0]
        assert rec["accepted"] is True, f"{task.name}: {rec}"
        assert rec["n_checks_passed"] == rec["n_checks"] == len(task.checks)


# --- HARDER_SLICE: +8 more classes, medium/hard/highly-complex tiers (owner directive) ------
# CREATION is gemma's WEAK half (~83% gemma / ~92% escalating system), so it has the most
# headroom and is the headline instrument -- grow it with genuinely HARDER, more diverse
# classes, following the exact TASK-15/17 contract-precise convention. Each new task gets a
# straightforward, correct reference implementation of its OWN stated contract, run through the
# REAL suite oracle -- proving the checks are genuinely satisfiable (not accidentally
# unsatisfiable or trivially-always-true), mirroring the FIRST_SLICE coherence tests above.

_JSON_VALIDATOR_CODE = (
    "import sys\n"
    "import json\n"
    "def main():\n"
    "    data = sys.stdin.read()\n"
    "    try:\n"
    "        obj = json.loads(data)\n"
    "    except Exception:\n"
    "        print('invalid: not valid json')\n"
    "        return\n"
    "    if (isinstance(obj, dict) and isinstance(obj.get('name'), str)\n"
    "            and isinstance(obj.get('port'), int) and not isinstance(obj.get('port'), bool)):\n"
    "        print('VALID')\n"
    "    else:\n"
    "        print('invalid: missing or bad field')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_GRAPH_BFS_CODE = (
    "import sys\n"
    "from collections import deque, defaultdict\n"
    "def main():\n"
    "    data = sys.stdin.read().split(chr(10))\n"
    "    idx = 0\n"
    "    n = int(data[idx].strip()); idx += 1\n"
    "    adj = defaultdict(set)\n"
    "    for _ in range(n):\n"
    "        u, v = data[idx].split(); idx += 1\n"
    "        adj[u].add(v)\n"
    "        adj[v].add(u)\n"
    "    src, dst = data[idx].split()\n"
    "    if src == dst:\n"
    "        print(0)\n"
    "        return\n"
    "    visited = {src}\n"
    "    q = deque([(src, 0)])\n"
    "    while q:\n"
    "        node, dist = q.popleft()\n"
    "        for nxt in adj.get(node, ()):\n"
    "            if nxt == dst:\n"
    "                print(dist + 1)\n"
    "                return\n"
    "            if nxt not in visited:\n"
    "                visited.add(nxt)\n"
    "                q.append((nxt, dist + 1))\n"
    "    print(-1)\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_BRACKET_BALANCE_CODE = (
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline().strip()\n"
    "    pairs = {')': '(', ']': '[', '}': '{'}\n"
    "    stack = []\n"
    "    ok = True\n"
    "    for ch in line:\n"
    "        if ch in '([{':\n"
    "            stack.append(ch)\n"
    "        elif ch in ')]}':\n"
    "            if not stack or stack.pop() != pairs[ch]:\n"
    "                ok = False\n"
    "                break\n"
    "    if stack:\n"
    "        ok = False\n"
    "    print('balanced' if ok else 'unbalanced')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_RLE_CODEC_CODE = (
    "import sys\n"
    "import re\n"
    "def _encode(s):\n"
    "    out = []\n"
    "    i = 0\n"
    "    while i < len(s):\n"
    "        j = i\n"
    "        while j < len(s) and s[j] == s[i]:\n"
    "            j += 1\n"
    "        out.append(str(j - i) + s[i])\n"
    "        i = j\n"
    "    return ''.join(out)\n"
    "def _decode(s):\n"
    "    out = []\n"
    "    for count, ch in re.findall(r'(\\d+)(\\D)', s):\n"
    "        out.append(ch * int(count))\n"
    "    return ''.join(out)\n"
    "def main():\n"
    "    mode = sys.argv[1]\n"
    "    line = sys.stdin.readline().strip()\n"
    "    if mode == 'encode':\n"
    "        print(_encode(line))\n"
    "    else:\n"
    "        print(_decode(line))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_CSV_AGGREGATOR_CODE = (
    "import sys\n"
    "def main():\n"
    "    column, agg = sys.argv[1], sys.argv[2]\n"
    "    lines = [ln for ln in sys.stdin.read().splitlines() if ln.strip()]\n"
    "    header = lines[0].split(',')\n"
    "    idx = header.index(column)\n"
    "    values = [float(row.split(',')[idx]) for row in lines[1:]]\n"
    "    if agg == 'sum':\n"
    "        result = sum(values)\n"
    "    else:\n"
    "        result = sum(values) / len(values) if values else 0.0\n"
    "    print('%.2f' % result)\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_TRAFFIC_LIGHT_CODE = (
    "import sys\n"
    "def main():\n"
    "    n = int(sys.argv[1])\n"
    "    states = ['RED', 'GREEN', 'YELLOW']\n"
    "    for i in range(n):\n"
    "        print(states[i % 3])\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_LRU_CACHE_CODE = (
    "import sys\n"
    "from collections import OrderedDict\n"
    "def main():\n"
    "    capacity = int(sys.argv[1])\n"
    "    cache = OrderedDict()\n"
    "    for line in sys.stdin:\n"
    "        parts = line.split()\n"
    "        if not parts:\n"
    "            continue\n"
    "        if parts[0] == 'put':\n"
    "            key, value = parts[1], parts[2]\n"
    "            if key in cache:\n"
    "                del cache[key]\n"
    "            cache[key] = value\n"
    "            if len(cache) > capacity:\n"
    "                cache.popitem(last=False)\n"
    "            print('ok')\n"
    "        elif parts[0] == 'get':\n"
    "            key = parts[1]\n"
    "            if key in cache:\n"
    "                value = cache.pop(key)\n"
    "                cache[key] = value\n"
    "                print(value)\n"
    "            else:\n"
    "                print('none')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_MATRIX_TRANSPOSE_CODE = (
    "import sys\n"
    "def main():\n"
    "    data = sys.stdin.read().split()\n"
    "    idx = 0\n"
    "    r = int(data[idx]); idx += 1\n"
    "    c = int(data[idx]); idx += 1\n"
    "    matrix = []\n"
    "    for _ in range(r):\n"
    "        row = [int(data[idx + k]) for k in range(c)]\n"
    "        idx += c\n"
    "        matrix.append(row)\n"
    "    for j in range(c):\n"
    "        print(' '.join(str(matrix[i][j]) for i in range(r)))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_HARDER_SLICE_REFERENCE_CODE = {
    "json-config-validator-cli": _JSON_VALIDATOR_CODE,
    "graph-bfs-shortest-path-cli": _GRAPH_BFS_CODE,
    "bracket-balance-cli": _BRACKET_BALANCE_CODE,
    "run-length-codec-cli": _RLE_CODEC_CODE,
    "csv-column-aggregator-cli": _CSV_AGGREGATOR_CODE,
    "traffic-light-sequencer-cli": _TRAFFIC_LIGHT_CODE,
    "lru-cache-cli": _LRU_CACHE_CODE,
    "matrix-transpose-cli": _MATRIX_TRANSPOSE_CODE,
}


def test_harder_slice_registry_shape():
    assert len(HARDER_SLICE) == 8
    names = [t.name for t in HARDER_SLICE]
    assert len(names) == len(set(names))   # unique names, and distinct from FIRST_SLICE
    assert set(names).isdisjoint({t.name for t in FIRST_SLICE})
    tiers = [t.tier for t in HARDER_SLICE]
    assert set(tiers) <= {"medium", "hard", "highly-complex"}
    assert "easy" not in tiers   # HARDER_SLICE is explicitly medium/hard/highly-complex only
    for task in HARDER_SLICE:
        assert task.cls and isinstance(task.cls, str)
        assert "main.py" in task.sentence   # every task pins the single-file entrypoint
        assert task.sentence.strip()
        assert len(task.checks) >= 2        # at least 2 deterministic checks each
        for check in task.checks:
            assert callable(check) or len(check) == 3


def test_all_creation_tasks_is_first_plus_harder():
    assert ALL_CREATION_TASKS == FIRST_SLICE + HARDER_SLICE


def test_harder_slice_tasks_are_internally_coherent():
    """TENET-3 coherence: every HARDER_SLICE task's ``checks`` are satisfied by a
    straightforward correct reference implementation of its OWN stated contract, run through
    the REAL ``run_creation_suite`` oracle -- proving each new task's contract is genuinely
    SATISFIABLE (not accidentally unsatisfiable) and its checks are actually determined by the
    stated sentence, not trivially-always-true."""
    assert set(_HARDER_SLICE_REFERENCE_CODE) == {t.name for t in HARDER_SLICE}
    for task in HARDER_SLICE:
        code = _HARDER_SLICE_REFERENCE_CODE[task.name]
        result = run_creation_suite(_reference_build_fn(code), tasks=[task])
        rec = result["results"][0]
        assert rec["accepted"] is True, f"{task.name}: {rec}"
        assert rec["n_checks_passed"] == rec["n_checks"] == len(task.checks)
