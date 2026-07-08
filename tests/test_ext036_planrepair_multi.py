"""EXT-036 TASK-42: deterministic plan-repair for the MEASURED MULTI-module
"entrypoint not a listed module" coherence defect (REQ-32).

MEASURED ROOT CAUSE (hard-tier capability diagnostic, `.jaros-data/hardtier_failure_diag.json`,
2026-07-06): the `graph-bfs-shortest-path-cli` CREATION task fails at the PLAN stage --
`build_system`'s `note` = "plan failed coherence validation: entrypoint not a listed
module" -- a pure deterministic plan-coherence rejection, not a reasoning failure.
LIVE-REPRODUCED (3/3 identical draws against the served gemma-4-e2b): the plan lists 2
modules (`graph_builder.py`, `bfs_solver.py`), BOTH with `imports: []` (a fully
disconnected pair), and `entrypoint: "main.py"`, a filename never added as a module.

`_repair_plan_entrypoint` (TASK-19, REQ-1) already fixes the analogous SINGLE-module
case but deliberately leaves EVERY multi-module case untouched ("ambiguous which module
should host the entrypoint"). `_repair_plan_entrypoint_multi` (REQ-32) fills the gap for
the multi-module case by ADDING a new entrypoint module (it never renames/chooses an
existing one, so the "which module hosts the entrypoint" ambiguity never applies).

TASK-47 GENERALIZATION (MEASURED 2026-07-07 on `todo-list-cli`): the original repair only
fired for a FULLY DISCONNECTED module set; it left wired DAGs rejected, so the common
`data_manager.py` + `cli_handler.py`-imports-it + `entrypoint: main.py` shape built 0
files. The repair now fires for ANY acyclic plan: the added entrypoint imports the ROOT
modules (those NO sibling imports -- in-degree 0), the top of the dependency graph from
which every module is transitively reachable. A disconnected set has every module as a
root, so it reduces EXACTLY to the prior behavior (a strict superset). Only a genuinely
cyclic plan (no in-degree-0 module) is still declined, and `validate_plan`'s cycle check
keeps it rejected.

OFFLINE -- no live model. Only plan literals + the pure repair/validate functions.
"""

from __future__ import annotations

import json

from harness.system_builder import (
    _repair_plan_entrypoint,
    _repair_plan_entrypoint_multi,
    validate_plan,
)

# The MEASURED graph-bfs shape: 2 modules, neither imports the other, entrypoint
# ("main.py") not among the listed module names.
GRAPH_BFS_SHAPE_PLAN = """{
  "modules": [
    {"name": "graph_builder.py", "responsibility": "Parses input into an adjacency list.",
     "exports": [{"name": "build_graph", "signature": "def build_graph(input_lines):"}],
     "imports": []},
    {"name": "bfs_solver.py", "responsibility": "BFS shortest path.",
     "exports": [{"name": "find_shortest_path", "signature": "def find_shortest_path(graph, src, dst):"}],
     "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "Runs BFS and prints the shortest path length."
}"""

# A WIRED DAG: cli.py imports the only other module (calculator.py). Root = cli.py. Under
# TASK-47 this is now REPAIRED (main.py added importing cli.py), not left rejected. This is
# the `todo-list-cli` shape that was building 0 files before the generalization.
EXISTING_WIRING_AMBIGUOUS_PLAN = """{
  "modules": [
    {"name": "calculator.py", "responsibility": "does math",
     "exports": [{"name": "add", "signature": "def add(a, b):"}], "imports": []},
    {"name": "cli.py", "responsibility": "CLI wrapper",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": ["calculator.py"]}
  ],
  "entrypoint": "main.py",
  "acceptance": "python main.py prints hi"
}"""

# A 3-module chain a <- b <- c (c imports b imports a), entrypoint mismatched. Root = c.py
# (nothing imports it). Under TASK-47 this is now REPAIRED (main.py added importing c.py).
CHAIN_AMBIGUOUS_PLAN = """{
  "modules": [
    {"name": "a.py", "responsibility": "leaf",
     "exports": [{"name": "f", "signature": "def f():"}], "imports": []},
    {"name": "b.py", "responsibility": "middle",
     "exports": [{"name": "g", "signature": "def g():"}], "imports": ["a.py"]},
    {"name": "c.py", "responsibility": "top",
     "exports": [{"name": "h", "signature": "def h():"}], "imports": ["b.py"]}
  ],
  "entrypoint": "main.py",
  "acceptance": "x"
}"""

