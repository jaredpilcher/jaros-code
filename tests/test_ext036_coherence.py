"""EXT-036 TASK-26: Long-horizon build coherence instrument (REQ-23).

OFFLINE -- no live model, no network. ``run_coherence_suite`` itself never calls a model (its
whole job is to drive an arbitrary ``build_fn`` and independently check each of a prompt's stated
requirements); these tests use STUB ``build_fn`` callables that write files directly to ``root``,
playing the role of a real ``harness.system_builder.build_system`` call, so they prove the
instrument's plumbing (build -> per-requirement independent check -> coherence/aggregate,
never-raise robustness) without needing a live model.
"""

from __future__ import annotations

from pathlib import Path

from harness.coherence_suite import CoherenceTask, FIRST_SLICE, run_coherence_suite


def _build_fn_writing(code: str):
    def build_fn(prompt, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "main.py").write_text(code, encoding="utf-8")
        return {"modules": {"main.py": code}, "shipped": True, "done": True,
                "unmet": [], "plan": {"entrypoint": "main.py"}, "note": "DONE"}
    return build_fn


def _noop_build_fn(prompt, root):
    """Writes nothing -- the no-trivial-pass control."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return {"modules": {}, "shipped": False, "done": False, "unmet": [],
            "plan": None, "note": "no-op"}


# --- Reference (fully correct) implementations, one per FIRST_SLICE task -------------------

_STATS_CLI_REFERENCE = (
    "import sys\n"
    "def main():\n"
    "    if len(sys.argv) < 2 or sys.argv[1] not in ('sum', 'mean', 'max'):\n"
    "        print('usage: main.py {sum|mean|max}')\n"
    "        return\n"
    "    cmd = sys.argv[1]\n"
    "    line = sys.stdin.readline()\n"
    "    nums = [int(x) for x in line.split()]\n"
    "    if cmd == 'sum':\n"
    "        print(sum(nums))\n"
    "    elif cmd == 'mean':\n"
    "        print('%.2f' % (sum(nums) / len(nums)))\n"
    "    else:\n"
    "        print(max(nums))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_TEXT_TOOLS_CLI_REFERENCE = (
    "import sys\n"
    "def main():\n"
    "    valid = ('upper', 'lower', 'reverse', 'count-words')\n"
    "    if len(sys.argv) < 2 or sys.argv[1] not in valid:\n"
    "        print('usage: main.py {upper|lower|reverse|count-words}')\n"
    "        return\n"
    "    cmd = sys.argv[1]\n"
    "    line = sys.stdin.readline().rstrip(chr(10))\n"
    "    if cmd == 'upper':\n"
    "        print(line.upper())\n"
    "    elif cmd == 'lower':\n"
    "        print(line.lower())\n"
    "    elif cmd == 'reverse':\n"
    "        print(line[::-1])\n"
    "    else:\n"
    "        print(len(line.split()))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_LEDGER_CLI_REFERENCE = (
    "import sys\n"
    "def main():\n"
    "    balance = 0\n"
    "    for raw in sys.stdin:\n"
    "        parts = raw.split()\n"
    "        if not parts:\n"
    "            continue\n"
    "        cmd = parts[0]\n"
    "        if cmd == 'deposit':\n"
    "            balance += int(parts[1])\n"
    "            print('balance %d' % balance)\n"
    "        elif cmd == 'withdraw':\n"
    "            amount = int(parts[1])\n"
    "            if balance >= amount:\n"
    "                balance -= amount\n"
    "                print('balance %d' % balance)\n"
    "            else:\n"
    "                print('insufficient funds')\n"
    "        elif cmd == 'balance':\n"
    "            print('balance %d' % balance)\n"
    "        else:\n"
    "            print('usage: deposit|withdraw|balance')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_REFERENCE_CODE = {
    "stats-cli": _STATS_CLI_REFERENCE,
    "text-tools-cli": _TEXT_TOOLS_CLI_REFERENCE,
    "ledger-cli": _LEDGER_CLI_REFERENCE,
}


# --- Partial implementations: satisfy only k of N requirements per task --------------------
# Each deliberately implements SOME of the task's requirements correctly and leaves the rest
# genuinely unsatisfied (not merely mis-worded), proving ``coherence`` measures per-requirement
# COVERAGE, not an all-or-nothing pass.

_STATS_CLI_PARTIAL = (   # satisfies sum + max (2 of 4); mean + usage are wrong on purpose
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    nums = [int(x) for x in line.split()] if line.strip() else []\n"
    "    if len(sys.argv) > 1 and sys.argv[1] == 'sum':\n"
    "        print(sum(nums))\n"
    "    elif len(sys.argv) > 1 and sys.argv[1] == 'max':\n"
    "        print(max(nums))\n"
    "    else:\n"
    "        print('nope')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)
_STATS_CLI_PARTIAL_K = 2

_TEXT_TOOLS_CLI_PARTIAL = (   # satisfies upper + lower + reverse (3 of 5); count-words + usage wrong
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline().rstrip(chr(10))\n"
    "    valid = ('upper', 'lower', 'reverse')\n"
    "    if len(sys.argv) > 1 and sys.argv[1] in valid:\n"
    "        cmd = sys.argv[1]\n"
    "        if cmd == 'upper':\n"
    "            print(line.upper())\n"
    "        elif cmd == 'lower':\n"
    "            print(line.lower())\n"
    "        else:\n"
    "            print(line[::-1])\n"
    "    else:\n"
    "        print('???')\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)
_TEXT_TOOLS_CLI_PARTIAL_K = 3

_LEDGER_CLI_PARTIAL = (   # satisfies deposit + balance-query (2 of 5); withdraw + usage wrong/ignored
    "import sys\n"
    "def main():\n"
    "    balance = 0\n"
    "    for raw in sys.stdin:\n"
    "        parts = raw.split()\n"
    "        if not parts:\n"
    "            continue\n"
    "        cmd = parts[0]\n"
    "        if cmd == 'deposit':\n"
    "            balance += int(parts[1])\n"
    "            print('balance %d' % balance)\n"
    "        elif cmd == 'balance':\n"
    "            print('balance %d' % balance)\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)
_LEDGER_CLI_PARTIAL_K = 2

_PARTIAL_CODE_AND_K = {
    "stats-cli": (_STATS_CLI_PARTIAL, _STATS_CLI_PARTIAL_K),
    "text-tools-cli": (_TEXT_TOOLS_CLI_PARTIAL, _TEXT_TOOLS_CLI_PARTIAL_K),
    "ledger-cli": (_LEDGER_CLI_PARTIAL, _LEDGER_CLI_PARTIAL_K),
}


# --- TENET-3: reference implementations are FULLY coherent (satisfy every requirement) -----

def test_first_slice_registry_shape():
    assert len(FIRST_SLICE) in (2, 3)
    names = [t.name for t in FIRST_SLICE]
    assert len(names) == len(set(names))
    tiers = {t.tier for t in FIRST_SLICE}
    assert tiers <= {"easy", "medium", "hard", "highly-complex"}
    for task in FIRST_SLICE:
        assert task.prompt.strip()
        assert 4 <= len(task.requirements) <= 5
        for req in task.requirements:
            assert len(req) == 4
            req_id, argv, stdin, expected = req
            assert isinstance(req_id, str) and req_id
            assert isinstance(argv, list)
            assert isinstance(expected, str) and expected


def test_reference_implementations_are_fully_coherent():
    assert set(_REFERENCE_CODE) == {t.name for t in FIRST_SLICE}
    for task in FIRST_SLICE:
        code = _REFERENCE_CODE[task.name]
        result = run_coherence_suite(_build_fn_writing(code), tasks=[task])
        rec = result["results"][0]
        assert rec["all_satisfied"] is True, f"{task.name}: {rec}"
        assert rec["coherence"] == 1.0
        assert rec["requirements_satisfied"] == rec["requirements_total"] == len(task.requirements)


# --- Partial builds score coherence = k/N exactly (the drift/partial signal) ---------------

def test_partial_implementations_score_exact_fraction():
    assert set(_PARTIAL_CODE_AND_K) == {t.name for t in FIRST_SLICE}
    for task in FIRST_SLICE:
        code, k = _PARTIAL_CODE_AND_K[task.name]
        n = len(task.requirements)
        result = run_coherence_suite(_build_fn_writing(code), tasks=[task])
        rec = result["results"][0]
        assert rec["requirements_satisfied"] == k, f"{task.name}: {rec}"
        assert rec["requirements_total"] == n
        assert rec["coherence"] == k / n
        assert rec["all_satisfied"] is (k == n)


# --- No-op build_fn -> coherence 0.0 for every task (no trivial pass) -----------------------

def test_noop_build_fn_scores_zero_for_every_task():
    result = run_coherence_suite(_noop_build_fn, tasks=FIRST_SLICE)
    for rec in result["results"]:
        assert rec["requirements_satisfied"] == 0
        assert rec["coherence"] == 0.0
        assert rec["all_satisfied"] is False


def test_noop_build_fn_never_raises_with_empty_requirements_task():
    task = CoherenceTask(name="empty-reqs", tier="easy", prompt="x", requirements=[])
    result = run_coherence_suite(_noop_build_fn, tasks=[task])
    rec = result["results"][0]
    assert rec["requirements_total"] == 0
    assert rec["coherence"] == 0.0
    assert rec["all_satisfied"] is False


def test_build_fn_raising_never_aborts_the_suite():
    def raising_build_fn(prompt, root):
        raise RuntimeError("simulated build crash")

    result = run_coherence_suite(raising_build_fn, tasks=FIRST_SLICE)
    assert len(result["results"]) == len(FIRST_SLICE)
    for rec in result["results"]:
        assert rec["requirements_satisfied"] == 0
        assert rec["coherence"] == 0.0


def test_build_fn_returning_non_dict_never_raises():
    def build_fn(prompt, root):
        return None
    result = run_coherence_suite(build_fn, tasks=[FIRST_SLICE[0]])
    rec = result["results"][0]
    assert rec["requirements_satisfied"] == 0
    assert rec["coherence"] == 0.0


# --- Aggregate shape is well-formed ----------------------------------------------------------

def test_aggregate_shape_well_formed():
    result = run_coherence_suite(_noop_build_fn, tasks=FIRST_SLICE)
    agg = result["aggregate"]
    assert set(agg.keys()) == {"overall", "by_tier"}
    overall = agg["overall"]
    assert overall["n"] == len(FIRST_SLICE)
    assert overall["mean_coherence"] == 0.0
    assert overall["fully_coherent_rate"] == 0.0
    tiers = {t.tier for t in FIRST_SLICE}
    assert set(agg["by_tier"].keys()) == tiers
    for tier, rates in agg["by_tier"].items():
        assert rates["n"] == sum(1 for t in FIRST_SLICE if t.tier == tier)


def test_aggregate_mean_coherence_reflects_mixed_results():
    # one fully-coherent task + one 0-coherent task -> mean_coherence == 0.5, fully_coherent_rate == 0.5
    good_task = FIRST_SLICE[0]
    bad_task = CoherenceTask(
        name="always-fails", tier="easy", prompt="x",
        requirements=[("r1", [], None, "never-matches")],
    )
    code = _REFERENCE_CODE[good_task.name]

    def build_fn(prompt, root):
        if prompt == good_task.prompt:
            return _build_fn_writing(code)(prompt, root)
        return _noop_build_fn(prompt, root)

    result = run_coherence_suite(build_fn, tasks=[good_task, bad_task])
    overall = result["aggregate"]["overall"]
    assert overall["n"] == 2
    assert overall["mean_coherence"] == 0.5
    assert overall["fully_coherent_rate"] == 0.5


def test_empty_task_list_aggregates_without_raising():
    result = run_coherence_suite(_noop_build_fn, tasks=[])
    assert result["results"] == []
    assert result["aggregate"]["overall"]["n"] == 0
    assert result["aggregate"]["overall"]["mean_coherence"] == 0.0
    assert result["aggregate"]["by_tier"] == {}


def test_wall_seconds_reported_and_nonnegative():
    result = run_coherence_suite(_build_fn_writing(_STATS_CLI_REFERENCE), tasks=[FIRST_SLICE[0]])
    rec = result["results"][0]
    assert isinstance(rec["wall_seconds"], float)
    assert rec["wall_seconds"] >= 0.0
