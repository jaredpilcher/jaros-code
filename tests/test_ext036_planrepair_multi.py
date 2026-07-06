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
should host the entrypoint"). `_repair_plan_entrypoint_multi` (this task, REQ-32) fills
the gap for the ONE unambiguous multi-module shape: a fully disconnected module set (no
module imports any sibling) -- there is no existing candidate to guess between, so it
ADDS a new entrypoint module importing every listed module. Any plan where an inter-
module import ALREADY exists is left untouched (genuinely ambiguous), preserving the
pre-existing `test_ext036_planrepair.py` conservatism byte-for-byte.

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

# The pre-existing PINNED ambiguous shape (test_ext036_planrepair.py) -- cli.py already
# imports the only other module, an existing wiring relationship -- must stay untouched.
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

# A 3-module chain a -> b -> c, entrypoint mismatched: an existing wiring relationship
# makes it ambiguous which module (if any) should host the entrypoint.
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

    assert note == (
        "plan-repair: added missing entrypoint module main.py "
        "importing ['graph_builder.py', 'bfs_solver.py']"
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


def test_existing_wiring_ambiguous_plan_left_untouched_no_regression():
    """The EXACT plan pinned by test_ext036_planrepair.py's
    test_multi_module_mismatched_entrypoint_still_rejected must stay untouched by the
    new function too -- an inter-module import already exists (cli.py imports
    calculator.py), so it is genuinely ambiguous and must not be guessed."""
    plan = json.loads(EXISTING_WIRING_AMBIGUOUS_PLAN)
    before = json.loads(EXISTING_WIRING_AMBIGUOUS_PLAN)

    repaired, note = _repair_plan_entrypoint_multi(plan)

    assert note is None
    assert repaired == before
    defects = validate_plan(repaired)
    assert any("entrypoint" in d for d in defects)


def test_chain_ambiguous_plan_left_untouched():
    plan = json.loads(CHAIN_AMBIGUOUS_PLAN)
    before = json.loads(CHAIN_AMBIGUOUS_PLAN)

    repaired, note = _repair_plan_entrypoint_multi(plan)

    assert note is None
    assert repaired == before
    assert any("entrypoint" in d for d in validate_plan(repaired))


def test_malformed_entrypoint_left_untouched():
    plan = json.loads(MALFORMED_ENTRYPOINT_PLAN)
    before = json.loads(MALFORMED_ENTRYPOINT_PLAN)

    repaired, note = _repair_plan_entrypoint_multi(plan)

    assert note is None
    assert repaired == before
    assert any("entrypoint" in d for d in validate_plan(repaired))


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