# A genuinely CYCLIC module graph: a.py imports b.py and b.py imports a.py -- every
# module has an incoming sibling import, so `roots` is empty (in-degree 0 for nobody).
# TASK-47's generalization must still decline here (no unambiguous top of the graph to
# import from) and leave the plan for `validate_plan`'s own "import cycle" check.
CYCLIC_PLAN = """{
  "modules": [
    {"name": "a.py", "responsibility": "x",
     "exports": [{"name": "f", "signature": "def f():"}], "imports": ["b.py"]},
    {"name": "b.py", "responsibility": "y",
     "exports": [{"name": "g", "signature": "def g():"}], "imports": ["a.py"]}
  ],
  "entrypoint": "main.py",
  "acceptance": "x"
}"""

# A malformed entrypoint (contains a space) -- nothing safe to add.
MALFORMED_ENTRYPOINT_PLAN = """{
  "modules": [
    {"name": "graph_builder.py", "responsibility": "x",
     "exports": [{"name": "build_graph", "signature": "def build_graph(x):"}], "imports": []},
    {"name": "bfs_solver.py", "responsibility": "x",
     "exports": [{"name": "find_shortest_path", "signature": "def find_shortest_path(g):"}], "imports": []}
  ],
  "entrypoint": "not a filename",
  "acceptance": "x"
}"""


def test_graph_bfs_shape_repaired_and_coherent():
    plan = json.loads(GRAPH_BFS_SHAPE_PLAN)
    before_defects = validate_plan(plan)
    assert "entrypoint not a listed module" in before_defects

    repaired, note = _repair_plan_entrypoint_multi(plan)

    # A fully DISCONNECTED set: every module is a root (in-degree 0), so main.py imports
    # them all -- identical to the original behavior, now phrased as "importing roots".
    assert note == (
        "plan-repair: added missing entrypoint module main.py "
        "importing roots ['graph_builder.py', 'bfs_solver.py']"
    )
    names = [m["name"] for m in repaired["modules"]]
    assert names == ["graph_builder.py", "bfs_solver.py", "main.py"]
    added = repaired["modules"][-1]
    assert added["name"] == "main.py"
    assert set(added["imports"]) == {"graph_builder.py", "bfs_solver.py"}
    assert added["exports"] and "(" in added["exports"][0]["signature"]
    assert validate_plan(repaired) == []


def test_single_module_repair_still_unaffected_by_the_new_function():
    """TASK-19's single-module repair is untouched: the new multi-module function is a
    no-op on a plan with fewer than 2 modules."""
    single_plan = json.loads(
        '{"modules": [{"name": "calculator.py", "exports": '
        '[{"name": "main", "signature": "def main():"}], "imports": []}], '
        '"entrypoint": "main.py", "acceptance": "x"}'
    )
    before = json.loads(json.dumps(single_plan))
    repaired, note = _repair_plan_entrypoint_multi(single_plan)
    assert note is None
    assert repaired == before

    # And _repair_plan_entrypoint (TASK-19) still does its own repair unchanged.
    fixed, rename_note = _repair_plan_entrypoint(json.loads(json.dumps(single_plan)))
    assert rename_note == "plan-repair: renamed sole module calculator.py -> main.py"
    assert validate_plan(fixed) == []


def test_existing_wiring_dag_now_repaired_by_importing_root():
    """TASK-47 generalization (MEASURED 2026-07-07 on `todo-list-cli`): a wired DAG
    (cli.py imports calculator.py) with a pinned `main.py` entrypoint is NO LONGER left
    rejected. Because the repair ADDS a new entrypoint module (it never renames/chooses an
    existing one), there is no "which module hosts the entrypoint" ambiguity -- the new
    main.py imports the ROOT modules (those no sibling imports; here cli.py), the top of
    the dependency DAG. This is the exact shape of the todo-list build that was failing
    with 0 files written."""
    plan = json.loads(EXISTING_WIRING_AMBIGUOUS_PLAN)

    repaired, note = _repair_plan_entrypoint_multi(plan)

    assert note == "plan-repair: added missing entrypoint module main.py importing roots ['cli.py']"
    added = repaired["modules"][-1]
    assert added["name"] == "main.py"
    assert added["imports"] == ["cli.py"]  # cli.py is the root; calculator.py is imported by it
    assert validate_plan(repaired) == []


def test_chain_dag_now_repaired_by_importing_top_root():
    """A 3-module chain a <- b <- c (c is the top root nothing imports) with a mismatched
    `main.py` entrypoint is now repaired: main.py imports the single root c.py, from which
    the rest of the chain is transitively reachable."""
    plan = json.loads(CHAIN_AMBIGUOUS_PLAN)

    repaired, note = _repair_plan_entrypoint_multi(plan)

    assert note == "plan-repair: added missing entrypoint module main.py importing roots ['c.py']"
    added = repaired["modules"][-1]
    assert added["name"] == "main.py"
    assert added["imports"] == ["c.py"]
    assert validate_plan(repaired) == []


def test_malformed_entrypoint_left_untouched():
    plan = json.loads(MALFORMED_ENTRYPOINT_PLAN)
    before = json.loads(MALFORMED_ENTRYPOINT_PLAN)

    repaired, note = _repair_plan_entrypoint_multi(plan)

    assert note is None
    assert repaired == before
    assert any("entrypoint" in d for d in validate_plan(repaired))


def test_cyclic_plan_left_untouched():
    """TASK-47's roots computation: a genuine a.py<->b.py cycle has NO in-degree-0
    module (`roots` is empty), so the function declines exactly like the pre-TASK-47
    "any sibling import" guard did, and `validate_plan` still rejects it -- both for
    the still-unlisted entrypoint AND the cycle itself."""
    plan = json.loads(CYCLIC_PLAN)
    before = json.loads(CYCLIC_PLAN)

    repaired, note = _repair_plan_entrypoint_multi(plan)

    assert note is None
    assert repaired == before
    defects = validate_plan(repaired)
    assert any("entrypoint" in d for d in defects)
    assert "import cycle" in defects


def test_never_raises_on_malformed_plan_shapes():
    assert _repair_plan_entrypoint_multi(None) == (None, None)
    assert _repair_plan_entrypoint_multi({}) == ({}, None)
    assert _repair_plan_entrypoint_multi({"modules": [], "entrypoint": "main.py"}) == (
        {"modules": [], "entrypoint": "main.py"}, None)
    assert _repair_plan_entrypoint_multi(
        {"modules": "not a list", "entrypoint": "main.py"}
    ) == ({"modules": "not a list", "entrypoint": "main.py"}, None)
    assert _repair_plan_entrypoint_multi(
        {"modules": [None, None], "entrypoint": "main.py"}
    ) == ({"modules": [None, None], "entrypoint": "main.py"}, None)
    # entrypoint not a string
    plan = {"modules": [{"name": "a.py"}, {"name": "b.py"}], "entrypoint": 5}
    assert _repair_plan_entrypoint_multi(plan) == (plan, None)
    # entrypoint empty string
    plan2 = {"modules": [{"name": "a.py"}, {"name": "b.py"}], "entrypoint": ""}
    assert _repair_plan_entrypoint_multi(plan2) == (plan2, None)
    # one module missing a name -- nothing safe to reason about
    plan3 = {"modules": [{"name": "a.py"}, {"exports": []}], "entrypoint": "main.py"}
    assert _repair_plan_entrypoint_multi(plan3) == (plan3, None)
    # non-dict module entries mixed in
    plan4 = {"modules": [{"name": "a.py"}, "not a dict"], "entrypoint": "main.py"}
    assert _repair_plan_entrypoint_multi(plan4) == (plan4, None)
    # entrypoint already listed -- nothing to repair
    plan5 = {
        "modules": [{"name": "a.py", "imports": []}, {"name": "b.py", "imports": []}],
        "entrypoint": "a.py",
    }
    before5 = json.loads(json.dumps(plan5))
    assert _repair_plan_entrypoint_multi(plan5) == (before5, None)


def test_build_system_ships_past_plan_stage_with_canned_graph_bfs_plan(tmp_path):
    """End-to-end through build_system: the exact measured graph-bfs plan shape no longer
    rejects at the coherence gate."""
    from harness.system_builder import build_system

    class _Resp:
        def __init__(self, text: str) -> None:
            self.text = text

    class _CannedLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, request):
            prompt = request.prompt
            if "build PLAN" in prompt:
                return _Resp(GRAPH_BFS_SHAPE_PLAN)
            if "ACCEPTANCE CHECKS" in prompt:
                return _Resp("[]")
            if "COMPLETE Python module" in prompt or "SYNTAX ERROR" in prompt:
                self.calls += 1
                return _Resp("def f():\n    pass\n")
            return _Resp("")

    llm = _CannedLlm()
    result = build_system(
        "A graph BFS shortest-path CLI.", tmp_path / "built", llm=llm
    )

    assert "coherence" not in (result.get("note") or "")
    assert "main.py" in result.get("plan", {}).get("modules", [{}])[-1].get("name", "") or any(
        m.get("name") == "main.py" for m in result.get("plan", {}).get("modules", [])
    )
    assert "added missing entrypoint module main.py" in result.get("plan_repair", "")
